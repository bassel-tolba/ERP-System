from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from datetime import date

from .test_base import AccountingServiceBaseTestCase
from .models import (
    ExpenseRequest, InventoryConsumption, PrepaidExpense, ExpenseLog, JournalEntry,
    FixedAsset, InventoryLog, Product, AccruedExpense, AccrualLog, SupplierInvoice, FinancialPeriod,
    BankAccount
)
from .services import expense_service, approval_service, accounting_service

class TestExpenseWorkflow(AccountingServiceBaseTestCase):
    def setUp(self):
        super().setUp()
        JournalEntry.objects.all().delete()
        # Create a fixed asset to be used in capitalization tests
        self.fixed_asset = FixedAsset.objects.create(
            asset_tag="CAP-ASSET-01",
            name="Test Capital Asset",
            gl_account=self.accounts['10101'], # آلات ومعدات
            accumulated_depreciation_account=self.accounts['2020501'], # مجمع إهلاك - آلات ومعدات
            depreciation_expense_account=self.accounts['5020501'], # مصروف إهلاك - آلات ومعدات
            purchase_cost=Decimal("10000.000"),
            purchase_date=self.period.start_date,
            depreciation_start_date=self.period.start_date,
            useful_life_years=5
        )
        # Create an MRO product to be used in tests
        self.mro_product = Product.objects.create(
            name="Test MRO Product for Workflow",
            code="MRO-WF-TEST-001",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=False
        )
        # Create an amortizable product
        self.amortizable_product = Product.objects.create(
            name="Test Amortizable Product for Workflow",
            code="AMORT-WF-TEST-001",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=True
        )
        # Create stock for the products
        InventoryLog.objects.create(
            product=self.mro_product,
            quantity=50.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("25.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 2, 10, 0, 0))
        )
        InventoryLog.objects.create(
            product=self.amortizable_product,
            quantity=10.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("1200.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 3, 10, 0, 0))
        )
        self.bank_account = BankAccount.objects.create(
            name="Test Bank Account for Expenses",
            gl_account=self.accounts['1020101'] # Main Bank Account
        )

    def test_create_and_cancel_request(self):
        """Confirms a request can be created and then cancelled without creating any financial records."""
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("100.00"),
            request_date=date(2025, 9, 10),
            description="Test direct expense",
            cost_pool_id=self.child_pool_maintenance.id,
            category=ExpenseLog.Category.MAINTENANCE,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
            settlement_method=ExpenseRequest.SettlementMethod.DIRECT_PAYMENT,
            bank_account_id=self.bank_account.id
        )
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)

        expense_service.cancel_pending_request(request.id, self.test_user)
        request.refresh_from_db()

        self.assertEqual(request.status, ExpenseRequest.Status.CANCELLED)
        self.assertEqual(JournalEntry.objects.count(), 2) # Only the setup logs
        self.assertEqual(InventoryConsumption.objects.count(), 0)
        self.assertEqual(ExpenseLog.objects.count(), 0)

    def test_create_and_reject_request(self):
        """Confirms a request can be rejected, again with no financial impact."""
        request = expense_service.request_inventory_expense(
            user=self.test_user,
            product_id=self.mro_product.id,
            quantity=Decimal("2.0"),
            request_date=date(2025, 9, 11),
            description="Test inventory expense",
            cost_pool_id=self.child_pool_maintenance.id
        )
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)

        approval_service.reject_request(request.id, self.test_user, "Not approved budget.")
        request.refresh_from_db()

        self.assertEqual(request.status, ExpenseRequest.Status.REJECTED)
        self.assertIn("Not approved budget", request.rejection_reason)
        self.assertEqual(JournalEntry.objects.count(), 2) # Only the setup logs
        self.assertEqual(InventoryConsumption.objects.count(), 0)

    def test_reject_capitalization_request(self):
        """Ensures a capitalization request can be rejected with no financial impact."""
        initial_cost = self.fixed_asset.purchase_cost
        
        request = expense_service.request_inventory_capitalization(
            user=self.test_user,
            product_id=self.mro_product.id,
            quantity=Decimal("5.0"),
            request_date=date(2025, 9, 16),
            description="Attempt to capitalize MRO items",
            fixed_asset_id=self.fixed_asset.id
        )
        
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)
        
        # Reject the request
        rejection_reason="This is not a capitalizable expense."
        approval_service.reject_request(request.id, self.test_user, rejection_reason)
        
        request.refresh_from_db()
        self.fixed_asset.refresh_from_db()
        
        # Assertions
        self.assertEqual(request.status, ExpenseRequest.Status.REJECTED)
        self.assertEqual(request.rejection_reason, rejection_reason)
        self.assertEqual(self.fixed_asset.purchase_cost, initial_cost) # Asset cost should not change
        self.assertEqual(JournalEntry.objects.count(), 2) # Only setup JEs
        self.assertEqual(InventoryConsumption.objects.count(), 0)

    def test_approve_inventory_prepaid_request_creates_all_objects(self):
        """Asserts that approving a prepaid request correctly creates all linked objects."""
        request = expense_service.request_inventory_prepaid(
            user=self.test_user,
            product_id=self.amortizable_product.id,
            quantity=Decimal("1.0"),
            request_date=date(2025, 9, 15),
            description="Annual software license",
            asset_account_id=self.general_settings.prepaid_expenses_account.id,
            expense_account_id=self.accounts['50207'].id, # Insurance Expense
            start_date=date(2025, 9, 15),
            end_date=date(2026, 9, 14)
        )
        
        approval_service.approve_request(request.id, self.test_user)

        # Assertions
        self.assertEqual(InventoryConsumption.objects.count(), 1)
        self.assertEqual(PrepaidExpense.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 3) # 2 setup logs + 1 consumption JE

        consumption = InventoryConsumption.objects.first()
        prepaid = PrepaidExpense.objects.first()
        je = JournalEntry.objects.latest('date')

        self.assertEqual(prepaid.source_content_object, consumption)
        self.assertEqual(je.source_object, consumption)
        self.assertEqual(prepaid.initial_amount, consumption.cost_at_consumption)
        
        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(debit_line.account, self.general_settings.prepaid_expenses_account)
        self.assertEqual(credit_line.account, accounting_service._get_product_inventory_account(self.amortizable_product))

    def test_approve_capitalization_request_updates_asset_cost(self):
        """Asserts that approving a capitalization request correctly increases the asset's cost."""
        initial_cost = self.fixed_asset.purchase_cost
        
        request = expense_service.request_inventory_capitalization(
            user=self.test_user,
            product_id=self.mro_product.id,
            quantity=Decimal("10.0"),
            request_date=date(2025, 9, 12),
            description="Capitalize spare parts onto asset",
            fixed_asset_id=self.fixed_asset.id
        )
        
        approval_service.approve_request(request.id, self.test_user)
        
        consumption = InventoryConsumption.objects.get(source_request=request)
        self.fixed_asset.refresh_from_db()
        
        expected_cost = initial_cost + consumption.cost_at_consumption
        self.assertEqual(self.fixed_asset.purchase_cost, expected_cost)

    def test_approve_direct_expense_request_creates_expense_log(self):
        """Asserts that approving a direct expense request creates the corresponding ExpenseLog."""
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("250.00"),
            request_date=date(2025, 9, 13),
            description="Urgent repairs",
            cost_pool_id=self.child_pool_maintenance.id,
            category=ExpenseLog.Category.MAINTENANCE,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
            settlement_method=ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER,
            supplier_id=self.supplier.id
        )
        
        approval_service.approve_request(request.id, self.test_user)
        
        self.assertEqual(ExpenseLog.objects.count(), 1)
        log = ExpenseLog.objects.first()
        self.assertEqual(log.source_request, request)
        self.assertEqual(log.amount, request.amount)
        self.assertEqual(log.cost_pool, request.cost_pool)

    def test_cannot_approve_non_pending_request(self):
        """Ensures that an already processed request cannot be approved again."""
        request = expense_service.request_direct_expense(
            user=self.test_user, amount=Decimal("50.00"), request_date=date(2025, 9, 14),
            description="Test", cost_pool_id=self.child_pool_rent.id, category=ExpenseLog.Category.RENT,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
            settlement_method=ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER,
            supplier_id=self.supplier.id
        )
        
        # Approve it once
        approval_service.approve_request(request.id, self.test_user)
        
        # Try to approve again
        with self.assertRaises(PermissionDenied):
            approval_service.approve_request(request.id, self.test_user)
            
        # Create and reject another request
        request2 = expense_service.request_direct_expense(
            user=self.test_user, amount=Decimal("60.00"), request_date=date(2025, 9, 15),
            description="Test 2", cost_pool_id=self.child_pool_rent.id, category=ExpenseLog.Category.RENT,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
            settlement_method=ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER,
            supplier_id=self.supplier.id
        )
        approval_service.reject_request(request2.id, self.test_user, "Rejected")
        
        # Try to approve the rejected one
        with self.assertRaises(PermissionDenied):
            approval_service.approve_request(request2.id, self.test_user)

    def test_correct_approved_expense_creates_reversing_je(self):
        """Approves a request, then corrects it, asserting a reversing JE is created."""
        request = expense_service.request_inventory_expense(
            user=self.test_user,
            product_id=self.mro_product.id,
            quantity=Decimal("4.0"),
            request_date=date(2025, 9, 20),
            description="Expense for production line A",
            cost_pool_id=self.child_pool_maintenance.id
        )
        approval_service.approve_request(request.id, self.test_user)
        
        self.assertEqual(JournalEntry.objects.count(), 3) # 2 setup + 1 consumption
        original_je = JournalEntry.objects.latest('date')
        
        # Now, correct it using the new service function
        expense_service.correct_approved_request(
            request_id=request.id,
            user=self.test_user,
            justification="Wrong quantity expensed, should have been 2 units."
        )
        
        self.assertEqual(JournalEntry.objects.count(), 4)
        reversing_je = JournalEntry.objects.latest('date')
        
        self.assertNotEqual(original_je.id, reversing_je.id)
        self.assertIn("Reversal of JE-", reversing_je.description)
        
        original_debits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='debit')}
        original_credits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='credit')}
        
        new_debits = {l.account.code: l.amount for l in reversing_je.lines.filter(entry_type='debit')}
        new_credits = {l.account.code: l.amount for l in reversing_je.lines.filter(entry_type='credit')}
        
        self.assertEqual(original_debits, new_credits)
        self.assertEqual(original_credits, new_debits)

    def test_approve_direct_expense_for_accrual(self):
        """
        Tests approving a direct expense that will be paid later via supplier invoice.
        This should create an ExpenseLog and a JE debiting the expense and crediting Accrued Liabilities.
        """
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("300.00"),
            request_date=date(2025, 9, 25),
            description="Consulting services for September",
            cost_pool_id=self.child_pool_maintenance.id,
            category=ExpenseLog.Category.FEES,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
            settlement_method=ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER,
            supplier_id=self.supplier.id
        )

        approval_service.approve_request(request.id, self.test_user)

        self.assertEqual(ExpenseLog.objects.count(), 1)
        log = ExpenseLog.objects.first()
        self.assertEqual(log.source_request, request)
        self.assertEqual(log.settlement_status, ExpenseLog.SettlementStatus.UNSETTLED)

        # 2 setup JEs + 1 for this expense
        self.assertEqual(JournalEntry.objects.count(), 3)
        je = JournalEntry.objects.latest('date')
        self.assertEqual(je.source_object, log)

        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')

        self.assertEqual(debit_line.account, self.child_pool_maintenance.gl_account)
        self.assertEqual(credit_line.account, self.general_settings.accrued_expenses_account)
        self.assertEqual(debit_line.amount, request.amount)

    def test_approve_direct_expense_for_direct_payment(self):
        """
        Tests approving a direct expense that was paid directly from a bank account.
        This should create an ExpenseLog and a JE debiting the expense and crediting the Bank Account.
        """
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("150.00"),
            request_date=date(2025, 9, 26),
            description="Office supplies paid with debit card",
            cost_pool_id=self.child_pool_maintenance.id,
            category=ExpenseLog.Category.OTHER,
            classification=ExpenseLog.Classification.SG_A,
            settlement_method=ExpenseRequest.SettlementMethod.DIRECT_PAYMENT,
            bank_account_id=self.bank_account.id
        )

        approval_service.approve_request(request.id, self.test_user)

        self.assertEqual(ExpenseLog.objects.count(), 1)
        log = ExpenseLog.objects.first()
        self.assertEqual(log.source_request, request)
        self.assertEqual(log.settlement_status, ExpenseLog.SettlementStatus.SETTLED)

        # 2 setup JEs + 1 for this expense. Crucially, the signal should NOT have fired a second JE.
        self.assertEqual(JournalEntry.objects.count(), 3)
        je = JournalEntry.objects.latest('date')
        self.assertEqual(je.source_object, log)
        
        # Check that the log's settlement object is this JE
        log.refresh_from_db()
        self.assertEqual(log.settlement_object, je)

        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')

        self.assertEqual(debit_line.account, self.child_pool_maintenance.gl_account)
        self.assertEqual(credit_line.account, self.bank_account.gl_account)
        self.assertEqual(debit_line.amount, request.amount)


