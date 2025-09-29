# gipcco_project/inventory/tests_accounting.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case and models from existing tests
from .tests import AccountingServiceBaseTestCase
from .models import (
    FinancialPeriod, InventoryLog, JournalEntry, JournalEntryLine, Batch, BatchItem, FinishedProductReceipt,
    SalesOrder, SalesOrderItem, FinishedProductDispatch, Payment,
    InventoryAdjustment, InventoryCount, InventoryConsumption, ProductionReturn,
    ExpenseLog, OverheadAllocationRun
)
from .services import overhead_service, accounting_service
from .services.accounting_service import (
    create_je_for_inventory_receipt,
    create_je_for_production_consumption,
    create_je_for_finished_goods_receipt
)


class TestAccountingService(AccountingServiceBaseTestCase):
    """
    Test suite for functions in `accounting_service.py`.
    Inherits the scalable setup from AccountingServiceBaseTestCase.
    """

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

        # 2. Act & Assert: Attempt to create a log and expect a PermissionError
        with self.assertRaises(PermissionError) as context:
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
            cost_at_consumption=Decimal("10.000"), # From the first receipt
            source_type='inventory_log' # Dummy value, not used by JE creation
        )
        BatchItem.objects.create(
            batch=batch,
            primitive_product=self.raw_material,
            theoretical_quantity=5.0, # --- FIX: Added missing field ---
            actual_quantity=5.0,
            cost_at_consumption=Decimal("12.000"), # A second, more expensive receipt
            source_type='inventory_log'
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


class TestPaymentAccounting(AccountingServiceBaseTestCase):
    """
    Test suite specifically for payment-related journal entries.
    """
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
        self.assertEqual(debit_line.account, self.accounts['20201']) # A/P Account
        self.assertEqual(debit_line.amount, Decimal("1130.000"))

        # Verify the credit to the Bank GL Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.bank_account.gl_account)
        self.assertEqual(credit_line.amount, Decimal("1130.000"))

    def test_create_je_for_customer_payment_success(self):
        """
        Verify that a payment from a customer correctly debits the bank and credits A/R.
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

        # Verify the credit to Accounts Receivable
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['10203']) # A/R Account
        self.assertEqual(credit_line.amount, Decimal("912.000"))


class TestMiscAccountingTransactions(AccountingServiceBaseTestCase):
    """
    Test suite for various other accounting transactions like internal
    consumption and production returns.
    """
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

    def test_create_je_for_production_return_success(self):
        """
        Verify that returning unused raw material from production correctly
        debits Raw Material Inventory and credits WIP Inventory.
        """
        # 1. Arrange
        # a) Create stock for the raw material. This creates JE #1.
        rm_log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=100.0,
            timestamp=timezone.now(), # FIX: Added missing required field
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000")
        )

        # b) Create the production return record. This triggers the signal for JE #2.
        # The costing service will calculate the value of this return.
        prod_return = ProductionReturn.objects.create(
            product=self.raw_material,
            source_log=rm_log,
            quantity=15.0,
            return_date=timezone.make_aware(timezone.datetime(2025, 9, 29, 16, 0, 0)),
            notes="Excess material from Batch B-TEST-001"
        )

        # 2. Act: The post_save signal on ProductionReturn has already fired.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for return
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, prod_return)
        self.assertEqual(je.lines.count(), 2)

        expected_value = Decimal("150.000") # 15 units * 10.000/unit cost from source log

        # Verify the debit to Raw Material Inventory
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['1020201']) # RM Inventory
        self.assertEqual(debit_line.amount, expected_value)

        # Verify the credit to WIP Inventory
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020205']) # WIP Inventory
        self.assertEqual(credit_line.amount, expected_value)


class TestOverheadAllocation(AccountingServiceBaseTestCase):
    """
    Test suite for the overhead allocation and application process.
    """
    def test_overhead_allocation_and_application_success(self):
        """
        Verify the full overhead cycle:
        1. Expense logs create a pool of costs.
        2. Allocation run calculates the rate.
        3. First JE moves costs from Expense accounts to WIP.
        4. Application applies cost to finished goods.
        5. Second JE moves applied cost from WIP to Finished Goods Inventory.
        """
        # 1. Arrange
        # a) Log expenses into the child cost pools during the period
        ExpenseLog.objects.create(
            expense_date="2025-09-10",
            amount=Decimal("10000.000"),
            description="Factory Rent for Sep 2025",
            cost_pool=self.child_pool_rent,
            category=ExpenseLog.Category.RENT
        )
        ExpenseLog.objects.create(
            expense_date="2025-09-15",
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
            receipt_date="2025-09-22",
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
            expense_date="2025-09-10",
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
        the bulk_update mechanism correctly updates costs without triggering extra JEs.
        """
        # 1. Arrange
        # a) Log expenses
        ExpenseLog.objects.create(
            expense_date="2025-09-10", amount=Decimal("15000.000"),
            description="Factory Overhead", cost_pool=self.child_pool_rent
        )
        
        # b) Create two batches with different machine hour consumptions
        batch1 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-OH-P1", batch_number="B-OH-P1",
            creation_date="2025-09-15", machine_hours_consumed=100.0 # 2/3 of total
        )
        batch2 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-OH-P2", batch_number="B-OH-P2",
            creation_date="2025-09-16", machine_hours_consumed=50.0 # 1/3 of total
        )
        
        # c) Receive finished goods for both batches. This will create 2 JEs.
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1, individual_batch_number="FPB-OH-P1", receipt_date="2025-09-18",
            total_cost=Decimal("10000.000"), total_quantity_produced=100.0
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2, individual_batch_number="FPB-OH-P2", receipt_date="2025-09-19",
            total_cost=Decimal("5000.000"), total_quantity_produced=50.0
        )
        self.assertEqual(JournalEntry.objects.count(), 2, "Pre-condition: Two JEs for FG receipts should exist.")

        # d) Create and execute the allocation run
        run = OverheadAllocationRun.objects.create(
            financial_period=self.period, cost_pool=self.parent_pool,
            allocation_driver=self.machine_hours_driver
        )
        overhead_service.execute_overhead_allocation_run(run)
        
        # 2. Act
        # Post the allocation JE (Expense -> WIP). This is JE #3.
        je_alloc = accounting_service.create_je_for_overhead_allocation(run)
        
        # Apply the overhead cost to the finished goods receipts
        total_applied_cost = overhead_service.apply_overhead_to_finished_goods(run)
        receipt1.refresh_from_db()
        receipt2.refresh_from_db()
        
        # Post the application JE (WIP -> FG). This is JE #4.
        je_app = accounting_service.create_je_for_overhead_application(run, total_applied_cost)

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 4, "Should be 4 JEs in total now.")
        
        # Assert proportional cost application
        total_pool_amount = Decimal("15000.000")
        expected_cost1 = (total_pool_amount * (Decimal("100.0") / Decimal("150.0"))).quantize(Decimal('0.001'))
        expected_cost2 = (total_pool_amount * (Decimal("50.0") / Decimal("150.0"))).quantize(Decimal('0.001'))
        
        self.assertEqual(receipt1.allocated_overhead_cost, expected_cost1)
        self.assertEqual(receipt2.allocated_overhead_cost, expected_cost2)
        self.assertEqual(total_applied_cost, expected_cost1 + expected_cost2)

        # Assert that the application JE correctly moves the total applied cost
        self.assertIsNotNone(je_app)
        debit_line = je_app.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.general_settings.finished_goods_inventory)
        self.assertEqual(debit_line.amount, total_applied_cost)
        credit_line = je_app.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.general_settings.wip_inventory)
        self.assertEqual(credit_line.amount, total_applied_cost)

    def test_overhead_application_by_labor_hours(self):
        """Verify overhead allocation based on Labor Hours."""
        # 1. Arrange
        ExpenseLog.objects.create(
            expense_date="2025-09-10", amount=Decimal("3000.000"),
            description="Supervision Salaries", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-LH-1", batch_number="B-LH-1",
            creation_date="2025-09-15", labor_hours_consumed=75.0 # 75%
        )
        batch2 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-LH-2", batch_number="B-LH-2",
            creation_date="2025-09-16", labor_hours_consumed=25.0 # 25%
        )
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1, individual_batch_number="FPB-LH-1", receipt_date="2025-09-18",
            total_cost=Decimal("1000.000"), total_quantity_produced=100.0
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2, individual_batch_number="FPB-LH-2", receipt_date="2025-09-19",
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
        ExpenseLog.objects.create(
            expense_date="2025-09-10", amount=Decimal("1500.000"),
            description="Packaging Supplies", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(template=self.test_template, shop_order_number="SO-BU-1", batch_number="B-BU-1", creation_date="2025-09-15")
        batch2 = Batch.objects.create(template=self.test_template, shop_order_number="SO-BU-2", batch_number="B-BU-2", creation_date="2025-09-16")
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1, individual_batch_number="FPB-BU-1", receipt_date="2025-09-18",
            total_cost=Decimal("1000.000"), total_quantity_produced=120.0 # 80% of units
        )
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2, individual_batch_number="FPB-BU-2", receipt_date="2025-09-19",
            total_cost=Decimal("500.000"), total_quantity_produced=30.0 # 20% of units
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
        expected_cost1 = (total_pool * (Decimal("120.0") / Decimal("150.0"))).quantize(Decimal('0.001'))
        expected_cost2 = (total_pool * (Decimal("30.0") / Decimal("150.0"))).quantize(Decimal('0.001'))
        self.assertEqual(receipt1.allocated_overhead_cost, expected_cost1)
        self.assertEqual(receipt2.allocated_overhead_cost, expected_cost2)

    def test_overhead_application_by_liters_volume(self):
        """Verify overhead allocation based on the total volume produced."""
        # 1. Arrange
        ExpenseLog.objects.create(
            expense_date="2025-09-10", amount=Decimal("500.000"),
            description="Water Treatment Costs", cost_pool=self.child_pool_rent
        )
        batch1 = Batch.objects.create(template=self.test_template, shop_order_number="SO-LV-1", batch_number="B-LV-1", creation_date="2025-09-15")
        batch2 = Batch.objects.create(template=self.test_template, shop_order_number="SO-LV-2", batch_number="B-LV-2", creation_date="2025-09-16")
        # Receipt 1: 100 bottles * 500ml = 50,000 ml = 50 Liters (2/3 of volume)
        receipt1 = FinishedProductReceipt.objects.create(
            batch=batch1,
            individual_batch_number="FPB-LV-1",
            receipt_date=timezone.now().date(),
            total_cost=Decimal("1000.000"),
            total_quantity_produced=100.0
        )
        # Receipt 2: 50 bottles * 500ml = 25,000 ml = 25 Liters (1/3 of volume)
        receipt2 = FinishedProductReceipt.objects.create(
            batch=batch2,
            individual_batch_number="FPB-LV-2",
            receipt_date=timezone.now().date(),
            total_cost=Decimal("500.000"),
            total_quantity_produced=50.0
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
        # Total volume is 75 Liters
        expected_cost1 = (total_pool * (Decimal("50.0") / Decimal("75.0"))).quantize(Decimal('0.001'))
        expected_cost2 = (total_pool * (Decimal("25.0") / Decimal("75.0"))).quantize(Decimal('0.001'))
        self.assertEqual(receipt1.allocated_overhead_cost, expected_cost1)
        self.assertEqual(receipt2.allocated_overhead_cost, expected_cost2)
