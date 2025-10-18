# gipcco_project/inventory/tests_sales.py

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .test_base import AccountingServiceBaseTestCase
from .models import (
    Payment, CustomerInvoice, CustomerInvoiceItem, FinishedProductDispatch, SalesOrder, SalesOrderItem, CustomerPaymentApplication, Customer,
    SalesReturn, SalesReturnItem, JournalEntry, InventoryAdjustment, CustomerCreditMemo, ProductTypeAccountingSettings, Product
)
from .services.sales_service import apply_payment_to_invoices, create_sales_order, dispatch_from_sales_order, create_invoice_from_dispatches
from .services import sales_return_service, ar_service

class SalesServiceTestCase(AccountingServiceBaseTestCase):
    """
    Test suite for the SalesService, focusing on the Order-to-Cash process.
    """
    def setUp(self):
        super().setUp()
        # Create a sales order and dispatch to have invoices to work with
        self.sales_order = SalesOrder.objects.create(
            customer=self.customer,
            order_date="2025-09-10",
            so_number="SO-TEST-001"
        )
        self.so_item = SalesOrderItem.objects.create(
            sales_order=self.sales_order,
            finished_product=self.receipt1,
            quantity_ordered=10,
            base_price_per_unit=Decimal("10.000"),
            vat_rate=Decimal("0.14")
        )
        self.dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=self.so_item,
            quantity=10,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 10, 0, 0)),
            cost_at_dispatch=Decimal("70.000") # Assuming a cost
        )

        # Create invoices
        self.invoice1 = CustomerInvoice.objects.create(
            customer=self.customer,
            invoice_number="INV-001",
            invoice_date="2025-09-12",
            due_date="2025-10-12",
            total_amount=Decimal("114.000"), # 10 * 10 * 1.14
            status=CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT
        )
        CustomerInvoiceItem.objects.create(invoice=self.invoice1, dispatch=self.dispatch, amount=self.invoice1.total_amount)

        self.invoice2 = CustomerInvoice.objects.create(
            customer=self.customer,
            invoice_number="INV-002",
            invoice_date="2025-09-13",
            due_date="2025-10-13",
            total_amount=Decimal("50.000"),
            status=CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT
        )
        
        self.payment = Payment.objects.create(
            payment_date="2025-09-20",
            amount=Decimal("164.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_IN,
            description="Payment from Test Customer",
            customer=self.customer
        )

    def test_create_sales_order_success(self):
        """
        Test successful creation of a sales order with valid data.
        """
        items = [
            {
                'finished_product_receipt_id': self.receipt1.id,
                'quantity_ordered': 5.0,
                'base_price_per_unit': Decimal('10.000'),
                'vat_rate': Decimal('0.14')
            },
            {
                'finished_product_receipt_id': self.receipt2.id,
                'quantity_ordered': 10.0,
                'base_price_per_unit': Decimal('11.000'),
                'vat_rate': Decimal('0.14')
            }
        ]
        
        so = create_sales_order(
            customer_id=self.customer.id,
            order_date="2025-09-25",
            so_number="SO-TEST-002",
            items=items
        )
        
        self.assertIsNotNone(so)
        self.assertEqual(so.so_number, "SO-TEST-002")
        self.assertEqual(so.items.count(), 2)
        self.assertEqual(SalesOrder.objects.count(), 2) # Including the one from setUp
        
        so_item1 = so.items.get(finished_product=self.receipt1)
        self.assertEqual(so_item1.quantity_ordered, 5.0)

    def test_create_sales_order_fail_invalid_customer(self):
        """
        Test that sales order creation fails with a non-existent customer ID.
        """
        items = [{'finished_product_receipt_id': self.receipt1.id, 'quantity_ordered': 1.0, 'base_price_per_unit': 1, 'vat_rate': 0}]
        
        with self.assertRaises(ValidationError) as e:
            create_sales_order(
                customer_id=9999,
                order_date="2025-09-25",
                so_number="SO-FAIL-001",
                items=items
            )
        self.assertIn("Customer with ID 9999 not found", str(e.exception))

    def test_create_sales_order_fail_invalid_product(self):
        """
        Test that sales order creation fails if any finished product receipt ID is invalid.
        """
        items = [
            {'finished_product_receipt_id': self.receipt1.id, 'quantity_ordered': 5.0, 'base_price_per_unit': 10, 'vat_rate': 0.14},
            {'finished_product_receipt_id': 9999, 'quantity_ordered': 10.0, 'base_price_per_unit': 11, 'vat_rate': 0.14}
        ]
        
        with self.assertRaises(ValidationError) as e:
            create_sales_order(
                customer_id=self.customer.id,
                order_date="2025-09-25",
                so_number="SO-FAIL-002",
                items=items
            )
        self.assertIn("finished product batches could not be found", str(e.exception))

    def test_dispatch_from_sales_order_success(self):
        """
        Test successful dispatch of items from a sales order.
        """
        self.assertEqual(FinishedProductDispatch.objects.count(), 1) # From setUp
        
        dispatches_data = [
            {'sales_order_item_id': self.so_item.id, 'quantity': 3.0}
        ]
        
        dispatch_date = timezone.make_aware(timezone.datetime(2025, 9, 26, 14, 0, 0))
        
        new_dispatches = dispatch_from_sales_order(
            sales_order_id=self.sales_order.id,
            dispatch_date=dispatch_date,
            dispatches=dispatches_data
        )
        
        self.assertEqual(len(new_dispatches), 1)
        self.assertEqual(FinishedProductDispatch.objects.count(), 2)
        
        new_dispatch = new_dispatches[0]
        self.assertEqual(new_dispatch.quantity, 3.0)
        self.assertTrue(new_dispatch.cost_at_dispatch > 0) # Cost should be calculated

    def test_dispatch_fail_invalid_so(self):
        """
        Test dispatch failure with a non-existent sales order ID.
        """
        with self.assertRaises(ValidationError) as e:
            dispatch_from_sales_order(
                sales_order_id=9999,
                dispatch_date=timezone.now(),
                dispatches=[{'sales_order_item_id': self.so_item.id, 'quantity': 1.0}]
            )
        self.assertIn("Sales Order with ID 9999 not found", str(e.exception))

    def test_dispatch_fail_invalid_so_item(self):
        """
        Test dispatch failure with a sales order item not on the specified order.
        """
        # Create another SO to get a valid but incorrect SO item ID
        other_so = SalesOrder.objects.create(customer=self.customer, order_date="2025-09-25", so_number="SO-OTHER")
        other_so_item = SalesOrderItem.objects.create(
            sales_order=other_so,
            finished_product=self.receipt2,
            quantity_ordered=1,
            base_price_per_unit=Decimal("10.000")
        )

        with self.assertRaises(ValidationError) as e:
            dispatch_from_sales_order(
                sales_order_id=self.sales_order.id,
                dispatch_date=timezone.now(),
                dispatches=[{'sales_order_item_id': other_so_item.id, 'quantity': 1.0}]
            )
        self.assertIn("sales order items could not be found", str(e.exception))

    def test_create_invoice_from_dispatches_success(self):
        """
        Test successful creation of an invoice from dispatch records.
        """
        # Create a new dispatch that is not yet invoiced
        new_dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=self.so_item,
            quantity=5,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 12, 10, 0, 0)),
            cost_at_dispatch=Decimal("35.000")
        )

        self.assertEqual(CustomerInvoice.objects.count(), 2) # From setUp
        
        invoice = create_invoice_from_dispatches(
            customer_id=self.customer.id,
            invoice_number="INV-TEST-003",
            invoice_date="2025-09-27",
            due_date="2025-10-27",
            dispatch_ids=[new_dispatch.id]
        )
        
        self.assertIsNotNone(invoice)
        self.assertEqual(CustomerInvoice.objects.count(), 3)
        self.assertEqual(invoice.items.count(), 1)
        expected_amount = (Decimal('5') * self.so_item.base_price_per_unit) * (Decimal('1') + self.so_item.vat_rate)
        self.assertEqual(invoice.total_amount, expected_amount.quantize(Decimal('0.001')))

    def test_create_invoice_fail_dispatch_invoiced(self):
        """
        Test that creating an invoice fails if a dispatch is already invoiced.
        """
        # self.dispatch is already part of self.invoice1 from setUp
        with self.assertRaises(ValidationError) as e:
            create_invoice_from_dispatches(
                customer_id=self.customer.id,
                invoice_number="INV-FAIL-001",
                invoice_date="2025-09-27",
                due_date="2025-10-27",
                dispatch_ids=[self.dispatch.id]
            )
        self.assertIn("has already been included in an invoice", str(e.exception))

    def test_create_invoice_fail_wrong_customer(self):
        """
        Test that creating an invoice fails if dispatches belong to another customer.
        """
        other_customer = Customer.objects.create(name="Other Customer")
        new_dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=self.so_item,
            quantity=1,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 13, 10, 0, 0)),
            cost_at_dispatch=Decimal("7.000")
        )
        with self.assertRaises(ValidationError) as e:
            create_invoice_from_dispatches(
                customer_id=other_customer.id,
                invoice_number="INV-FAIL-002",
                invoice_date="2025-09-27",
                due_date="2025-10-27",
                dispatch_ids=[new_dispatch.id]
            )
        self.assertIn("belongs to a different customer", str(e.exception))

    def test_apply_payment_full_single_invoice(self):
        """
        Test applying a payment that fully covers a single invoice.
        """
        self.assertEqual(self.invoice1.status, CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT)
        
        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("114.000")}
        ]
        
        apply_payment_to_invoices(self.payment, applications)
        
        self.invoice1.refresh_from_db()
        self.assertEqual(self.invoice1.amount_paid, Decimal("114.000"))
        self.assertEqual(self.invoice1.balance_due, Decimal("0.000"))
        self.assertEqual(self.invoice1.status, CustomerInvoice.InvoiceStatus.PAID)
        
        self.assertTrue(CustomerPaymentApplication.objects.filter(payment=self.payment, invoice=self.invoice1).exists())

    def test_apply_payment_partial_single_invoice(self):
        """
        Test applying a payment that partially covers a single invoice.
        """
        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("50.000")}
        ]
        
        apply_payment_to_invoices(self.payment, applications)
        
        self.invoice1.refresh_from_db()
        self.assertEqual(self.invoice1.amount_paid, Decimal("50.000"))
        self.assertEqual(self.invoice1.balance_due, Decimal("64.000"))
        self.assertEqual(self.invoice1.status, CustomerInvoice.InvoiceStatus.PARTIALLY_PAID)

    def test_apply_payment_multiple_invoices(self):
        """
        Test applying a single payment across multiple invoices.
        """
        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("114.000")},
            {'invoice_id': self.invoice2.id, 'amount_to_apply': Decimal("30.000")}
        ]
        
        apply_payment_to_invoices(self.payment, applications)
        
        self.invoice1.refresh_from_db()
        self.invoice2.refresh_from_db()
        
        self.assertEqual(self.invoice1.status, CustomerInvoice.InvoiceStatus.PAID)
        self.assertEqual(self.invoice2.status, CustomerInvoice.InvoiceStatus.PARTIALLY_PAID)
        self.assertEqual(self.invoice2.amount_paid, Decimal("30.000"))
        self.assertEqual(self.invoice2.balance_due, Decimal("20.000"))
        
        self.assertEqual(CustomerPaymentApplication.objects.filter(payment=self.payment).count(), 2)

    def test_fail_overapply_payment_total(self):
        """
        Test that applying more than the payment's unapplied amount fails.
        """
        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("114.000")},
            {'invoice_id': self.invoice2.id, 'amount_to_apply': Decimal("100.000")} # Total 214 > 164
        ]
        
        with self.assertRaises(ValidationError) as e:
            apply_payment_to_invoices(self.payment, applications)
        self.assertIn("exceeds the unapplied amount of the payment", str(e.exception))

    def test_fail_overapply_single_invoice(self):
        """
        Test that applying more than an invoice's balance due fails.
        """
        applications = [
            {'invoice_id': self.invoice2.id, 'amount_to_apply': Decimal("50.001")}
        ]
        
        with self.assertRaises(ValidationError) as e:
            apply_payment_to_invoices(self.payment, applications)
        self.assertIn("exceeds its balance due", str(e.exception))

    def test_fail_with_invalid_invoice_id(self):
        """
        Test that the process fails if a non-existent invoice ID is provided.
        """
        applications = [
            {'invoice_id': 99999, 'amount_to_apply': Decimal("10.000")}
        ]
        
        with self.assertRaises(ValidationError) as e:
            apply_payment_to_invoices(self.payment, applications)
        self.assertIn("invoices could not be found", str(e.exception))

    def test_fail_with_wrong_payment_type(self):
        """
        Test that using an outgoing payment fails validation.
        """
        outgoing_payment = Payment.objects.create(
            payment_date="2025-09-21",
            amount=Decimal("100.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Payment to supplier",
            supplier=self.supplier
        )
        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("10.000")}
        ]
        
        with self.assertRaises(ValidationError) as e:
            apply_payment_to_invoices(outgoing_payment, applications)
        self.assertIn("not an incoming customer payment", str(e.exception))

    def test_transactionality_on_failure(self):
        """
        Test that if one application fails, none of the changes are committed.
        """
        self.assertEqual(self.invoice1.amount_paid, Decimal("0.000"))
        self.assertEqual(self.invoice2.amount_paid, Decimal("0.000"))

        applications = [
            {'invoice_id': self.invoice1.id, 'amount_to_apply': Decimal("10.000")}, # Valid
            {'invoice_id': self.invoice2.id, 'amount_to_apply': Decimal("50.001")}  # Invalid
        ]
        
        with self.assertRaises(ValidationError):
            apply_payment_to_invoices(self.payment, applications)
            
        self.invoice1.refresh_from_db()
        self.invoice2.refresh_from_db()
        
        # Assert that no changes were saved
        self.assertEqual(self.invoice1.amount_paid, Decimal("0.000"))
        self.assertEqual(self.invoice2.amount_paid, Decimal("0.000"))
        self.assertFalse(CustomerPaymentApplication.objects.exists())

