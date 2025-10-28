# gipcco_project/inventory/tests_accounting.py

from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone
from django.db.models import Sum
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied

# Import the base test case and models from the new base file
from .test_base import AccountingServiceBaseTestCase
from .models import (
    FinancialPeriod, InventoryLog, JournalEntry, JournalEntryLine, Batch, BatchItem, FinishedProductReceipt,
    SalesOrder, SalesOrderItem, FinishedProductDispatch, Payment,
    InventoryAdjustment, InventoryCount, InventoryConsumption, ProductionReturn,
    ExpenseLog, OverheadAllocationRun, TransactionCorrection, Account, ShopOrderTemplate,
    OpeningBalanceEntry, OpeningBalanceEntryLine, OpeningBalanceSubLedgerDetail, Product, FiscalYear, PrepaidExpense
)
from .services import overhead_service, accounting_service
from .services.accounting_service import (
    create_je_for_inventory_receipt,
    create_je_for_production_consumption,
    create_je_for_finished_goods_receipt,
    create_reversing_je_for_correction,
    _get_product_inventory_account
)


class TestAccountingService(AccountingServiceBaseTestCase):
    """
    Test suite for functions in `accounting_service.py`.
    Inherits the scalable setup from AccountingServiceBaseTestCase.
    """

    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_create_je_for_inventory_receipt_success(self):
        """
        Verify that receiving a raw material creates a correct and balanced journal entry
        by triggering the post_save signal.
        """
        # 1. Arrange: Define the data for the inventory log
        log_data = {
            "product": self.raw_material,
            "company": self.supplier,
            "quantity": 100.0,
            "timestamp": timezone.now(),
            "release_timestamp": timezone.make_aware(timezone.datetime(2025, 9, 15, 10, 0, 0)),
            "status": InventoryLog.Status.RELEASED,
            "qc_no": "QC-TEST-001",
            "base_unit_price": Decimal("10.000"),
            "vat_amount": Decimal("140.000"),
            "vat_treatment": InventoryLog.VatTreatment.RECOVERABLE,
            "withholding_tax_amount": Decimal("10.000")
        }

        # 2. Act: Create the InventoryLog, which triggers the post_save signal
        log = InventoryLog.objects.create(**log_data)

        # 3. Assert: Verify the journal entry was created by the signal
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je, "Journal entry should be created by the signal.")
        
        self.assertEqual(je.lines.count(), 4, "Should have 4 lines: Inv, VAT, AP, WHT")
        self.assertEqual(je.status, JournalEntry.Status.POSTED)
        self.assertEqual(je.source_object, log)

        # Verify amounts and accounts
        total_base = Decimal("1000.000")
        costing_value = log.costing_unit_price * Decimal(log.quantity)
        self.assertEqual(costing_value, total_base)

        debits = {line.account.code: line.amount for line in je.lines.filter(entry_type='debit')}
        credits = {line.account.code: line.amount for line in je.lines.filter(entry_type='credit')}

        # Check debits
        self.assertIn(self.accounts['1020201'].code, debits)
        self.assertEqual(debits[self.accounts['1020201'].code], total_base)
        self.assertIn(self.accounts['1020404'].code, debits)
        self.assertEqual(debits[self.accounts['1020404'].code], Decimal("140.000"))

        # Check credits
        self.assertIn(self.accounts['20201'].code, credits)
        self.assertEqual(credits[self.accounts['20201'].code], Decimal("1130.000"))
        self.assertIn(self.accounts['2020202'].code, credits)
        self.assertEqual(credits[self.accounts['2020202'].code], Decimal("10.000"))

        # Verify the entry is balanced
        total_debits = sum(debits.values())
        total_credits = sum(credits.values())
        self.assertEqual(total_debits, total_credits)
        self.assertEqual(total_debits, Decimal("1140.000"))

        # --- NEW: Verify Sub-Ledger Links ---
        inv_line = je.lines.get(account=self.accounts['1020201'])
        ap_line = je.lines.get(account=self.accounts['20201'])
        self.assertEqual(inv_line.sub_ledger_object, self.raw_material)
        self.assertEqual(ap_line.sub_ledger_object, self.supplier)

    def test_create_je_for_inventory_receipt_not_released(self):
        """
        Verify that a JE is NOT created if the inventory log is not 'RELEASED'.
        """
        # 1. Arrange: Create a quarantined inventory log
        log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=50.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.QUARANTINED, # Not released
            base_unit_price=Decimal("10.000")
        )

        # 2. Act: Call the service function
        je = create_je_for_inventory_receipt(log)

        # 3. Assert: Verify no journal entry was created
        self.assertIsNone(je, "Journal entry should not be created for non-released logs.")
        self.assertEqual(JournalEntry.objects.count(), 0)

    def test_create_je_for_inventory_receipt_duplicate_prevention(self):
        """
        Verify that the service does not create a duplicate journal entry for the same log.
        This test now checks the signal's behavior.
        """
        # 1. Arrange: Create a log, which will automatically create one JE via the signal.
        log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=10.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 15, 11, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("5.000")
        )
        self.assertEqual(JournalEntry.objects.count(), 1, "Signal should have created one JE.")

        # 2. Act: Call the service function directly. It should recognize the existing JE and do nothing.
        je = create_je_for_inventory_receipt(log)

        # 3. Assert: Verify no new journal entry was created
        self.assertIsNone(je, "Service should return None for duplicates.")
        self.assertEqual(JournalEntry.objects.count(), 1, "No new journal entry should be created.")

    def test_create_je_for_inventory_receipt_period_closed(self):
        """
        Verify that if the financial period is closed, creating a log raises a PermissionError.
        """
        # 1. Arrange: Close the financial period
        self.period.status = FinancialPeriod.Status.CLOSED
        self.period.save()

        log_data = {
            "product": self.raw_material,
            "company": self.supplier,
            "quantity": 10.0,
            "timestamp": timezone.now(),
            "release_timestamp": timezone.make_aware(timezone.datetime(2025, 9, 15, 12, 0, 0)),
            "status": InventoryLog.Status.RELEASED,
            "base_unit_price": Decimal("10.000")
        }

        # 2. Act & Assert: Attempt to create a log and expect a PermissionDenied error
        with self.assertRaises(PermissionDenied) as context:
            InventoryLog.objects.create(**log_data)
        
        self.assertIn("period 'September 2025' for date 2025-09-15 is Closed", str(context.exception))
        self.assertEqual(JournalEntry.objects.count(), 0, "No JE should be created when the period is closed.")


    def test_create_je_for_production_consumption_success(self):
        """
        Verify that creating a Batch correctly creates a JE to move value
        from Raw Material Inventory to WIP Inventory.
        """
        # 1. Arrange: Create a batch with items to consume
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-TEST-001",
            batch_number="B-TEST-001",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 16, 9, 0, 0)),
        )
        # Create two items to consume from the same material but with different costs
        BatchItem.objects.create(
            batch=batch,
            primitive_product=self.raw_material,
            theoretical_quantity=20.0, # --- FIX: Added missing field ---
            actual_quantity=20.0,
            cost_at_consumption=Decimal("10.000") # From the first receipt
        )
        BatchItem.objects.create(
            batch=batch,
            primitive_product=self.raw_material,
            theoretical_quantity=5.0, # --- FIX: Added missing field ---
            actual_quantity=5.0,
            cost_at_consumption=Decimal("12.000") # A second, more expensive receipt
        )

        # 2. Act: The initial save triggers the signal, but with no items.
        # We must save the batch *again* after adding items to trigger the signal
        # with the complete data, simulating an update.
        batch.save()
        
        # 3. Assert: Verify the journal entry
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, batch)
        self.assertEqual(je.lines.count(), 2, "Should have 2 lines: one debit to WIP, one credit to RM Inv")

        # Calculate expected total cost
        expected_total_cost = (Decimal("20.0") * Decimal("10.000")) + (Decimal("5.0") * Decimal("12.000"))
        self.assertEqual(expected_total_cost, Decimal("260.000"))

        # Verify the debit to WIP
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['1020205']) # WIP Account
        self.assertEqual(debit_line.amount, expected_total_cost)

        # Verify the credit to Raw Materials Inventory
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020201']) # RM Inventory Account
        self.assertEqual(credit_line.amount, expected_total_cost)

        # --- NEW: Verify Sub-Ledger Links ---
        self.assertEqual(debit_line.sub_ledger_object, self.final_product)
        self.assertEqual(credit_line.sub_ledger_object, self.raw_material)

    def test_create_je_for_finished_goods_receipt_success(self):
        """
        Verify that creating a FinishedProductReceipt correctly moves value
        from WIP Inventory to Finished Goods Inventory.
        """
        # 1. Arrange: Create a batch and a receipt for it
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-TEST-002",
            batch_number="B-TEST-002",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 17, 9, 0, 0)),
        )
        receipt = FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-TEST-001",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 18, 14, 0, 0)),
            total_cost=Decimal("500.000"), # This is the value coming from WIP
            total_quantity_produced=1000.0
        )

        # 2. Act: The post_save signal on FinishedProductReceipt should have created the JE.

        # 3. Assert: Verify the journal entry
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, receipt)
        self.assertEqual(je.lines.count(), 2, "Should have one debit and one credit line.")

        # Verify the debit to Finished Goods Inventory
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['1020206']) # FG Inventory Account
        self.assertEqual(debit_line.amount, Decimal("500.000"))

        # Verify the credit to WIP Inventory
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020205']) # WIP Account
        self.assertEqual(credit_line.amount, Decimal("500.000"))

        # --- NEW: Verify Sub-Ledger Links ---
        self.assertEqual(debit_line.sub_ledger_object, self.final_product)
        self.assertEqual(credit_line.sub_ledger_object, self.final_product)

    def test_create_je_for_sales_dispatch_success(self):
        """
        Verify that dispatching a finished good creates a compound journal entry
        for both COGS and Revenue.
        """
        # 1. Arrange
        # a) Create stock to sell. This will create one JE for the receipt.
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-SALE-001",
            batch_number="B-SALE-001",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 19, 9, 0, 0)),
        )
        receipt = FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-SALE-001",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 20, 14, 0, 0)),
            total_cost=Decimal("5000.000"),  # 100 units @ cost of 50.00 each
            total_quantity_produced=100.0
        )

        # b) Create the sales order and item
        so = SalesOrder.objects.create(
            customer=self.customer,
            order_date=timezone.make_aware(timezone.datetime(2025, 9, 21, 10, 0, 0)),
            so_number="SO-TEST-SALE-001"
        )
        so_item = SalesOrderItem.objects.create(
            sales_order=so,
            finished_product=receipt,
            quantity_ordered=10.0,
            base_price_per_unit=Decimal("80.000"),  # Selling price
            vat_rate=Decimal("0.14")
        )

        # c) Create the dispatch, which triggers the signal to create the second JE
        dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=so_item,
            quantity=10.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 22, 11, 0, 0)),
            cost_at_dispatch=Decimal("500.000")  # 10 units * cost of 50.00
        )

        # 2. Act: The post_save signal on FinishedProductDispatch has already fired.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 2, "Should be 2 JEs: 1 for receipt, 1 for dispatch")
        je = JournalEntry.objects.latest('date')  # The dispatch JE is the most recent one
        self.assertEqual(je.source_object, dispatch)
        self.assertEqual(je.lines.count(), 5, "Should have 5 lines: COGS, FG Inv, AR, Sales, VAT")

        # Verify amounts
        cogs_amount = Decimal("500.000")
        base_revenue = Decimal("800.000")  # 10 * 80
        vat_amount = Decimal("112.000")  # 800 * 0.14
        total_receivable = base_revenue + vat_amount

        debits = {line.account.code: line.amount for line in je.lines.filter(entry_type='debit')}
        credits = {line.account.code: line.amount for line in je.lines.filter(entry_type='credit')}

        # Check debits
        self.assertEqual(len(debits), 2)
        self.assertIn(self.accounts['50101'].code, debits)  # COGS Account
        self.assertEqual(debits[self.accounts['50101'].code], cogs_amount)
        self.assertIn(self.accounts['10203'].code, debits)  # A/R Account
        self.assertEqual(debits[self.accounts['10203'].code], total_receivable)

        # Check credits
        self.assertEqual(len(credits), 3)
        self.assertIn(self.accounts['1020206'].code, credits)  # FG Inventory Account
        self.assertEqual(credits[self.accounts['1020206'].code], cogs_amount)
        self.assertIn(self.accounts['40101'].code, credits)  # Sales Revenue Account
        self.assertEqual(credits[self.accounts['40101'].code], base_revenue)
        self.assertIn(self.accounts['2020201'].code, credits)  # VAT Payable Account
        self.assertEqual(credits[self.accounts['2020201'].code], vat_amount)

        # Verify the entry is balanced
        self.assertEqual(sum(debits.values()), sum(credits.values()))

        # --- NEW: Verify Sub-Ledger Links ---
        cogs_debit_line = je.lines.get(account=self.accounts['50101'], entry_type='debit')
        fg_credit_line = je.lines.get(account=self.accounts['1020206'], entry_type='credit')
        ar_debit_line = je.lines.get(account=self.accounts['10203'], entry_type='debit')
        rev_credit_line = je.lines.get(account=self.accounts['40101'], entry_type='credit')

        self.assertEqual(cogs_debit_line.sub_ledger_object, self.final_product)
        self.assertEqual(fg_credit_line.sub_ledger_object, self.final_product)
        self.assertEqual(ar_debit_line.sub_ledger_object, self.customer)
        self.assertEqual(rev_credit_line.sub_ledger_object, self.final_product)