class TestAccrualSettlement(AccountingServiceBaseTestCase):
    def setUp(self):
        super().setUp()
        JournalEntry.objects.all().delete() # Start fresh

        # 1. Define accounts
        self.utilities_expense_account = self.accounts['50208'] # Utilities Expense
        self.accrued_liability_account = self.general_settings.accrued_expenses_account # Accrued Expenses Liability

        # 2. Create a recurring accrued expense
        self.accrued_utility = AccruedExpense.objects.create(
            description="Estimated Monthly Electricity Bill",
            status=AccruedExpense.Status.ACTIVE,
            target_expense_account=self.utilities_expense_account,
            target_liability_account=self.accrued_liability_account,
            estimated_monthly_amount=Decimal("1000.00")
        )

        # 3. Create a log for the period we are testing (September)
        # This simulates the month-end accrual process having run
        self.accrual_log_sept = AccrualLog.objects.create(
            accrued_expense=self.accrued_utility,
            financial_period=self.period, # September 2025
            amount=Decimal("1000.00") # Estimated amount for Sept
        )
        # The signal on AccrualLog creates the initial JE
        self.initial_je = self.accrual_log_sept.journal_entry
        self.assertIsNotNone(self.initial_je)
        self.assertEqual(JournalEntry.objects.count(), 1)

        # 4. Create a supplier invoice that arrives in the next period (October)
        self.october_period = FinancialPeriod.objects.get(name="October 2025")
        self.invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-UTILITY-SEP",
            invoice_date=date(2025, 10, 5), # Invoice received in October for September's expense
            due_date=date(2025, 10, 25),
            total_amount=Decimal("1250.00") # Actual amount is higher
        )

    def test_settle_accrual_invoice_greater_than_accrual(self):
        """
        Tests settling an accrual where the actual invoice is MORE than the estimate.
        The variance should be expensed in the current period (October).
        """
        original_accrual = self.accrual_log_sept.amount
        invoice_amount = self.invoice.total_amount
        self.assertGreater(invoice_amount, original_accrual)

        # Action: Settle the accrual
        settlement_je = expense_service.settle_accrual(
            user=self.test_user,
            accrual_log_id=self.accrual_log_sept.id,
            invoice_id=self.invoice.id
        )

        # Assertions
        self.assertEqual(JournalEntry.objects.count(), 2) # Initial accrual + settlement
        self.accrual_log_sept.refresh_from_db()
        self.assertEqual(self.accrual_log_sept.settling_invoice, self.invoice)
        self.assertEqual(self.accrual_log_sept.true_up_journal_entry, settlement_je)

        # Verify the JE details
        self.assertEqual(settlement_je.date, self.invoice.invoice_date)
        self.assertEqual(settlement_je.source_object, self.invoice)
        self.assertEqual(settlement_je.lines.count(), 4)
        self.assertTrue(settlement_je.is_balanced())

        # DEBIT: Accrued Liability (reversing the original credit)
        debit_accrued_liability = settlement_je.lines.get(account=self.accrued_liability_account, entry_type='debit')
        self.assertEqual(debit_accrued_liability.amount, original_accrual)

        # DEBIT: Expense Account (for the full actual invoice amount)
        debit_expense = settlement_je.lines.get(account=self.utilities_expense_account, entry_type='debit')
        self.assertEqual(debit_expense.amount, invoice_amount)

        # CREDIT: Accounts Payable (for the full actual invoice amount)
        credit_ap = settlement_je.lines.get(account=self.general_settings.accounts_payable, entry_type='credit')
        self.assertEqual(credit_ap.amount, invoice_amount)
        self.assertEqual(credit_ap.sub_ledger_object, self.supplier)

        # CREDIT: Expense Account (reversing the original estimated debit)
        credit_expense = settlement_je.lines.get(account=self.utilities_expense_account, entry_type='credit')
        self.assertEqual(credit_expense.amount, original_accrual)

    def test_settle_accrual_invoice_less_than_accrual(self):
        """
        Tests settling an accrual where the actual invoice is LESS than the estimate.
        The variance should be a credit to the expense account in the current period.
        """
        self.invoice.total_amount = Decimal("900.00")
        self.invoice.save()

        original_accrual = self.accrual_log_sept.amount
        invoice_amount = self.invoice.total_amount
        self.assertLess(invoice_amount, original_accrual)

        # Action
        settlement_je = expense_service.settle_accrual(
            user=self.test_user,
            accrual_log_id=self.accrual_log_sept.id,
            invoice_id=self.invoice.id
        )

        # Assertions
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.assertTrue(settlement_je.is_balanced())
        self.assertEqual(settlement_je.lines.count(), 4)

        # Check the key lines
        self.assertEqual(settlement_je.lines.get(account=self.accrued_liability_account, entry_type='debit').amount, original_accrual)
        self.assertEqual(settlement_je.lines.get(account=self.utilities_expense_account, entry_type='debit').amount, invoice_amount)
        self.assertEqual(settlement_je.lines.get(account=self.general_settings.accounts_payable, entry_type='credit').amount, invoice_amount)
        self.assertEqual(settlement_je.lines.get(account=self.utilities_expense_account, entry_type='credit').amount, original_accrual)

    def test_settle_accrual_invoice_equals_accrual(self):
        """
        Tests settling an accrual where the actual invoice is EXACTLY the estimate.
        The net effect on the expense account in the current period should be zero.
        """
        self.invoice.total_amount = self.accrual_log_sept.amount
        self.invoice.save()

        original_accrual = self.accrual_log_sept.amount
        invoice_amount = self.invoice.total_amount
        self.assertEqual(invoice_amount, original_accrual)

        # Action
        settlement_je = expense_service.settle_accrual(
            user=self.test_user,
            accrual_log_id=self.accrual_log_sept.id,
            invoice_id=self.invoice.id
        )

        # Assertions
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.assertTrue(settlement_je.is_balanced())
        self.assertEqual(settlement_je.lines.count(), 4)

        # Check the key lines
        self.assertEqual(settlement_je.lines.get(account=self.accrued_liability_account, entry_type='debit').amount, original_accrual)
        self.assertEqual(settlement_je.lines.get(account=self.utilities_expense_account, entry_type='debit').amount, invoice_amount)
        self.assertEqual(settlement_je.lines.get(account=self.general_settings.accounts_payable, entry_type='credit').amount, invoice_amount)
        self.assertEqual(settlement_je.lines.get(account=self.utilities_expense_account, entry_type='credit').amount, original_accrual)

    def test_cannot_settle_already_settled_accrual(self):
        """Ensures an already settled accrual log cannot be settled again."""
        # Settle it once
        expense_service.settle_accrual(
            user=self.test_user,
            accrual_log_id=self.accrual_log_sept.id,
            invoice_id=self.invoice.id
        )
        self.assertEqual(JournalEntry.objects.count(), 2)

        # Create a new invoice for the second attempt
        second_invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-UTILITY-SEP-DUPE",
            invoice_date=date(2025, 10, 6),
            due_date=date(2025, 10, 26),
            total_amount=Decimal("100.00")
        )

        # Try to settle it again
        with self.assertRaises(ValidationError) as e:
            expense_service.settle_accrual(
                user=self.test_user,
                accrual_log_id=self.accrual_log_sept.id,
                invoice_id=second_invoice.id
            )
        
        self.assertIn("has already been settled", str(e.exception))
        self.assertEqual(JournalEntry.objects.count(), 2) # No new JE created

    def test_cannot_settle_in_closed_period(self):
        """Ensures settlement fails if the invoice date is in a closed period."""
        # Close the October period
        self.october_period.status = FinancialPeriod.Status.CLOSED
        self.october_period.save()

        with self.assertRaises(PermissionError) as e:
            expense_service.settle_accrual(
                user=self.test_user,
                accrual_log_id=self.accrual_log_sept.id,
                invoice_id=self.invoice.id
            )
        
        self.assertIn("is Closed and cannot be posted to", str(e.exception))
        self.assertEqual(JournalEntry.objects.count(), 2) # No new JE created
