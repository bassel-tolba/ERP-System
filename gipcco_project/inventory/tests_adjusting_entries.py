# gipcco_project/inventory/tests_adjusting_entries.py

from decimal import Decimal
from django.utils import timezone
from datetime import date, timedelta
from django.db import transaction

from .test_base import AccountingServiceBaseTestCase
from .models import (
    InventoryConsumption, InventoryLog, PrepaidExpense, AmortizationLog,
    ExpenseLog, JournalEntry, JournalEntryLine, Product, CostPool, CostPoolSplit,
    AccruedExpense, AccrualLog, SupplierInvoice, SupplierInvoiceItem,FinancialPeriod
)
from .services.adjusting_entries_service import run_monthly_amortization, run_monthly_accruals


class TestAdjustingEntries(AccountingServiceBaseTestCase):
    """
    Test suite for the integrated adjusting entries system, covering
    prepaid expenses (amortization) and accrued expenses.
    """
    def setUp(self):
        """Set up specific data for these tests."""
        super().setUp()
        JournalEntry.objects.all().delete()
        
        # Create a specific amortizable product with a unique code for this test suite
        self.amortizable_part = Product.objects.create(
            name="Amortizable Filter Unit",
            code="MRO-FILT-ADJUST-TEST",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=True
        )
        # Create a specific non-amortizable product with a unique code
        self.consumable_part = Product.objects.create(
            name="Consumable Gasket",
            code="MRO-GSKT-ADJUST-TEST",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=False
        )

    def test_prepaid_asset_flow_from_amortizable_consumption(self):
        """
        Verify that consuming an `is_amortizable` product correctly:
        1. Creates a linked PrepaidExpense object.
        2. Creates the initial JE moving cost from Inventory to Prepaid Expenses.
        """
        # 1. Arrange: Create stock for the amortizable part
        log = InventoryLog.objects.create(
            product=self.amortizable_part,
            quantity=10.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("120.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 1, 10, 0, 0))
        )
        
        # 2. Act: Consume the part. The post_save signal should trigger the workflow.
        consumption = InventoryConsumption.objects.create(
            product=self.amortizable_part,
            source_log=log,
            quantity_consumed=1.0,
            consumption_date=timezone.make_aware(timezone.datetime(2025, 9, 15, 14, 0, 0)),
            department=InventoryConsumption.Department.PRODUCTION,
            cost_at_consumption=Decimal("120.000"),
            consumption_type=InventoryConsumption.ConsumptionType.EXPENSE # Required for prepaid creation
        )

        # 3. Assert
        # a) Verify the PrepaidExpense object was created
        self.assertEqual(PrepaidExpense.objects.count(), 1)
        prepaid = PrepaidExpense.objects.first()
        self.assertIsNotNone(prepaid)
        self.assertEqual(prepaid.source_content_object, consumption)
        self.assertEqual(prepaid.initial_amount, Decimal("120.000"))
        self.assertEqual(prepaid.amortization_start_date, date(2025, 9, 15))

        # b) Verify the initial Journal Entry
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for consumption
        je = JournalEntry.objects.latest('date')
        self.assertEqual(je.source_object, consumption)
        
        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')

        # DEBIT should be to the master Prepaid Expenses account
        self.assertEqual(debit_line.account, self.general_settings.prepaid_expenses_account)
        self.assertEqual(debit_line.amount, Decimal("120.000"))
        
        # CREDIT should be from the MRO Inventory account
        mro_inventory_account = self.get_product_type_setting(Product.ProductType.MRO).inventory_account
        self.assertEqual(credit_line.account, mro_inventory_account)
        self.assertEqual(credit_line.amount, Decimal("120.000"))

    def test_direct_expense_flow_from_consumable_part(self):
        """
        Verify that consuming a non-amortizable product with a cost pool:
        1. Creates a single ExpenseLog record.
        2. Does NOT create a PrepaidExpense object.
        3. Creates the correct JE (Inventory -> Expense Account).
        """
        # 1. Arrange: Create stock for the consumable part
        log = InventoryLog.objects.create(
            product=self.consumable_part,
            quantity=100.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("5.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 1, 10, 0, 0))
        )

        # 2. Act: Consume the part, specifying a cost pool
        consumption = InventoryConsumption.objects.create(
            product=self.consumable_part,
            source_log=log,
            quantity_consumed=10.0,
            consumption_date=timezone.make_aware(timezone.datetime(2025, 9, 16, 10, 0, 0)),
            department=InventoryConsumption.Department.PRODUCTION,
            cost_at_consumption=Decimal("50.000"),
            cost_pool=self.child_pool_maintenance # Direct expense to this pool
        )

        # 3. Assert
        # a) Verify ExpenseLog creation
        self.assertEqual(ExpenseLog.objects.count(), 1)
        expense_log = ExpenseLog.objects.first()
        self.assertEqual(expense_log.cost_pool, self.child_pool_maintenance)
        self.assertEqual(expense_log.amount, Decimal("50.000"))

        # b) Verify NO PrepaidExpense was created
        self.assertEqual(PrepaidExpense.objects.count(), 0)

        # c) Verify the Journal Entry
        self.assertEqual(JournalEntry.objects.count(), 2)
        je = JournalEntry.objects.latest('date')
        self.assertEqual(je.source_object, consumption)
        
        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')

        # DEBIT should be to the product's default expense account
        mro_expense_account = self.get_product_type_setting(Product.ProductType.MRO).cogs_or_expense_account
        self.assertEqual(debit_line.account, mro_expense_account)
        
        # CREDIT should be from the MRO Inventory account
        mro_inventory_account = self.get_product_type_setting(Product.ProductType.MRO).inventory_account
        self.assertEqual(credit_line.account, mro_inventory_account)

    def test_amortization_prorating_and_cost_splitting(self):
        """
        Test a prepaid that starts mid-month and has a 70/30 split.
        Verify the first month's expense is prorated correctly and the
        ExpenseLog records have an identical 70/30 split.
        """
        # 1. Arrange
        # a) Create a PrepaidExpense starting mid-month
        prepaid = PrepaidExpense.objects.create(
            description="Test Prepaid Insurance",
            initial_amount=Decimal("1200.000"),
            amortization_start_date=date(2025, 9, 16),
            amortization_end_date=date(2026, 9, 15), # 365 days
            asset_account=self.general_settings.prepaid_expenses_account,
            expense_account=self.accounts['50207'], # Insurance Expense
            created_by=self.test_user,
            source_content_object=self.create_dummy_payment()
        )
        # b) Create the 70/30 split
        CostPoolSplit.objects.create(content_object=prepaid, cost_pool=self.child_pool_rent, percentage=Decimal("70.00"))
        CostPoolSplit.objects.create(content_object=prepaid, cost_pool=self.child_pool_maintenance, percentage=Decimal("30.00"))

        # 2. Act: Run the amortization service for the September period
        run_monthly_amortization(self.period)

        # 3. Assert
        # a) Verify AmortizationLog and prorated amount
        self.assertEqual(AmortizationLog.objects.count(), 1)
        log = AmortizationLog.objects.first()
        
        # September has 30 days. Amortization runs from Sep 16 to Sep 30 = 15 days.
        daily_rate = Decimal("1200.000") / 365
        expected_amount = (daily_rate * 15).quantize(Decimal('0.001'))
        self.assertAlmostEqual(log.amount, expected_amount, places=3)

        # b) Verify the Journal Entry
        self.assertIsNotNone(log.journal_entry)
        je = log.journal_entry
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['50207'])
        self.assertAlmostEqual(debit_line.amount, expected_amount, places=3)

        # c) Verify the split ExpenseLog records
        self.assertEqual(ExpenseLog.objects.count(), 2)
        rent_log = ExpenseLog.objects.get(cost_pool=self.child_pool_rent)
        maint_log = ExpenseLog.objects.get(cost_pool=self.child_pool_maintenance)
        
        expected_rent_amount = (expected_amount * Decimal("0.70")).quantize(Decimal('0.001'))
        expected_maint_amount = (expected_amount * Decimal("0.30")).quantize(Decimal('0.001'))

        self.assertAlmostEqual(rent_log.amount, expected_rent_amount, places=3)
        self.assertAlmostEqual(maint_log.amount, expected_maint_amount, places=3)

    def test_full_accrual_and_true_up_lifecycle(self):
        """
        Test the full accrual lifecycle:
        1. Initial estimated JE is created by the monthly service.
        2. A SupplierInvoice with a different value is linked.
        3. Verify the three-part "true-up" JE is generated correctly.
        """
        # 1. Arrange: Create an AccruedExpense for utilities
        accrual = AccruedExpense.objects.create(
            description="Factory Utilities",
            estimated_monthly_amount=Decimal("5000.000"),
            target_expense_account=self.accounts['50208'], # Utilities Expense
            target_liability_account=self.accounts['20204'] # Accrued Expenses
        )

        # 2. Act (Part 1): Run the accrual service for September
        run_monthly_accruals(self.period)

        # 3. Assert (Part 1): Verify the initial accrual JE
        self.assertEqual(AccrualLog.objects.count(), 1)
        log = AccrualLog.objects.first()
        self.assertEqual(log.amount, Decimal("5000.000"))
        
        je1 = log.journal_entry
        self.assertEqual(je1.lines.get(entry_type='debit').account, self.accounts['50208'])
        self.assertEqual(je1.lines.get(entry_type='credit').account, self.accounts['20204'])
        self.assertEqual(je1.lines.get(entry_type='debit').amount, Decimal("5000.000"))

        # 4. Arrange (Part 2): The actual invoice arrives in October
        october_period = FinancialPeriod.objects.get(name="October 2025")
        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="UTIL-SEP-2025",
            invoice_date=date(2025, 10, 5),
            due_date=date(2025, 10, 20),
            total_amount=Decimal("5500.000") # Actual cost is higher
        )
        # This is a placeholder for the goods/services received
        dummy_log = InventoryLog.objects.create(
            product=self.consumable_part,
            quantity=1,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=0,
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 10, 5, 0, 0, 0))
        )
        SupplierInvoiceItem.objects.create(invoice=invoice, receipt=dummy_log, amount=invoice.total_amount)

        # 5. Act (Part 2): Link the invoice to the accrual to trigger the true-up
        # This logic will be in a separate service function, which we call here.
        from .services.adjusting_entries_service import settle_accrual_with_invoice
        je2 = settle_accrual_with_invoice(log, invoice)
        # For now, we will simulate the JE creation manually to test the concept.
        
        # This is what the `settle_accrual_with_invoice` service *would* do:
        

        # 6. Assert (Part 2): Verify the true-up JE
        self.assertIsNotNone(je2)
        self.assertEqual(je2.lines.count(), 4)
        
        debits = {l.account.code: l.amount for l in je2.lines.filter(entry_type='debit')}
        credits = {l.account.code: l.amount for l in je2.lines.filter(entry_type='credit')}

        # Debits: Accrued Liability (5000) + Expense (5500)
        self.assertEqual(debits[self.accounts['20204'].code], Decimal("5000.000"))
        self.assertEqual(debits[self.accounts['50208'].code], Decimal("5500.000"))
        
        # Credits: A/P (5500) + Expense (5000)
        self.assertEqual(credits[self.accounts['20201'].code], Decimal("5500.000"))
        self.assertEqual(credits[self.accounts['50208'].code], Decimal("5000.000"))

        self.assertEqual(sum(debits.values()), sum(credits.values())) # Balanced
        
        # Net effect on expense account for October: Debit 5500, Credit 5000 -> Net Debit of 500, which is the variance. Correct.

    def create_dummy_payment(self):
        """Helper to create a payment for linking to a prepaid."""
        from .models import Payment
        return Payment.objects.create(
            payment_date=date(2025, 9, 15),
            amount=Decimal("1200.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Dummy Payment for Prepaid",
            supplier=self.supplier
        )