class TestPaymentAccounting(AccountingServiceBaseTestCase):
    """
    Test suite specifically for payment-related journal entries.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_create_je_for_supplier_payment_success(self):
        """
        Verify that a payment to a supplier correctly debits A/P and credits the bank account.
        """
        # 1. Arrange
        payment = Payment.objects.create(
            payment_date=timezone.make_aware(timezone.datetime(2025, 9, 25, 10, 0, 0)),
            amount=Decimal("1130.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Payment for Invoice INV-001",
            supplier=self.supplier
        )

        # 2. Act: The post_save signal on Payment should have created the JE.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, payment)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to Accounts Payable
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.general_settings.accounts_payable)
        self.assertEqual(debit_line.sub_ledger_object, self.supplier)
        
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.amount, payment.amount)
        # --- FIX: Assert against the GL account, not the BankAccount object itself ---
        self.assertEqual(credit_line.account, self.bank_account.gl_account)
        # --- FIX: Assert the sub-ledger is the BankAccount instance ---
        self.assertEqual(credit_line.sub_ledger_object, self.bank_account)

    def test_create_je_for_customer_payment_success(self):
        """
        Verify that an on-account payment from a customer correctly debits the bank
        and credits the Customer Deposits liability account.
        """
        # 1. Arrange
        payment = Payment.objects.create(
            payment_date=timezone.make_aware(timezone.datetime(2025, 9, 26, 11, 0, 0)),
            amount=Decimal("912.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_IN,
            description="Payment for Sales Order SO-TEST-SALE-001",
            customer=self.customer
        )

        # 2. Act: The post_save signal on Payment should have created the JE.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, payment)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to the Bank GL Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.bank_account.gl_account)
        self.assertEqual(debit_line.amount, Decimal("912.000"))

        # Verify the credit to Customer Deposits for an on-account payment
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['20203']) # Customer Deposits Account
        self.assertEqual(credit_line.amount, Decimal("912.000"))

        # --- NEW: Verify Sub-Ledger Links ---
        # --- FIX: Assert the sub-ledger is the BankAccount instance, not its GL account ---
        self.assertEqual(debit_line.sub_ledger_object, self.bank_account)
        self.assertEqual(credit_line.sub_ledger_object, self.customer)


class TestMiscAccountingTransactions(AccountingServiceBaseTestCase):
    """
    Test suite for various other accounting transactions like internal
    consumption and production returns.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_create_je_for_internal_consumption_success(self):
        """
        Verify that internally consuming an MRO item correctly debits an
        expense account and credits the MRO inventory account.
        """
        # 1. Arrange
        # a) Create stock for the MRO product. This creates JE #1.
        mro_log = InventoryLog.objects.create(
            product=self.mro_product,
            company=self.supplier,
            quantity=10.0,
            timestamp=timezone.now(), # FIX: Added missing required field
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 10, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("100.000")
        )

        # b) Create the consumption record. This triggers the signal for JE #2.
        consumption = InventoryConsumption.objects.create(
            product=self.mro_product,
            source_log=mro_log,
            quantity_consumed=2.0,
            consumption_date=timezone.make_aware(timezone.datetime(2025, 9, 29, 14, 0, 0)),
            department=InventoryConsumption.Department.ENGINEERING,
            cost_at_consumption=Decimal("200.000") # 2 cans * 100.000/can
        )

        # 2. Act: The post_save signal on InventoryConsumption has already fired.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for consumption
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, consumption)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to the MRO Expense Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['50201']) # Maintenance Expense
        self.assertEqual(debit_line.amount, Decimal("200.000"))

        # Verify the credit to the MRO Inventory Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020207']) # MRO Inventory
        self.assertEqual(credit_line.amount, Decimal("200.000"))

        # --- NEW: Verify Sub-Ledger Links ---
        self.assertEqual(credit_line.sub_ledger_object, self.mro_product)
        # Expense line has no sub-ledger in this case
        self.assertIsNone(debit_line.sub_ledger_object)

    def test_create_je_for_amortizable_consumption_success(self):
        """
        Verify that consuming an amortizable MRO item correctly creates a
        PrepaidExpense asset and a JE that debits the Prepaid a/c.
        """
        # 1. Arrange
        # a) Create stock for the amortizable product. This creates JE #1.
        amortizable_log = InventoryLog.objects.create(
            product=self.amortizable_product,
            company=self.supplier,
            quantity=1.0,
             timestamp=timezone.now(),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 10, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("1200.000")
        )

        # b) Create the consumption record. The pre_save signal should set its
        #    type to AMORTIZE, and the post_save signal should create a
        #    PrepaidExpense and the corresponding JE.
        consumption = InventoryConsumption.objects.create(
            product=self.amortizable_product,
            source_log=amortizable_log,
            quantity_consumed=1.0,
            consumption_date=timezone.make_aware(timezone.datetime(2025, 9, 29, 14, 0, 0)),
            department=InventoryConsumption.Department.ENGINEERING,
            cost_at_consumption=Decimal("1200.000")
        )

        # 2. Act: The signals have already fired.

        # 3. Assert
        # a) Verify the consumption type was set correctly
        self.assertEqual(consumption.consumption_type, InventoryConsumption.ConsumptionType.AMORTIZE)

        # b) Verify the PrepaidExpense object was created
        ct = ContentType.objects.get_for_model(consumption)
        self.assertTrue(PrepaidExpense.objects.filter(source_content_type=ct, source_object_id=consumption.id).exists())
        prepaid_asset = PrepaidExpense.objects.get(source_content_type=ct, source_object_id=consumption.id)
        self.assertEqual(prepaid_asset.initial_amount, Decimal("1200.000"))

        # c) Verify the Journal Entry (should be JE #2)
        self.assertEqual(JournalEntry.objects.count(), 2)
        je = JournalEntry.objects.latest('date')
        self.assertEqual(je.source_object, consumption)

        # d) Verify the JE lines: Debit Prepaid a/c, Credit Inventory
        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')

        self.assertEqual(debit_line.account, self.general_settings.prepaid_expenses_account)
        self.assertEqual(debit_line.amount, Decimal("1200.000"))
        # The sub-ledger for the prepaid debit will be the PrepaidExpense object itself,
        # but the signal doesn't link it. This is acceptable.
        self.assertIsNone(debit_line.sub_ledger_object)

        inventory_account = _get_product_inventory_account(self.amortizable_product)
        self.assertEqual(credit_line.account, inventory_account)
        self.assertEqual(credit_line.sub_ledger_object, self.amortizable_product)


    def test_create_je_for_production_return_success(self):
        """
        Verify that returning a raw material from production back to inventory
        creates a correct journal entry.
        """
        # 1. Arrange
        # a) Create stock for the raw material. This creates JE #1.
        rm_log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=50.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 10, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000") # Cost is 10
        )

        # b) Create a batch that consumes some of it. This creates JE #2.
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-RETURN-TEST",
            batch_number="B-RETURN-TEST",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 9, 0, 0)),
        )
        BatchItem.objects.create(
            batch=batch,
            primitive_product=self.raw_material,
            actual_quantity=20.0,
            source_log=rm_log,
            cost_at_consumption=Decimal("10.000")
        )
        batch.save() # Trigger consumption JE

        # c) Create the production return record. This triggers the signal for JE #3.
        prod_return = ProductionReturn.objects.create(
            product=self.raw_material,
            source_log=rm_log,
            batch=batch,
            quantity=5.0,
            return_date=timezone.make_aware(timezone.datetime(2025, 9, 12, 10, 0, 0)),
            notes="Excess material returned"
        )

        # 2. Act: The post_save signal on ProductionReturn has already fired.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 3) # 1 for receipt, 1 for consumption, 1 for return
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, prod_return)
        self.assertEqual(je.lines.count(), 2)

        # The value of the return is based on the Moving Average Cost at the time of return.
        # Since there's only one receipt, the MAC is 10. Return value = 5 * 10 = 50.
        expected_return_value = Decimal("50.000")

        # Verify the debit to the Raw Material Inventory Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['1020201']) # RM Inventory
        self.assertEqual(debit_line.amount, expected_return_value)
        self.assertEqual(debit_line.sub_ledger_object, self.raw_material)

        # Verify the credit to the WIP Inventory Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020205']) # WIP Inventory
        self.assertEqual(credit_line.amount, expected_return_value)
        self.assertEqual(credit_line.sub_ledger_object, self.raw_material)


