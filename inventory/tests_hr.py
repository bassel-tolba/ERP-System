# gipcco_project/inventory/tests_hr.py

from decimal import Decimal
from django.utils import timezone
from datetime import date

# Import the base test case from the new base file
from .test_base import AccountingServiceBaseTestCase
from .models import (
    Employee, EmployeeAdvance, EmployeeAdvanceSettlement, Payment, BankAccount,
    ExpenseLog, JournalEntry, CostPool
)
from .services import accounting_service

class TestEmployeeFinances(AccountingServiceBaseTestCase):
    """
    Test suite for Employee Advances and Settlements.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

        # Create test-specific data
        self.employee = Employee.objects.create(
            first_name="John",
            last_name="Doe",
            employee_id="EMP001"
        )
        # self.bank_account is inherited from AccountingServiceBaseTestCase
        self.cost_pool = CostPool.objects.create(
            name="HR Test Cost Pool",
            gl_account=self.accounts['50207']
        )

        # Create a payment to source the advance
        self.payment = Payment.objects.create(
            payment_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 9, 0, 0)),
            amount=Decimal("1000.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description=f"Advance for {self.employee.full_name}"
        )
        
        self.advance = EmployeeAdvance.objects.create(
            employee=self.employee,
            advance_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 9, 0, 0)),
            amount=Decimal("1000.000"),
            source_payment=self.payment
        )

    def test_create_je_for_employee_advance_success(self):
        """
        Verify that an employee advance correctly debits the employee advances
        receivable account and credits the bank account.
        """
        # 1. Arrange
        # An advance requires a source payment transaction
        
        # 2. Act: The post_save signal on EmployeeAdvance will fire. The signal
        # on Payment will not create a JE because there is no supplier/customer.
        
        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, self.advance)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to Employee Advances Receivable
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.general_settings.employee_advances_receivable)
        self.assertEqual(debit_line.amount, Decimal("1000.000"))

        # Verify the credit to the Bank GL Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.bank_account.gl_account)
        self.assertEqual(credit_line.amount, Decimal("1000.000"))

    def test_employee_advance_settlement_and_status_change(self):
        """Verify that settling an advance updates its status and unsettled amount correctly."""
        # 1. Settle a portion of the advance
        expense = ExpenseLog.objects.create(
            expense_date="2025-09-05",
            amount=Decimal("150.000"),
            description="Partial settlement",
            cost_pool=self.cost_pool,
            employee=self.employee
        )
        settlement1 = EmployeeAdvanceSettlement.objects.create(
            advance=self.advance,
            amount_settled=Decimal("150.000"),
            source_transaction=expense,
            settlement_date=date(2025, 9, 5)
        )
        self.advance.refresh_from_db()

        # 2. Assert: Check that the advance is partially settled
        self.assertEqual(self.advance.total_settled, Decimal("150.000"))
        self.assertEqual(self.advance.unsettled_amount, Decimal("850.000"))
        self.assertEqual(self.advance.status, EmployeeAdvance.Status.PARTIALLY_SETTLED)
        self.assertEqual(self.employee.outstanding_advance_balance, Decimal("850.000"))

        # 3. Settle the remaining amount of the advance
        expense2 = ExpenseLog.objects.create(
            expense_date="2025-09-10",
            amount=Decimal("850.000"),
            description="Final settlement",
            cost_pool=self.cost_pool,
            employee=self.employee
        )
        settlement2 = EmployeeAdvanceSettlement.objects.create(
            advance=self.advance,
            amount_settled=Decimal("850.000"),
            source_transaction=expense2,
            settlement_date=date(2025, 9, 10)
        )
        self.advance.refresh_from_db()

        # 4. Assert: Check that the advance is fully settled
        self.assertEqual(self.advance.total_settled, Decimal("1000.000"))
        self.assertEqual(self.advance.unsettled_amount, Decimal("0.000"))
        self.assertEqual(self.advance.status, EmployeeAdvance.Status.SETTLED)
        self.assertEqual(self.employee.outstanding_advance_balance, Decimal("0.000"))
