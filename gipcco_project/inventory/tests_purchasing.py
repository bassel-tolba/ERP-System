# gipcco_project/inventory/tests_purchasing.py

from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Sum, Q
from django.contrib.contenttypes.models import ContentType

from .models import (
    PurchaseOrder, PurchaseOrderItem, InventoryLog, PurchaseReturn,
    PurchaseReturnItem, SupplierDebitMemo, JournalEntry, JournalEntryLine,
    LandedCostInvoice, LandedCostType, LandedCostAllocation, Product, LandedCostInvoiceItem,
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
            items_data=[{'product_id': self.product.id, 'quantity': 100, 'base_price_per_unit': 10, 'vat_rate': 0.14, 'withholding_tax_rate': 0.01}]
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
            items_data=[{'product_id': self.product.id, 'quantity': 50, 'base_price_per_unit': 20, 'vat_rate': 0, 'withholding_tax_rate': 0}]
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
            }]
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
        je = purchasing_service.post_supplier_invoice(invoice)
        invoice.refresh_from_db()

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

        # Assertions
        # Helper to get total amount for an account and entry type in the JE
        def get_total_for_account(account, entry_type):
            return je.lines.filter(account=account, entry_type=entry_type).aggregate(total=Sum('amount'))['total'] or Decimal('0.000')

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


    def test_landed_cost_workflow(self):
        """
        Tests the full 2-step landed cost workflow, allocating a single cost
        across TWO different receipts proportionally by value.
        """
        # Step 1: Create base data - two receipts for different products
        product2 = self.create_product("RM-PUR-02", "Second Raw Material", Product.ProductType.RAW_MATERIAL)
        po = purchasing_service.create_purchase_order(
            user=self.user,
            po_data={'po_number': 'PO-LC-WF', 'supplier_id': self.supplier.id, 'order_date': '2025-09-05'},
            items_data=[
                {'product_id': self.product.id, 'quantity': 200, 'base_price_per_unit': 100, 'vat_rate': 0, 'withholding_tax_rate': 0},
                {'product_id': product2.id, 'quantity': 50, 'base_price_per_unit': 300, 'vat_rate': 0, 'withholding_tax_rate': 0}
            ]
        )
        receipt1 = self.create_inventory_log(self.supplier, self.product, 200, 100, po.items.all()[0])
        receipt2 = self.create_inventory_log(self.supplier, product2, 50, 300, po.items.all()[1])
        
        initial_cost1 = receipt1.costing_unit_price
        initial_cost2 = receipt2.costing_unit_price
        landed_cost_amount = Decimal('1400.000')

        # Step 2: Post the Landed Cost Invoice
        lc_invoice = LandedCostInvoice.objects.create(
            vendor=self.vendor,
            invoice_number='LC-INV-01',
            invoice_date='2025-09-18',
            total_amount=landed_cost_amount
        )
        cost_type = LandedCostType.objects.create(name="Freight")
        LandedCostInvoiceItem.objects.create(
            landed_cost_invoice=lc_invoice,
            cost_type=cost_type,
            amount=landed_cost_amount
        )
        purchasing_service.post_landed_cost_invoice(lc_invoice)
        lc_invoice.refresh_from_db()
        self.assertEqual(lc_invoice.status, LandedCostInvoice.Status.AWAITING_ALLOCATION)
        
        post_je = lc_invoice.journal_entry
        self.assertTrue(post_je.is_balanced())
        self.assertEqual(
            post_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).account,
            self.general_settings.landed_costs_clearing_account
        )
        self.assertEqual(
            post_je.lines.get(entry_type=JournalEntryLine.EntryType.CREDIT).account,
            self.general_settings.accounts_payable
        )
        self.assertEqual(post_je.lines.get(entry_type=JournalEntryLine.EntryType.DEBIT).amount, landed_cost_amount)

        # Step 3: Allocate the cost across both receipts
        purchasing_service.allocate_landed_costs_from_invoice(
            landed_cost_invoice_ids=[lc_invoice.id],
            receipt_log_ids=[receipt1.id, receipt2.id],
            user=self.user
        )
        lc_invoice.refresh_from_db()
        self.assertEqual(lc_invoice.status, LandedCostInvoice.Status.FULLY_ALLOCATED)

        # Step 4: Verify the allocation and cost updates
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        # Calculate expected proportional allocation
        value1 = receipt1.base_unit_price * Decimal(str(receipt1.quantity)) # 200 * 100 = 20000
        value2 = receipt2.base_unit_price * Decimal(str(receipt2.quantity)) # 50 * 300 = 15000
        total_value = value1 + value2 # 35000
        
        expected_cost_alloc1 = (landed_cost_amount * (value1 / total_value)).quantize(Decimal('0.001')) # 1400 * (20/35) = 800
        expected_cost_alloc2 = (landed_cost_amount * (value2 / total_value)).quantize(Decimal('0.001')) # 1400 * (15/35) = 600
        
        cost_increase_per_unit1 = (expected_cost_alloc1 / Decimal(str(receipt1.quantity))).quantize(Decimal('0.001')) # 800 / 200 = 4
        cost_increase_per_unit2 = (expected_cost_alloc2 / Decimal(str(receipt2.quantity))).quantize(Decimal('0.001')) # 600 / 50 = 12

        self.assertEqual(receipt1.costing_unit_price, initial_cost1 + cost_increase_per_unit1)
        self.assertEqual(receipt2.costing_unit_price, initial_cost2 + cost_increase_per_unit2)
        self.assertEqual(receipt1.landed_cost_component, cost_increase_per_unit1)
        self.assertEqual(receipt2.landed_cost_component, cost_increase_per_unit2)

        # Verify the single, consolidated allocation JE
        alloc_record = LandedCostAllocation.objects.filter(receipt_log=receipt1).first()
        alloc_je = alloc_record.journal_entry
        self.assertTrue(alloc_je.is_balanced())
        self.assertEqual(alloc_je.lines.count(), 3) # 1 CR to Clearing, 2 DR to Inventory accounts

        # Check total credit to clearing
        self.assertEqual(
            alloc_je.lines.get(entry_type=JournalEntryLine.EntryType.CREDIT).amount,
            landed_cost_amount
        )
        product_content_type = ContentType.objects.get_for_model(Product)
        # Check debit to first inventory account
        debit1 = alloc_je.lines.get(
            account=self.get_product_type_setting(self.product.product_type).inventory_account,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_content_type=product_content_type,
            sub_ledger_object_id=self.product.id
        ).amount
        self.assertEqual(debit1, expected_cost_alloc1)

        # Check debit to second inventory account
        debit2 = alloc_je.lines.get(
            account=self.get_product_type_setting(product2.product_type).inventory_account,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_content_type=product_content_type,
            sub_ledger_object_id=product2.id
        ).amount
        self.assertEqual(debit2, expected_cost_alloc2)

        # Final check: The clearing account should be balanced
        clearing_balance = JournalEntryLine.objects.filter(
            account=self.general_settings.landed_costs_clearing_account
        ).aggregate(
            balance=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.DEBIT)) - Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.CREDIT))
        )['balance']
        self.assertEqual(clearing_balance, Decimal('0.000'))