class TestOverheadAllocation(AccountingServiceBaseTestCase):
    """
    Test suite for the overhead allocation and application process.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_overhead_allocation_and_application_success(self):
        """
        Verify the full overhead allocation and application process creates
        the expected journal entries and updates the receipt costs correctly.
        """
        # 1. Arrange
        # a) Log expenses into the child cost pools during the period
        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 10)),
            amount=Decimal("10000.000"),
            description="Factory Rent for Sep 2025",
            cost_pool=self.child_pool_rent,
            category=ExpenseLog.Category.RENT
        )
        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 15)),
            amount=Decimal("5000.000"),
            description="Machine Repair Services",
            cost_pool=self.child_pool_maintenance,
            category=ExpenseLog.Category.MAINTENANCE
        )

        # b) Create a production batch that consumes machine hours (the driver)
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-OH-001",
            batch_number="B-OH-001",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 20, 10, 0, 0)),
            machine_hours_consumed=150.0 # Total driver units for the period
        )
        # c) Receive finished goods from this batch within the period
        receipt = FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-OH-001",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 22)),
            total_cost=Decimal("20000.000"), # Prime cost
            total_quantity_produced=1000.0
        )

        # d) Create the allocation run instance
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period,
            cost_pool=self.parent_pool, # Allocate from the parent pool
            allocation_driver=self.machine_hours_driver
        )

        # 2. Act
        # Step 1: Execute the calculation
        overhead_service.execute_overhead_allocation_run(run)
        run.refresh_from_db()

        # Step 2: Post the allocation JE (Expense -> WIP)
        je_alloc = accounting_service.create_je_for_overhead_allocation(run)
        run.refresh_from_db()

        # Step 3: Apply the overhead cost to the finished goods receipt
        total_applied_cost = overhead_service.apply_overhead_to_finished_goods(run)
        receipt.refresh_from_db()

        # Step 4: Post the application JE (WIP -> FG)
        je_app = accounting_service.create_je_for_overhead_application(run, total_applied_cost)
        run.refresh_from_db()

        # 3. Assert
        # Assert Calculation
        expected_pool_total = Decimal("15000.000")
        expected_driver_total = 150.0
        expected_rate = expected_pool_total / Decimal(str(expected_driver_total)) # 100.0
        self.assertEqual(run.total_pool_amount, expected_pool_total)
        self.assertEqual(run.total_driver_units, expected_driver_total)
        self.assertEqual(run.calculated_rate, expected_rate)
        self.assertEqual(run.status, OverheadAllocationRun.Status.APPLIED)

        # Assert Allocation Journal Entry (JE #1)
        self.assertIsNotNone(je_alloc)
        self.assertEqual(je_alloc.lines.count(), 3) # 1 Debit, 2 Credits
        debit_line = je_alloc.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.general_settings.wip_inventory)
        self.assertEqual(debit_line.amount, expected_pool_total)
        
        credits = {line.account.code: line.amount for line in je_alloc.lines.filter(entry_type='credit')}
        self.assertEqual(credits[self.accounts['50203'].code], Decimal("10000.000")) # Rent
        self.assertEqual(credits[self.accounts['50201'].code], Decimal("5000.000")) # Maintenance

        # Assert Application to Inventory
        # In this case, 100% of the driver units belong to this one receipt
        self.assertEqual(total_applied_cost, expected_pool_total)
        self.assertEqual(receipt.allocated_overhead_cost, expected_pool_total)

        # Assert Application Journal Entry (JE #2)
        self.assertIsNotNone(je_app)
        self.assertEqual(je_app.lines.count(), 2)
        debit_line_app = je_app.lines.get(entry_type='debit')
        credit_line_app = je_app.lines.get(entry_type='credit')
        self.assertEqual(debit_line_app.account, self.general_settings.finished_goods_inventory)
        self.assertEqual(debit_line_app.amount, total_applied_cost)
        self.assertEqual(credit_line_app.account, self.general_settings.wip_inventory)
        self.assertEqual(credit_line_app.amount, total_applied_cost)

    def test_overhead_allocation_with_zero_driver_units(self):
        """
        Verify that if the total driver units are zero, the calculated rate is zero
        and the process completes without errors.
        """
        # 1. Arrange: Log an expense, but create no batches/receipts
        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 10)),
            amount=Decimal("10000.000"),
            description="Factory Rent for Sep 2025",
            cost_pool=self.child_pool_rent
        )
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period,
            cost_pool=self.parent_pool,
            allocation_driver=self.machine_hours_driver
        )

        # 2. Act: Execute the calculation
        overhead_service.execute_overhead_allocation_run(run)
        run.refresh_from_db()

        # 3. Assert
        self.assertEqual(run.total_pool_amount, Decimal("10000.000"))
        self.assertEqual(run.total_driver_units, 0.0)
        self.assertEqual(run.calculated_rate, Decimal("0.00000"))
        self.assertEqual(run.status, OverheadAllocationRun.Status.CALCULATED)

    def test_apply_overhead_with_no_receipts_in_period(self):
        """
        Verify that if a run is posted but there are no FG receipts in the period,
        the application step completes gracefully and marks the run as APPLIED.
        """
        # 1. Arrange: Create a run that is already posted
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period,
            cost_pool=self.parent_pool,
            allocation_driver=self.machine_hours_driver,
            total_pool_amount=Decimal("15000.000"),
            total_driver_units=150.0,
            calculated_rate=Decimal("100.0"),
            status=OverheadAllocationRun.Status.POSTED # Manually set status
        )
        # No receipts are created in this test.

        # 2. Act: Apply the overhead
        total_applied_cost = overhead_service.apply_overhead_to_finished_goods(run)
        
        # Try to create the application JE
        je_app = accounting_service.create_je_for_overhead_application(run, total_applied_cost)
        run.refresh_from_db()

        # 3. Assert
        self.assertEqual(total_applied_cost, Decimal("0.0"))
        self.assertIsNone(je_app, "No application JE should be created for zero cost.")
        self.assertEqual(run.status, OverheadAllocationRun.Status.APPLIED)
        self.assertIsNone(run.application_journal_entry)

    def test_overhead_proportional_application_and_bulk_update(self):
        """
        Verify that overhead is applied proportionally to multiple receipts and that
        the bulk_update mechanism works as expected.
        """
        # 1. Arrange
        # a) Create two batches and receipts, each with different machine hours
        batch1 = self.get_or_create_batch_for_template(self.test_template, "SO-PROP-01", "B-PROP-01")
        batch1.machine_hours_consumed = 100.0
        batch1.save()
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1, individual_batch_number="FPB-PROP-01",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 18, 10, 0, 0)),
            total_cost=Decimal("1000.000"), total_quantity_produced=100.0
        )

        batch2 = self.get_or_create_batch_for_template(self.test_template, "SO-PROP-02", "B-PROP-02")
        batch2.machine_hours_consumed = 50.0
        batch2.save()
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2, individual_batch_number="FPB-PROP-02",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 19, 10, 0, 0)),
            total_cost=Decimal("500.000"), total_quantity_produced=50.0
        )
        self.assertEqual(JournalEntry.objects.count(), 2, "Pre-condition: Two JEs for FG receipts should exist.")

        # b) Create an overhead run and an expense to be allocated
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period,
            cost_pool=self.parent_pool, # Allocate from the parent pool
            allocation_driver=self.machine_hours_driver,
        )
        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime.fromisoformat(self.period.start_date.isoformat())),
            amount=Decimal("15000.000"),
            description="Factory Rent for Test",
            cost_pool=self.child_pool_rent # Expense goes into a child pool
        )

        # 2. Act
        # a) Execute the run to calculate the rate
        overhead_service.execute_overhead_allocation_run(run)
        run.refresh_from_db()
        self.assertEqual(run.status, OverheadAllocationRun.Status.CALCULATED)
        self.assertEqual(run.total_pool_amount, Decimal("15000.000"))
        self.assertEqual(run.total_driver_units, 150.0) # 100 + 50
        self.assertEqual(run.calculated_rate , Decimal("100.000")) # 15000 / 150

        # b) Apply the calculated overhead to the receipts
        overhead_service.apply_overhead_to_finished_goods(run)

        # 3. Assert
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()

        expected_cost1 = Decimal("100.0") * run.calculated_rate # 100 hours * 100/hr = 10000
        expected_cost2 = Decimal("50.0") * run.calculated_rate  # 50 hours * 100/hr = 5000

        self.assertEqual(receipt1.allocated_overhead_cost, expected_cost1)
        self.assertEqual(receipt2.allocated_overhead_cost, expected_cost2)
        self.assertEqual(receipt1.total_cost, Decimal("1000.000") + expected_cost1)
        self.assertEqual(receipt2.total_cost, Decimal("500.000") + expected_cost2)

    def test_overhead_application_by_labor_hours(self):
        """Verify overhead allocation based on Labor Hours."""
        # 1. Arrange
        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 10)), amount=Decimal("3000.000"),
            description="Supervision Salaries", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-LH-1", batch_number="B-LH-1",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 15)), labor_hours_consumed=75.0 # 75%
        )
        batch2 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-LH-2", batch_number="B-LH-2",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 16)), labor_hours_consumed=25.0 # 25%
        )
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1, individual_batch_number="FPB-LH-1", receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 18)),
            total_cost=Decimal("1000.000"), total_quantity_produced=100.0
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2, individual_batch_number="FPB-LH-2", receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 19)),
            total_cost=Decimal("500.000"), total_quantity_produced=50.0
        )
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period, cost_pool=self.parent_pool,
            allocation_driver=self.labor_hours_driver
        )
        # 2. Act
        overhead_service.execute_overhead_allocation_run(run)
        accounting_service.create_je_for_overhead_allocation(run)
        total_applied = overhead_service.apply_overhead_to_finished_goods(run)
        accounting_service.create_je_for_overhead_application(run, total_applied)
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        # 3. Assert
        total_pool = Decimal("3000.000")
        expected_cost1 = (total_pool * (Decimal("75.0") / Decimal("100.0"))).quantize(Decimal('0.001'))
        expected_cost2 = (total_pool * (Decimal("25.0") / Decimal("100.0"))).quantize(Decimal('0.001'))
        self.assertEqual(receipt1.allocated_overhead_cost, expected_cost1)
        self.assertEqual(receipt2.allocated_overhead_cost, expected_cost2)

    def test_overhead_application_by_bottle_units(self):
        """Verify overhead allocation based on the number of units produced."""
        # 1. Arrange
        # --- ISOLATION: Create unique product and template for this test ---
        unique_product = Product.objects.create(name="Bottle Unit Test Product", code="FP-BU-TEST", product_type=Product.ProductType.FINAL_PRODUCT, unit="Unit")
        unique_template = ShopOrderTemplate.objects.create(name="Bottle Unit Test Template", final_product=unique_product, bottle_size_ml=100)

        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 10)), amount=Decimal("1500.000"),
            description="Packaging Supplies", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(template=unique_template, shop_order_number="SO-BU-1", batch_number="B-BU-1", creation_date=timezone.make_aware(timezone.datetime(2025, 9, 15)))
        batch2 = Batch.objects.create(template=unique_template, shop_order_number="SO-BU-2", batch_number="B-BU-2", creation_date=timezone.make_aware(timezone.datetime(2025, 9, 16)))
        
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1,
            individual_batch_number="FPB-BU-1",
            total_quantity_produced=100.0, total_cost=Decimal("1000.000"),
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 18)), status=FinishedProductReceipt.Status.RELEASED
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2,
            individual_batch_number="FPB-BU-2",
            total_quantity_produced=50.0, total_cost=Decimal("500.000"),
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 19)), status=FinishedProductReceipt.Status.RELEASED
        )
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period, cost_pool=self.parent_pool,
            allocation_driver=self.bottle_units_driver
        )
        # 2. Act
        overhead_service.execute_overhead_allocation_run(run)
        accounting_service.create_je_for_overhead_allocation(run)
        total_applied = overhead_service.apply_overhead_to_finished_goods(run)
        accounting_service.create_je_for_overhead_application(run, total_applied)
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        # 3. Assert
        total_pool = Decimal("1500.000")
        # --- FIX: Total units = 150 (from setup) + 100 (receipt1) + 50 (receipt2) = 300. Rate = 1500 / 300 = 5.
        rate = total_pool / Decimal("300.0")
        expected_cost1 = (Decimal("100.0") * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP) # 100 * 5 = 500.000
        expected_cost2 = (Decimal("50.0") * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)  # 50 * 5 = 250.000
        self.assertAlmostEqual(receipt1.allocated_overhead_cost, expected_cost1, places=3)
        self.assertAlmostEqual(receipt2.allocated_overhead_cost, expected_cost2, places=3)

    def test_overhead_application_by_liters_volume(self):
        """Verify overhead allocation based on the total volume produced."""
        # 1. Arrange
        # --- ISOLATION: Create unique product and template for this test ---
        unique_product = Product.objects.create(name="Liter Volume Test Product", code="FP-LV-TEST", product_type=Product.ProductType.FINAL_PRODUCT, unit="Unit")
        unique_template = ShopOrderTemplate.objects.create(name="Liter Volume Test Template", final_product=unique_product, bottle_size_ml=500)

        ExpenseLog.objects.create(
            expense_date=timezone.make_aware(timezone.datetime(2025, 9, 10)), amount=Decimal("500.000"),
            description="Water Treatment Costs", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(template=unique_template, shop_order_number="SO-LV-1", batch_number="B-LV-1", creation_date=timezone.make_aware(timezone.datetime(2025, 9, 15)))
        batch2 = Batch.objects.create(template=unique_template, shop_order_number="SO-LV-2", batch_number="B-LV-2", creation_date=timezone.make_aware(timezone.datetime(2025, 9, 16)))
        # Receipt 1: 100 bottles * 500ml = 50,000 ml = 50 Liters (2/3 of volume)
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1,
            individual_batch_number="FPB-LV-1",
            total_quantity_produced=100.0, total_cost=Decimal("1000.000"),
            # --- FIX: Use a date within the allocation period (September) ---
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 20)),
            status=FinishedProductReceipt.Status.RELEASED
        )
        # Receipt 2: 50 bottles * 500ml = 25,000 ml = 25 Liters (1/3 of volume)
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2,
            individual_batch_number="FPB-LV-2",
            total_quantity_produced=50.0, total_cost=Decimal("500.000"),
            # --- FIX: Use a date within the allocation period (September) ---
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 21)),
            status=FinishedProductReceipt.Status.RELEASED
        )
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period, cost_pool=self.parent_pool,
            allocation_driver=self.liters_volume_driver
        )
        # 2. Act
        overhead_service.execute_overhead_allocation_run(run)
        accounting_service.create_je_for_overhead_allocation(run)
        total_applied = overhead_service.apply_overhead_to_finished_goods(run)
        accounting_service.create_je_for_overhead_application(run, total_applied)
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        # 3. Assert
        total_pool = Decimal("500.000")
        # --- FIX: Total volume includes 75L from base setup + 75L from this test = 150L ---
        total_volume_in_period = Decimal("150.0")
        rate = total_pool / total_volume_in_period
        # This test's receipt1 has 50L volume
        expected_cost1 = (Decimal("50.0") * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        # This test's receipt2 has 25L volume
        expected_cost2 = (Decimal("25.0") * rate).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        self.assertAlmostEqual(receipt1.allocated_overhead_cost, expected_cost1, places=3)
        self.assertAlmostEqual(receipt2.allocated_overhead_cost, expected_cost2, places=3)


class TestTransactionCorrection(AccountingServiceBaseTestCase):
    """
    Test suite for the immutable ledger and transaction correction framework.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create a second, later financial period to post corrections into
        # --- FIX: Use get_or_create to avoid IntegrityError if base setup already created it ---
        cls.correction_period, _ = FinancialPeriod.objects.get_or_create(
            fiscal_year=cls.fiscal_year,
            name="October 2025",
            defaults={
                'start_date': timezone.make_aware(timezone.datetime(2025, 10, 1)),
                'end_date': timezone.make_aware(timezone.datetime(2025, 10, 31)),
                'status': FinancialPeriod.Status.OPEN
            }
        )

    def test_reversing_sales_dispatch_in_closed_period(self):
        """
        Verify the full correction workflow:
        1. A transaction is posted in a period.
        2. The period is closed.
        3. A correction is initiated, creating a reversing JE in the *current open* period.
        """
        # 1. Arrange: Create and dispatch an item in the September period
        # --- FIX: Explicitly create the dispatch object instead of using a missing helper ---
        batch = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-CORR-01", batch_number="B-CORR-01",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 20, 9, 0, 0)),
        )
        receipt = FinishedProductReceipt.objects.create(
            batch=batch, individual_batch_number="FPB-CORR-01",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 21, 14, 0, 0)),
            total_cost=Decimal("1000.000"), total_quantity_produced=20.0
        )
        so = SalesOrder.objects.create(
            customer=self.customer, order_date=timezone.make_aware(timezone.datetime(2025, 9, 22, 10, 0, 0)),
            so_number="SO-CORR-SALE-01"
        )
        so_item = SalesOrderItem.objects.create(
            sales_order=so, finished_product=receipt, quantity_ordered=5.0,
            base_price_per_unit=Decimal("80.000"), vat_rate=Decimal("0.14")
        )
        original_dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=so_item, quantity=5.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 23, 11, 0, 0)),
            cost_at_dispatch=Decimal("250.000") # 5 units * (1000/20)
        )
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for dispatch

        # 2. Close the September period
        self.period.status = FinancialPeriod.Status.CLOSED
        self.period.save()

        # 3. Act: Create the correction in the October period
        correction_date = timezone.make_aware(timezone.datetime(2025, 10, 5, 10, 0, 0))
        adjusting_je = accounting_service.create_reversing_je_for_correction(
            original_object=original_dispatch,
            justification="Incorrect quantity dispatched. Reversing full transaction to re-issue.",
            user=self.test_user,
            correction_date=correction_date
        )

        # 4. Assert
        # a) Check that a new JE was created and the old one is untouched
        self.assertEqual(JournalEntry.objects.count(), 3)
        original_je = JournalEntry.objects.get(content_type=ContentType.objects.get_for_model(original_dispatch), object_id=original_dispatch.id)
        self.assertEqual(original_je.date.month, 9, "Original JE date should not change.")

        # b) Verify the new adjusting JE
        self.assertIsNotNone(adjusting_je)
        self.assertEqual(adjusting_je.date, correction_date, "Adjusting JE should be in the new period.")
        self.assertEqual(adjusting_je.lines.count(), 5, "Reversing JE should have the same number of lines.")

        # c) Verify the reversal logic
        original_debits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='debit')}
        original_credits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='credit')}
        
        new_debits = {l.account.code: l.amount for l in adjusting_je.lines.filter(entry_type='debit')}
        new_credits = {l.account.code: l.amount for l in adjusting_je.lines.filter(entry_type='credit')}

        self.assertEqual(original_debits, new_credits, "Original debits should be new credits.")
        self.assertEqual(original_credits, new_debits, "Original credits should be new debits.")

        # d) Verify the audit trail (TransactionCorrection record)
        self.assertEqual(TransactionCorrection.objects.count(), 1)
        correction_record = TransactionCorrection.objects.first()
        self.assertEqual(correction_record.source_object, original_dispatch)
        self.assertEqual(correction_record.adjusting_journal_entry, adjusting_je)
        self.assertEqual(correction_record.corrected_by, self.test_user)
        self.assertIn("Incorrect quantity", correction_record.justification)
        
        # e) Verify the link from the adjusting JE back to the correction record
        self.assertEqual(adjusting_je.source_object, correction_record)

        # 5. Assert: Verify the original JE is unchanged and the new JE is a perfect reversal
        original_je = JournalEntry.objects.get(content_type=ContentType.objects.get_for_model(original_dispatch), object_id=original_dispatch.id)
        original_je.refresh_from_db()
        self.assertEqual(original_je.date.month, 9, "Original JE date should not change.")

        self.assertEqual(adjusting_je.date.month, 10)
        self.assertEqual(adjusting_je.lines.count(), original_je.lines.count())

        # Compare debits and credits
        original_debits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='debit')}
        original_credits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='credit')}
        new_debits = {l.account.code: l.amount for l in adjusting_je.lines.filter(entry_type='debit')}
        new_credits = {l.account.code: l.amount for l in adjusting_je.lines.filter(entry_type='credit')}

        self.assertEqual(original_debits, new_credits)  # Original debits should be new credits
        self.assertEqual(original_credits, new_debits)  # Original credits should be new debits