class SalesReturnServiceTestCase(AccountingServiceBaseTestCase):
    """
    Test suite for the sales return and credit memo workflow.
    """
    def setUp(self):
        super().setUp()
        # Setup a dispatched item to be returned
        self.sales_order = SalesOrder.objects.create(
            customer=self.customer, order_date="2025-09-10", so_number="SO-RETURN-001"
        )
        self.so_item = SalesOrderItem.objects.create(
            sales_order=self.sales_order,
            finished_product=self.receipt1,
            quantity_ordered=10,
            base_price_per_unit=Decimal("100.000"),
            vat_rate=Decimal("0.14")
        )
        self.dispatch_to_return = FinishedProductDispatch.objects.create(
            sales_order_item=self.so_item,
            quantity=8,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 10, 0, 0)),
            cost_at_dispatch=Decimal("80.000") # 8 units @ cost of 10.00
        )
        # This dispatch creates a JE (COGS Dr, FG Cr)
        JournalEntry.objects.all().delete() # Clear JEs for clean test

    def test_full_sales_return_workflow(self):
        """
        Tests the complete, multi-step sales return workflow:
        1. A SalesReturn is created.
        2. The return is "inspected" and dispositions are set.
        3. The inspected return is processed via the service.
        4. A credit memo is created from the return.
        5. All resulting journal entries are validated.
        """
        # 1. Arrange: Create a SalesReturn with two items, one to be stocked, one to be scrapped.
        sales_return = SalesReturn.objects.create(
            customer=self.customer,
            return_date="2025-09-20",
            sales_order=self.sales_order,
            status=SalesReturn.Status.PENDING_INSPECTION
        )
        SalesReturnItem.objects.create(
            sales_return=sales_return,
            original_dispatch=self.dispatch_to_return,
            quantity_returned=6.0, # 6 units good
            disposition=SalesReturnItem.Disposition.RETURN_TO_STOCK
        )
        SalesReturnItem.objects.create(
            sales_return=sales_return,
            original_dispatch=self.dispatch_to_return,
            quantity_returned=2.0, # 2 units scrap
            disposition=SalesReturnItem.Disposition.SCRAP
        )
        sales_return.status = SalesReturn.Status.PENDING_PROCESSING
        sales_return.save()

        # 2. Act I: Process the inspected return (handles inventory/COGS side)
        sales_return_service.process_inspected_return(sales_return)

        # 3. Assert I: Verify the inventory-side transactions
        sales_return.refresh_from_db()
        self.assertEqual(sales_return.status, SalesReturn.Status.COMPLETED)

        # a) Verify the consolidated COGS Reversal Journal Entry
        self.assertIsNotNone(sales_return.cogs_reversal_journal_entry)
        cogs_je = sales_return.cogs_reversal_journal_entry
        self.assertEqual(cogs_je.lines.count(), 2)
        
        # DEBIT: Sales Returns Clearing Account (for the total cost of 8 units)
        debit_line = cogs_je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.general_settings.sales_returns_clearing_account)
        self.assertEqual(debit_line.amount, Decimal("80.000")) # 8 units @ cost 10

        # CREDIT: COGS Account
        credit_line = cogs_je.lines.get(entry_type='credit')
        cogs_account = self.get_product_type_setting(Product.ProductType.FINAL_PRODUCT).cogs_or_expense_account
        self.assertEqual(credit_line.account, cogs_account)
        self.assertEqual(credit_line.amount, Decimal("80.000"))

        # b) Verify the Inventory Adjustments and their JEs
        self.assertEqual(InventoryAdjustment.objects.count(), 2)
        
        # Adjustment for the 6 good items returned to stock
        adj_good = InventoryAdjustment.objects.get(adjustment_quantity__gt=0)
        self.assertEqual(adj_good.adjustment_quantity, 6.0)
        self.assertEqual(adj_good.reason_code, InventoryAdjustment.ReasonCode.SALES_RETURN_STOCK)
        
        adj_good_je = JournalEntry.objects.get(object_id=adj_good.id, content_type=ContentType.objects.get_for_model(adj_good))
        # DEBIT: Finished Goods Inventory (value comes back)
        # CREDIT: Sales Returns Clearing Account
        self.assertEqual(adj_good_je.lines.get(entry_type='debit').account, self.general_settings.finished_goods_inventory)
        self.assertEqual(adj_good_je.lines.get(entry_type='debit').amount, Decimal("60.000"))
        self.assertEqual(adj_good_je.lines.get(entry_type='credit').account, self.general_settings.sales_returns_clearing_account)
        self.assertEqual(adj_good_je.lines.get(entry_type='credit').amount, Decimal("60.000"))

        # Adjustment for the 2 scrapped items
        adj_scrap = InventoryAdjustment.objects.get(adjustment_quantity__lt=0)
        self.assertEqual(adj_scrap.adjustment_quantity, -2.0)
        self.assertEqual(adj_scrap.reason_code, InventoryAdjustment.ReasonCode.DAMAGE)

        adj_scrap_je = JournalEntry.objects.get(object_id=adj_scrap.id, content_type=ContentType.objects.get_for_model(adj_scrap))
        # DEBIT: Damaged Goods Expense
        # CREDIT: Sales Returns Clearing Account
        self.assertEqual(adj_scrap_je.lines.get(entry_type='debit').account, self.general_settings.damaged_goods_expense_account)
        self.assertEqual(adj_scrap_je.lines.get(entry_type='debit').amount, Decimal("20.000"))
        self.assertEqual(adj_scrap_je.lines.get(entry_type='credit').account, self.general_settings.sales_returns_clearing_account)
        self.assertEqual(adj_scrap_je.lines.get(entry_type='credit').amount, Decimal("20.000"))


        # 4. Act II: Create the credit memo (handles financial/AR side)
        credit_memo = sales_return_service.create_credit_memo_from_return(
            sales_return=sales_return,
            memo_number="CM-TEST-001",
            memo_date="2025-09-21"
        )

        # 5. Assert II: Verify the financial-side transactions
        self.assertIsNotNone(credit_memo)
        self.assertEqual(CustomerCreditMemo.objects.count(), 1)
        
        # The post_save signal on CustomerCreditMemo creates the JE
        cm_je = JournalEntry.objects.get(object_id=credit_memo.id, content_type=ContentType.objects.get_for_model(credit_memo))
        self.assertIsNotNone(cm_je)
        self.assertEqual(cm_je.lines.count(), 3)

        # Total returned value: 8 units * 100 base price = 800
        # Total VAT: 800 * 0.14 = 112
        # Total Credit: 912
        self.assertEqual(credit_memo.total_amount, Decimal("912.000"))

        # DEBIT: Sales Returns & Allowances (contra-revenue)
        self.assertEqual(cm_je.lines.get(account=self.general_settings.sales_returns_account).amount, Decimal("800.000"))
        # DEBIT: VAT Payable (reversing liability)
        self.assertEqual(cm_je.lines.get(account=self.general_settings.vat_payable).amount, Decimal("112.000"))
        # CREDIT: Accounts Receivable (reducing customer balance)
        self.assertEqual(cm_je.lines.get(account=self.general_settings.accounts_receivable).amount, Decimal("912.000"))



