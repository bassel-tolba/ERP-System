# gipcco_project/inventory/tests_banking.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case and models from existing tests
from .tests import AccountingServiceBaseTestCase
from .models import (
    JournalEntry, BankTransfer, BankReconciliation, BankStatementLine, Payment
)

class TestBankingAccounting(AccountingServiceBaseTestCase):
    """
    Test suite for banking-related journal entries and processes.
    """
    def test_create_je_for_bank_transfer_success(self):
        """
        Verify that a bank transfer correctly debits the destination account
        and credits the source account.
        """
        # 1. Arrange
        transfer = BankTransfer.objects.create(
            transfer_date=timezone.make_aware(timezone.datetime(2025, 9, 27, 10, 0, 0)),
            amount=Decimal("5000.000"),
            source_account=self.bank_account,
            destination_account=self.secondary_bank_account,
            description="Cash transfer for operations"
        )

        # 2. Act: The post_save signal on BankTransfer should have created the JE.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, transfer)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to the destination bank's GL account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.secondary_bank_account.gl_account)
        self.assertEqual(debit_line.amount, Decimal("5000.000"))

        # Verify the credit to the source bank's GL account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.bank_account.gl_account)
        self.assertEqual(credit_line.amount, Decimal("5000.000"))


class TestBankReconciliation(AccountingServiceBaseTestCase):
    """
    Test suite for the Bank Reconciliation module.
    """
    def setUp(self):
        """Create transactions to be reconciled for each test."""
        super().setUp()
        self.payment_out = Payment.objects.create(
            payment_date="2025-09-10",
            amount=Decimal("150.00"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Supplier Payment",
            supplier=self.supplier
        )
        self.payment_in = Payment.objects.create(
            payment_date="2025-09-15",
            amount=Decimal("500.00"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_IN,
            description="Customer Payment",
            customer=self.customer
        )
        self.transfer = BankTransfer.objects.create(
            transfer_date="2025-09-20",
            amount=Decimal("1000.00"),
            source_account=self.secondary_bank_account,
            destination_account=self.bank_account,
            description="Funding transfer"
        )

    def test_bank_reconciliation_creation_and_unmatch(self):
        """
        Verify that a BankReconciliation can be created and that its
        transactions can be unmatched.
        """
        # 1. Arrange: Create a reconciliation and link a payment to it
        recon = BankReconciliation.objects.create(
            bank_account=self.bank_account,
            statement_date="2025-09-30",
            statement_opening_balance=Decimal("0.00"),
            statement_closing_balance=Decimal("350.00")
        )
        self.payment_out.reconciliation = recon
        self.payment_out.cleared_date = "2025-09-12"
        self.payment_out.save()

        # 2. Act: Call the unmatch method
        recon.unmatch_all_transactions()

        # 3. Assert
        self.payment_out.refresh_from_db()
        self.assertIsNone(self.payment_out.reconciliation)
        self.assertIsNone(self.payment_out.cleared_date)

    def test_bank_statement_line_matching(self):
        """
        Verify that a BankStatementLine can be linked to a Payment.
        """
        # 1. Arrange
        recon = BankReconciliation.objects.create(
            bank_account=self.bank_account,
            statement_date="2025-09-30",
            statement_opening_balance=Decimal("0.00"),
            statement_closing_balance=Decimal("350.00")
        )
        statement_line = BankStatementLine.objects.create(
            reconciliation=recon,
            transaction_date="2025-09-11",
            description="Payment to Supplier",
            amount=Decimal("-150.00") # Negative for withdrawal
        )

        # 2. Act: Manually link the statement line to the payment
        statement_line.is_reconciled = True
        statement_line.reconciled_object = self.payment_out
        statement_line.save()

        # 3. Assert
        statement_line.refresh_from_db()
        self.assertTrue(statement_line.is_reconciled)
        self.assertEqual(statement_line.reconciled_object, self.payment_out)
        self.assertIsNotNone(statement_line.reconciled_object_id)
        self.assertIsNotNone(statement_line.reconciled_object_content_type)