class TestOpeningBalanceSystem(AccountingServiceBaseTestCase):
    """
    Test suite for the new Universal Opening Balance system models.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()
        # Ensure all OB models are cleared for isolation
        OpeningBalanceEntry.objects.all().delete()

        # Create a fiscal year and period for 2024 for pre-migration data
        fy_2024, _ = FiscalYear.objects.get_or_create(
            name="Test Fiscal Year 2024",
            defaults={
                'start_date': timezone.make_aware(timezone.datetime(2024, 1, 1)),
                'end_date': timezone.make_aware(timezone.datetime(2024, 12, 31))
            }
        )
        FinancialPeriod.objects.get_or_create(
            fiscal_year=fy_2024,
            name="December 2024",
            defaults={
                'start_date': timezone.make_aware(timezone.datetime(2024, 12, 1)),
                'end_date': timezone.make_aware(timezone.datetime(2024, 12, 31)),
                'status': FinancialPeriod.Status.OPEN
            }
        )

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create a financial period for the migration date to prevent PermissionError
        cls.migration_period, _ = FinancialPeriod.objects.get_or_create(
            fiscal_year=cls.fiscal_year,
            name="January 2025",
            defaults={
                'start_date': timezone.make_aware(timezone.datetime(2025, 1, 1)),
                'end_date': timezone.make_aware(timezone.datetime(2025, 1, 31)),
                'status':FinancialPeriod.Status.OPEN
            }
        )

    def test_create_opening_balance_entry_structure(self):
        """
        Verify that the core models for an opening balance entry can be created
        and linked together correctly.
        """
        # 1. Arrange & Act
        ob_entry = OpeningBalanceEntry.objects.create(
            name="Go-Live 2025-01-01",
            migration_date=timezone.make_aware(timezone.datetime(2025, 1, 1))
        )
        line1 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry,
            account=self.accounts['1020206'], # Finished Goods Inventory
            entry_type=OpeningBalanceEntryLine.EntryType.DEBIT,
            total_amount=Decimal("55000.000")
        )
        # A placeholder for an equity account
        retained_earnings, _ = Account.objects.get_or_create(
            code='305', name='Retained Earnings', account_type=Account.AccountType.EQUITY
        )
        line2 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry,
            account=retained_earnings,
            entry_type=OpeningBalanceEntryLine.EntryType.CREDIT,
            total_amount=Decimal("55000.000")
        )

        # 3. Assert
        self.assertEqual(OpeningBalanceEntry.objects.count(), 1)
        self.assertEqual(ob_entry.lines.count(), 2)
        self.assertEqual(OpeningBalanceEntryLine.objects.count(), 2)
        self.assertEqual(line1.opening_balance_entry, ob_entry)
        self.assertEqual(line2.opening_balance_entry, ob_entry)

    def test_post_opening_balance_je_with_sub_ledgers_comprehensive(self):
        """
        Verify the full opening balance workflow with a comprehensive, realistic dataset:
        1. Create operational sub-ledger records (receipts, customers, suppliers, assets, WIP).
        2. Create the OpeningBalanceEntry structure linking to them.
        3. Call the service to post the master JE.
        4. Verify the resulting JE is balanced and has correct sub-ledger links for all types.
        """
        # 1. Arrange: Create the operational records (the sub-ledgers)
        migration_date = "2025-01-01"
        
        # a) Finished Goods Receipts
        mig_template = ShopOrderTemplate.objects.create(name="MIG-TPL", final_product=self.final_product)
        mig_batch_fg = Batch.objects.create(
            template=mig_template, shop_order_number="MIG-SO-FG", batch_number="MIGRATION-FG",
            creation_date=migration_date
        )
        ob_receipt1 = FinishedProductReceipt.objects.create(
            batch=mig_batch_fg, individual_batch_number="FP-A-123", total_quantity_produced=500.0,
            total_cost=Decimal("25000.000"), receipt_date=migration_date, status=FinishedProductReceipt.Status.RELEASED
        )

        # b) Raw Materials & Packaging
        ob_log_rm = InventoryLog.objects.create(
            product=self.raw_material, quantity=100.0, timestamp=migration_date,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.00"),
            release_timestamp=migration_date
        )
        ob_log_pkg = InventoryLog.objects.create(
            product=self.packaging_material, quantity=500.0, timestamp=migration_date,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("1.50"),
            release_timestamp=migration_date
        )

        # c) Work-in-Progress
        mig_batch_wip = Batch.objects.create(
            template=mig_template, shop_order_number="MIG-SO-WIP", batch_number="MIGRATION-WIP",
            creation_date="2024-12-31" # In-progress at migration
        )
        wip_cost = Decimal("525.00") # e.g., 50 units of RM @ 10.50
        # Simulate consumption by creating a JE manually for this test setup
        wip_je = JournalEntry.objects.create(date="2024-12-31", description="Simulated WIP JE", source_object=mig_batch_wip)
        JournalEntryLine.objects.create(journal_entry=wip_je, account=self.general_settings.wip_inventory, amount=wip_cost, entry_type='debit', sub_ledger_object=self.final_product)
        JournalEntryLine.objects.create(journal_entry=wip_je, account=self.accounts['1020201'], amount=wip_cost, entry_type='credit', sub_ledger_object=self.raw_material)


        # d) Fixed Assets (use assets created in base setup)
        # Calculate accumulated depreciation up to migration date
        accum_dep_asset1 = (self.asset1.depreciable_base / (self.asset1.useful_life_years * 12)) * 12
        accum_dep_asset2 = (self.asset2.depreciable_base / (self.asset2.useful_life_years * 12)) * 18

        # e) Prepaid Expenses
        ob_prepaid = PrepaidExpense.objects.create(
            description="Opening Balance Prepaid Insurance",
            initial_amount=Decimal("6000.000"),
            amortization_start_date="2024-10-01",
            amortization_end_date="2025-09-30",
            asset_account=self.general_settings.prepaid_expenses_account,
            expense_account=self.accounts['50207'], # Insurance Expense
            created_by=self.test_user,
            source_content_object=FiscalYear.objects.first() # Dummy source object
        )


        # 2. Arrange: Create the financial opening balance structure
        ob_entry = OpeningBalanceEntry.objects.create(
            name="Comprehensive Go-Live 2025-01-01", migration_date=migration_date
        )
        
        # --- DEBIT LINES ---
        # Bank
        bank_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['1020102'], entry_type='debit', total_amount=Decimal("150000.00"))
        OpeningBalanceSubLedgerDetail.objects.create(line=bank_line, sub_ledger_object=self.bank_account, amount=Decimal("150000.00"))
        # A/R
        ar_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['10203'], entry_type='debit', total_amount=Decimal("15000.00"))
        OpeningBalanceSubLedgerDetail.objects.create(line=ar_line, sub_ledger_object=self.customer, amount=Decimal("15000.00"))
        # FG Inventory
        fg_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['1020206'], entry_type='debit', total_amount=ob_receipt1.total_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=fg_line, sub_ledger_object=ob_receipt1, amount=ob_receipt1.total_cost)
        # RM Inventory
        rm_cost = ob_log_rm.costing_unit_price * Decimal(str(ob_log_rm.quantity))
        rm_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['1020201'], entry_type='debit', total_amount=rm_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=rm_line, sub_ledger_object=self.raw_material, amount=rm_cost)
        # Packaging Inventory
        pkg_cost = ob_log_pkg.costing_unit_price * Decimal(str(ob_log_pkg.quantity))
        pkg_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['1020202'], entry_type='debit', total_amount=pkg_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=pkg_line, sub_ledger_object=self.packaging_material, amount=pkg_cost)
        # WIP Inventory
        wip_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['1020205'], entry_type='debit', total_amount=wip_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=wip_line, sub_ledger_object=self.final_product, amount=wip_cost)
        # Fixed Assets (Cost)
        fa1_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['10101'], entry_type='debit', total_amount=self.asset1.purchase_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=fa1_line, sub_ledger_object=self.asset1, amount=self.asset1.purchase_cost)
        fa2_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['10102'], entry_type='debit', total_amount=self.asset2.purchase_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=fa2_line, sub_ledger_object=self.asset2, amount=self.asset2.purchase_cost)
        # Prepaid Expenses
        prepaid_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.general_settings.prepaid_expenses_account, entry_type='debit', total_amount=ob_prepaid.initial_amount)
        OpeningBalanceSubLedgerDetail.objects.create(line=prepaid_line, sub_ledger_object=ob_prepaid, amount=ob_prepaid.initial_amount)


        # --- CREDIT LINES ---
        # A/P
        ap_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['20201'], entry_type='credit', total_amount=Decimal("20000.00"))
        OpeningBalanceSubLedgerDetail.objects.create(line=ap_line, sub_ledger_object=self.supplier, amount=Decimal("20000.00"))
        # Accumulated Depreciation
        ad1_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['2020501'], entry_type='credit', total_amount=accum_dep_asset1)
        OpeningBalanceSubLedgerDetail.objects.create(line=ad1_line, sub_ledger_object=self.asset1, amount=accum_dep_asset1)
        ad2_line = OpeningBalanceEntryLine.objects.create(opening_balance_entry=ob_entry, account=self.accounts['2020502'], entry_type='credit', total_amount=accum_dep_asset2)
        OpeningBalanceSubLedgerDetail.objects.create(line=ad2_line, sub_ledger_object=self.asset2, amount=accum_dep_asset2)

        # Balancing line for Equity
        total_debits = sum(l.total_amount for l in ob_entry.lines.filter(entry_type='debit'))
        total_credits = sum(l.total_amount for l in ob_entry.lines.filter(entry_type='credit'))
        equity_balance = total_debits - total_credits
        retained_earnings, _ = Account.objects.get_or_create(code='305', name='Retained Earnings', account_type=Account.AccountType.EQUITY)
        OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=retained_earnings,
            entry_type='credit', total_amount=equity_balance
        )

        # 3. Act: Call the service to post the journal entry
        je = accounting_service.create_je_for_opening_balance(ob_entry)
        ob_entry.refresh_from_db()

        # 4. Assert
        self.assertIsNotNone(je)
        self.assertEqual(je.status, JournalEntry.Status.POSTED)
        self.assertEqual(ob_entry.status, OpeningBalanceEntry.Status.POSTED)
        self.assertEqual(ob_entry.journal_entry, je)
        
        # Verify balance
        debits_sum = je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total']
        credits_sum = je.lines.filter(entry_type='credit').aggregate(total=Sum('amount'))['total']
        self.assertIsNotNone(debits_sum)
        self.assertEqual(debits_sum, credits_sum)

        # Verify sub-ledger links are created correctly for each type
        ct = ContentType.objects.get_for_model
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.bank_account), sub_ledger_object_id=self.bank_account.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.customer), sub_ledger_object_id=self.customer.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(FinishedProductReceipt), sub_ledger_object_id=ob_receipt1.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.raw_material), sub_ledger_object_id=self.raw_material.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.packaging_material), sub_ledger_object_id=self.packaging_material.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.final_product), sub_ledger_object_id=self.final_product.id).exists()) # For WIP
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.asset1), sub_ledger_object_id=self.asset1.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.asset2), sub_ledger_object_id=self.asset2.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(self.supplier), sub_ledger_object_id=self.supplier.id).exists())
        self.assertTrue(je.lines.filter(sub_ledger_content_type=ct(PrepaidExpense), sub_ledger_object_id=ob_prepaid.id).exists())

        # Verify specific line amounts
        ar_line_je = je.lines.get(sub_ledger_content_type=ct(self.customer))
        self.assertEqual(ar_line_je.amount, Decimal("15000.00"))
        
        fa1_cost_line = je.lines.get(account=self.accounts['10101'], sub_ledger_object_id=self.asset1.id)
        self.assertEqual(fa1_cost_line.amount, self.asset1.purchase_cost)
        
        ad1_credit_line = je.lines.get(account=self.accounts['2020501'], sub_ledger_object_id=self.asset1.id)
        self.assertEqual(ad1_credit_line.amount, accum_dep_asset1)


    def test_create_opening_balance_with_sub_ledger_details(self):
        """
        Verify that sub-ledger details can be correctly linked to an opening
        balance journal entry.
        """
        # --- FIX: Create the necessary financial period for the test data ---
        FinancialPeriod.objects.get_or_create(
            fiscal_year=self.fiscal_year,
            name="January 2025",
            defaults={
                'start_date':"2025-01-01",
                'end_date':"2025-01-31",
                'status':FinancialPeriod.Status.OPEN
            }
        )

        # 1. Arrange: Create operational records representing opening balances
        # a) An opening balance for a finished good
        mig_template = ShopOrderTemplate.objects.create(
            name="MIG-TPL-PROD-A", final_product=self.final_product
        )
        mig_batch = Batch.objects.create(
            template=mig_template, shop_order_number="MIG-SO-PROD-A", batch_number="MIGRATION",
            creation_date="2025-01-01"
        )
        receipt1 = FinishedProductReceipt.objects.create(
            batch=mig_batch, individual_batch_number="FP-A-123",
            total_quantity_produced=500.0, total_cost=Decimal("25000.000"),
            receipt_date="2025-01-01", status=FinishedProductReceipt.Status.RELEASED
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=mig_batch, individual_batch_number="FP-B-456",
            total_quantity_produced=300.0, total_cost=Decimal("30000.000"),
            receipt_date="2025-01-01", status=FinishedProductReceipt.Status.RELEASED
        )

        # 2. Act: Create the financial opening balance structure linking to the records.
        ob_entry = OpeningBalanceEntry.objects.create(
            name="Go-Live 2025-01-01", migration_date="2025-01-01"
        )
        ob_line = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry,
            account=self.accounts['1020206'], # Finished Goods Inventory
            entry_type=OpeningBalanceEntryLine.EntryType.DEBIT,
            total_amount=Decimal("55000.000")
        )
        
        # Link the first sub-ledger detail
        detail1 = OpeningBalanceSubLedgerDetail.objects.create(
            line=ob_line,
            sub_ledger_object=receipt1,
            amount=receipt1.total_cost
        )
        # Link the second sub-ledger detail
        detail2 = OpeningBalanceSubLedgerDetail.objects.create(
            line=ob_line,
            sub_ledger_object=receipt2,
            amount=receipt2.total_cost
        )

        # 3. Assert
        self.assertEqual(ob_line.sub_ledger_details.count(), 2)
        self.assertEqual(OpeningBalanceSubLedgerDetail.objects.count(), 2)
        
        # Verify the details are linked correctly
        self.assertEqual(detail1.line, ob_line)

        self.assertEqual(detail1.sub_ledger_object, receipt1)
        self.assertEqual(detail1.amount, Decimal("25000.000"))
        
        self.assertEqual(detail2.line, ob_line)
        self.assertEqual(detail2.sub_ledger_object, receipt2)
        self.assertEqual(detail2.amount, Decimal("30000.000"))
        
        # Verify that the sum of the details matches the line total
        total_detail_amount = sum(d.amount for d in ob_line.sub_ledger_details.all())
        self.assertEqual(ob_line.total_amount, total_detail_amount)
