# gipcco_project/inventory/tests_purchasing.py

from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Sum, Q
from django.contrib.contenttypes.models import ContentType

from .models import (
    PurchaseOrder, PurchaseOrderItem, InventoryLog, PurchaseReturn,
    PurchaseReturnItem, SupplierDebitMemo, JournalEntry, JournalEntryLine,  # Add JournalEntryLine
    LandedCostInvoice, LandedCostType, Product, LandedCostInvoiceItem,
    SupplierInvoice
)
from .services import purchasing_service
from .test_base import AccountingServiceBaseTestCase


class PurchasingServiceTestCase(AccountingServiceBaseTestCase):
    """
    Test suite for the purchasing services, including returns and landed costs.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # --- Basic setup from parent is already done ---
        cls.supplier = cls.create_company("Test Supplier Co")
        cls.vendor = cls.create_company("Test Shipping Vendor")
        cls.product = cls.create_product("RM-PUR-01", "Test Raw Material", Product.ProductType.RAW_MATERIAL)

    def test_create_purchase_return_validation(self):
        """
        Ensures that a purchase return cannot be created for a quantity
        greater than the available quantity from the original receipt.
        """
        po = purchasing_service.create_purchase_order(
            user=self.user,
            po_data={'po_number': 'PO-VALIDATE', 'supplier_id': self.supplier.id, 'order_date': '2025-09-05'},
            items_data=[{'product_id': self.product.id, 'quantity': 100, 'base_price_per_unit': 10, 'vat_rate': 0.14, 'withholding_tax_rate': 0.01}],
            landed_costs_data=[]
        )
        receipt = self.create_inventory_log(self.supplier, self.product, 100, 10, po.items.first())

        # 1. Test returning more than available
        with self.assertRaises(ValidationError, msg="Should not allow returning more than received"):
            purchasing_service.create_purchase_return(
                user=self.user,
                return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-10'},
                items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': 101}]
            )

        # 2. Test returning a negative or zero quantity
        with self.assertRaises(ValidationError, msg="Should not allow returning zero quantity"):
            purchasing_service.create_purchase_return(
                user=self.user,
                return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-10'},
                items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': 0}]
            )

        # 3. Create a valid partial return
        purchasing_service.create_purchase_return(
            user=self.user,
            return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-11'},
            items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': 60}]
        )
        self.assertEqual(PurchaseReturn.objects.count(), 1)

        # 4. Test returning more than the REMAINING available quantity
        with self.assertRaises(ValidationError, msg="Should not allow returning more than remaining quantity"):
            purchasing_service.create_purchase_return(
                user=self.user,
                return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-12'},
                items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': 41}] # 100 - 60 = 40 available
            )

        # 5. Create a second valid return that uses up the remaining quantity
        pr2 = purchasing_service.create_purchase_return(
            user=self.user,
            return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-13'},
            items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': 40}]
        )
        self.assertEqual(PurchaseReturn.objects.count(), 2)


    def test_purchase_return_and_debit_memo_workflow(self):
        """
        Tests the full workflow:
        1. Create a purchase return.
        2. Process the inventory adjustment (crediting inventory, debiting clearing).
        3. Create a debit memo (debiting A/P, crediting clearing).
        """
        po = purchasing_service.create_purchase_order(
            user=self.user,
            po_data={'po_number': 'PO-RETURN-WF', 'supplier_id': self.supplier.id, 'order_date': '2025-09-05'},
            items_data=[{'product_id': self.product.id, 'quantity': 50, 'base_price_per_unit': 20, 'vat_rate': 0, 'withholding_tax_rate': 0}],
            landed_costs_data=[]
        )
        receipt = self.create_inventory_log(self.supplier, self.product, 50, 20, po.items.first())
        return_qty = 30
        return_value = Decimal(str(return_qty)) * receipt.costing_unit_price

        # Step 1: Create the Purchase Return object
        pr = purchasing_service.create_purchase_return(
            user=self.user,
            return_data={'supplier_id': self.supplier.id, 'return_date': '2025-09-15'},
            items_data=[{'original_receipt_id': receipt.id, 'quantity_returned': return_qty}]
        )
        self.assertEqual(pr.status, PurchaseReturn.Status.PENDING)

        # Step 2: Process the inventory movement
        purchasing_service.process_inventory_return(self.user, pr)
        pr.refresh_from_db()
        self.assertEqual(pr.status, PurchaseReturn.Status.COMPLETED)
        
        # Verify the inventory adjustment and its JE
        adj = PurchaseReturnItem.objects.get(purchase_return=pr).inventory_adjustment
        self.assertIsNotNone(adj)
        self.assertEqual(adj.adjustment_quantity, -return_qty)
        
        adj_je = self.get_je_for_object(adj)
        self.assertTrue(adj_je.is_balanced())
        self.assertEqual(adj_je.lines.count(), 2)
        self.assertEqual(
            adj_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).account,
            self.general_settings.purchase_returns_clearing_account
        )
        self.assertEqual(
            adj_je.lines.get(entry_type=JournalEntryLine.EntryType.CREDIT).account,
            self.get_product_type_setting(self.product.product_type).inventory_account
        )
        self.assertEqual(adj_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).amount, return_value)

        # Step 3: Create the Debit Memo and its JE
        memo = purchasing_service.create_debit_memo_from_return(
            user=self.user,
            purchase_return=pr,
            memo_data={'memo_number': 'DM-001', 'memo_date': '2025-09-16'}
        )
        self.assertEqual(memo.total_amount, return_value)
        self.assertIsNotNone(memo.journal_entry)
        
        memo_je = memo.journal_entry
        self.assertTrue(memo_je.is_balanced())
        self.assertEqual(memo_je.lines.count(), 2)
        self.assertEqual(
            memo_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).account,
            self.general_settings.accounts_payable
        )
        self.assertEqual(
            memo_je.lines.get(entry_type=JournalEntryLine.EntryType.CREDIT).account,
            self.general_settings.purchase_returns_clearing_account
        )
        self.assertEqual(memo_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).amount, return_value)

        # Final check: The clearing account should be balanced
        clearing_balance = JournalEntryLine.objects.filter(
            account=self.general_settings.purchase_returns_clearing_account
        ).aggregate(
            balance=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.DEBIT)) - Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.CREDIT))
        )['balance']
        self.assertEqual(clearing_balance, Decimal('0.000'))


    def test_post_supplier_invoice_with_ppv_and_taxes(self):
        """
        Tests the 3-way match posting of a supplier invoice that has:
        1. A different price from the PO (creating a Purchase Price Variance).
        2. VAT and Withholding Tax.
        """
        # Step 1: Create PO and Receipt
        po_price = Decimal('100.000')
        po_qty = 10
        vat_rate = Decimal('0.14')
        wht_rate = Decimal('0.01')
        
        po = purchasing_service.create_purchase_order(
            user=self.user,
            po_data={'po_number': 'PO-PPV', 'supplier_id': self.supplier.id, 'order_date': '2025-09-20'},
            items_data=[{
                'product_id': self.product.id, 'quantity': po_qty, 'base_price_per_unit': po_price,
                'vat_rate': vat_rate, 'withholding_tax_rate': wht_rate
            }],
            landed_costs_data=[]
        )
        receipt = self.create_inventory_log(self.supplier, self.product, po_qty, po_price, po.items.first())

        # Step 2: Create a Supplier Invoice with a different price
        invoice_price = Decimal('105.000') # Unfavorable PPV
        actual_subtotal = invoice_price * po_qty
        actual_vat = actual_subtotal * vat_rate

        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number='INV-PPV-01',
            invoice_date='2025-09-22',
            due_date='2025-10-22',
            actual_subtotal=actual_subtotal,
            actual_vat=actual_vat
        )
        invoice.items.create(
            receipt=receipt,
            amount=(receipt.base_unit_price * Decimal(str(receipt.quantity))) + receipt.vat_amount
        )

        # Step 3: Post the invoice
        purchasing_service.post_supplier_invoice(invoice)
        invoice.refresh_from_db()

        # --- FIX: Re-fetch the JournalEntry from the database to get the freshest object ---
        je = JournalEntry.objects.get(pk=invoice.journal_entry.id)

        self.assertEqual(invoice.status, SupplierInvoice.InvoiceStatus.AWAITING_PAYMENT)
        self.assertIsNotNone(je)
        self.assertTrue(je.is_balanced())

        # Step 4: Verify the Journal Entry lines
        # Based on receipt:
        receipt_base_value = po_price * po_qty
        receipt_vat_value = receipt_base_value * vat_rate
        receipt_wht_value = receipt_base_value * wht_rate
        
        # Correct GRNI value is Base + VAT - WHT
        grni_value = receipt_base_value + receipt_vat_value - receipt_wht_value

        # Based on invoice:
        ap_value = actual_subtotal + actual_vat - receipt_wht_value
        ppv_value = actual_subtotal - receipt_base_value
        vat_variance = actual_vat - receipt_vat_value

        # Helper to get total amount for an account and entry type in the JE
        def get_total_for_account(account, entry_type):
            # FIX: Use lowercase 'debit' and 'credit' to match database values
            return je.lines.filter(
                account=account, 
                entry_type=entry_type.lower()  # Convert DEBIT -> debit
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0.000')

        # Assertions
        self.assertEqual(get_total_for_account(self.general_settings.goods_received_not_invoiced_account, 'DEBIT'), grni_value)
        self.assertEqual(get_total_for_account(self.general_settings.accounts_payable, 'CREDIT'), ap_value)
        
        # For variances, check debit for unfavorable, credit for favorable
        if ppv_value >= 0:
            self.assertEqual(get_total_for_account(self.general_settings.purchase_price_variance_account, 'DEBIT'), ppv_value)
        else:
            self.assertEqual(get_total_for_account(self.general_settings.purchase_price_variance_account, 'CREDIT'), abs(ppv_value))

        if vat_variance >= 0:
            self.assertEqual(get_total_for_account(self.general_settings.vat_receivable, 'DEBIT'), vat_variance)
        else:
            self.assertEqual(get_total_for_account(self.general_settings.vat_receivable, 'CREDIT'), abs(vat_variance))


    def test_full_landed_cost_workflow_with_proration_and_variance(self):
        """
        Tests the complete, refactored landed cost workflow:
        1.  PO is created with a total estimated landed cost, allocated by percentage.
        2.  A partial receipt correctly prorates and capitalizes its share of the cost.
        3.  A final receipt capitalizes the remaining share.
        4.  A Landed Cost Invoice is posted with a different actual cost.
        5.  The variance is calculated correctly and posted to a variance account.
        6.  The Accrued Landed Costs account is fully cleared for the transaction.
        """
        # 1. --- Setup: PO with two items and one PO-level landed cost ---
        product1 = self.create_product("RM-LC-01", "LC Test Product 1")
        product2 = self.create_product("RM-LC-02", "LC Test Product 2")
        freight_cost_type = LandedCostType.objects.create(name="Ocean Freight")

        po_price1 = Decimal('10.000')
        po_qty1 = 100  # Total value = 1000
        po_price2 = Decimal('50.000')
        po_qty2 = 20   # Total value = 1000
        
        # Total PO value = 2000. We'll allocate landed costs 50/50 based on value.
        total_estimated_freight = Decimal('200.000')

        po = purchasing_service.create_purchase_order(
            user=self.user,
            po_data={'po_number': 'PO-LC-FULL', 'supplier_id': self.supplier.id, 'order_date': '2025-09-25'},
            items_data=[
                {
                    'product_id': product1.id, 'quantity': po_qty1, 'base_price_per_unit': po_price1,
                    'vat_rate': 0, 'withholding_tax_rate': 0, 'landed_cost_allocation_percentage': '50.0'
                },
                {
                    'product_id': product2.id, 'quantity': po_qty2, 'base_price_per_unit': po_price2,
                    'vat_rate': 0, 'withholding_tax_rate': 0, 'landed_cost_allocation_percentage': '50.0'
                }
            ],
            landed_costs_data=[
                {'cost_type_id': freight_cost_type.id, 'estimated_amount': total_estimated_freight}
            ]
        )
        po_item1 = po.items.get(product=product1)
        po_item2 = po.items.get(product=product2)

        # 2. --- Partial Receipt of Item 1 ---
        receipt1_qty = 60
        receipt1 = self.create_inventory_log(self.supplier, product1, receipt1_qty, po_price1, po_item1)
        
        # Verification for Receipt 1
        landed_cost_for_item1 = total_estimated_freight * (Decimal('50.0') / Decimal('100.0')) # 200 * 50% = 100
        prorated_cost_for_receipt1 = landed_cost_for_item1 * (Decimal(receipt1_qty) / Decimal(po_qty1)) # 100 * (60/100) = 60
        
        receipt1.refresh_from_db()
        self.assertEqual(receipt1.landed_cost_component * Decimal(receipt1_qty), prorated_cost_for_receipt1)
        
        receipt1_je = self.get_je_for_object(receipt1)
        self.assertEqual(
            receipt1_je.lines.get(account=self.general_settings.accrued_landed_costs_account).amount,
            prorated_cost_for_receipt1
        )

        # 3. --- Final Receipt of Item 1 and Full Receipt of Item 2 ---
        receipt2_qty = po_qty1 - receipt1_qty # 40
        receipt2 = self.create_inventory_log(self.supplier, product1, receipt2_qty, po_price1, po_item1)
        receipt3 = self.create_inventory_log(self.supplier, product2, po_qty2, po_price2, po_item2)

        # Verification for Receipt 2
        prorated_cost_for_receipt2 = landed_cost_for_item1 * (Decimal(receipt2_qty) / Decimal(po_qty1)) # 100 * (40/100) = 40
        receipt2.refresh_from_db()
        self.assertEqual(receipt2.landed_cost_component * Decimal(receipt2_qty), prorated_cost_for_receipt2)

        # Verification for Receipt 3
        landed_cost_for_item2 = total_estimated_freight * (Decimal('50.0') / Decimal('100.0')) # 200 * 50% = 100
        prorated_cost_for_receipt3 = landed_cost_for_item2 * (Decimal(po_qty2) / Decimal(po_qty2)) # 100 * (20/20) = 100
        receipt3.refresh_from_db()
        self.assertEqual(receipt3.landed_cost_component * Decimal(po_qty2), prorated_cost_for_receipt3)

        # Total accrued should now equal the total estimate
        total_accrued = prorated_cost_for_receipt1 + prorated_cost_for_receipt2 + prorated_cost_for_receipt3
        self.assertEqual(total_accrued, total_estimated_freight)

        # 4. --- Post Landed Cost Invoice with Variance ---
        actual_freight_cost = Decimal('235.000') # Unfavorable variance of 35
        variance = actual_freight_cost - total_estimated_freight

        lc_invoice = LandedCostInvoice.objects.create(
            vendor=self.vendor,
            invoice_number='LC-INV-FULL-01',
            invoice_date='2025-09-28',
            total_amount=actual_freight_cost,
            purchase_order=po
        )
        purchasing_service.post_landed_cost_invoice(lc_invoice, self.user)
        
        # 5. --- Verify Final Journal Entry ---
        receipt1_je = self.get_je_for_object(receipt1)
        receipt2_je = self.get_je_for_object(receipt2)
        receipt3_je = self.get_je_for_object(receipt3)
        bill_je = self.get_je_for_object(lc_invoice)
        self.assertTrue(bill_je.is_balanced())
        self.assertEqual(bill_je.lines.count(), 3)

        # DEBIT Accrued Landed Costs (clearing the accrual)
        self.assertEqual(
            bill_je.lines.get(account=self.general_settings.accrued_landed_costs_account).amount,
            total_estimated_freight
        )
        # DEBIT Landed Cost Variance (unfavorable)
        self.assertEqual(
            bill_je.lines.get(account=self.general_settings.landed_cost_variance_account).amount,
            variance
        )
        # CREDIT Accounts Payable (actual liability)
        self.assertEqual(
            bill_je.lines.get(account=self.general_settings.accounts_payable).amount,
            actual_freight_cost
        )

        # 6. --- Verify Clearing Account is Balanced ---
        final_balance = JournalEntryLine.objects.filter(
            account=self.general_settings.accrued_landed_costs_account,
            journal_entry__in=[receipt1_je, receipt2_je, receipt3_je, bill_je]
        ).aggregate(
            balance=Sum('amount', filter=Q(entry_type='credit')) - Sum('amount', filter=Q(entry_type='debit'))
        )['balance']
        
        self.assertEqual(final_balance, Decimal('0.000'))
