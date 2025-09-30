# gipcco_project/inventory/tests_hr.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case from the new base file
from .test_base import AccountingServiceBaseTestCase
from .models import (
    JournalEntry, Payment, EmployeeAdvance, EmployeeAdvanceSettlement, InventoryLog, ExpenseLog
)

class TestEmployeeFinances(AccountingServiceBaseTestCase):
    """
    Test suite for Employee Advances and Settlements.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_create_je_for_employee_advance_success(self):
        """
        Verify that an employee advance correctly debits the employee advances
        receivable account and credits the bank account.
        """
        # 1. Arrange
        # An advance requires a source payment transaction
        payment = Payment.objects.create(
            payment_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 9, 0, 0)),
            amount=Decimal("1000.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description=f"Advance for {self.employee.full_name}"
        )
        
        advance = EmployeeAdvance.objects.create(
            employee=self.employee,
            advance_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 9, 0, 0)),
            amount=Decimal("1000.000"),
            source_payment=payment
        )

        # 2. Act: The post_save signal on EmployeeAdvance will fire. The signal
        # on Payment will not create a JE because there is no supplier/customer.
        
        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, advance)
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
        """
        Verify that settling an advance updates its status and unsettled amount correctly.
        """
        # 1. Arrange: Create an advance to be settled
        payment = Payment.objects.create(
            payment_date="2025-09-01", amount=Decimal("2000.000"),
            bank_account=self.bank_account, payment_type=Payment.PaymentType.PAYMENT_OUT
        )
        advance = EmployeeAdvance.objects.create(
            employee=self.employee, advance_date="2025-09-01",
            amount=Decimal("2000.000"), source_payment=payment
        )
        self.assertEqual(advance.status, EmployeeAdvance.Status.OPEN)
        self.assertEqual(self.employee.outstanding_advance_balance, Decimal("2000.000"))

        # Create an expense log that will be used to settle part of the advance
        expense = ExpenseLog.objects.create(
            expense_date="2025-09-05",
            amount=Decimal("500.000"),
            description="Travel Expenses",
            category=ExpenseLog.Category.TRANSPORT,
            classification=ExpenseLog.Classification.SG_A,
            employee=self.employee
        )

        # 2. Act: Create a settlement record linking the expense to the advance
        settlement = EmployeeAdvanceSettlement.objects.create(
            advance=advance,
            amount_settled=Decimal("500.000"),
            source_transaction=expense
        )
        # The signal on the settlement should trigger the advance status update
        advance.refresh_from_db()

        # 3. Assert
        self.assertEqual(advance.total_settled, Decimal("500.000"))
        self.assertEqual(advance.unsettled_amount, Decimal("1500.000"))
        self.assertEqual(advance.status, EmployeeAdvance.Status.PARTIALLY_SETTLED)
        self.assertEqual(self.employee.outstanding_advance_balance, Decimal("1500.000"))

        # 4. Act: Settle the rest of the advance
        expense2 = ExpenseLog.objects.create(
            expense_date="2025-09-10", amount=Decimal("1500.000"),
            description="Conference Fee", category=ExpenseLog.Category.FEES,
            classification=ExpenseLog.Classification.SG_A, employee=self.employee
        )
        EmployeeAdvanceSettlement.objects.create(
            advance=advance,
            amount_settled=Decimal("1500.000"),
            source_transaction=expense2
        )
        advance.refresh_from_db()

        # 5. Assert
        self.assertEqual(advance.total_settled, Decimal("2000.000"))
        self.assertEqual(advance.unsettled_amount, Decimal("0.000"))
        self.assertEqual(advance.status, EmployeeAdvance.Status.SETTLED)
        self.assertEqual(self.employee.outstanding_advance_balance, Decimal("0.000"))
