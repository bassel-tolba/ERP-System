# gipcco_project/inventory/tests_sub_ledger.py

from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from .tests import AccountingServiceBaseTestCase
from .models import JournalEntry, JournalEntryLine, Account, Customer

class TestSubLedgerIntegrity(AccountingServiceBaseTestCase):
    """
    Test suite dedicated to ensuring the unbreakable link between the
    General Ledger and its sub-ledgers.
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        
        # 1. Designate Accounts Receivable as a control account
        cls.ar_account = cls.accounts['10203']
        cls.ar_account.is_control_account = True
        cls.ar_account.sub_ledger_model = ContentType.objects.get_for_model(Customer)
        cls.ar_account.save()

        # 2. Get a non-control account for comparison
        cls.cash_account = cls.accounts['1020101'] # النقدية بالصندوق

    def test_je_line_to_control_account_without_sub_ledger_fails(self):
        """
        Verify that creating a JournalEntryLine for a control account
        without a sub-ledger link raises a ValidationError.
        """
        je = JournalEntry.objects.create(
            date=self.period.start_date,
            description="Manual A/R entry - SHOULD FAIL"
        )
        
        line = JournalEntryLine(
            journal_entry=je,
            account=self.ar_account,
            amount="100.00",
            entry_type='debit'
            # Missing sub_ledger_object
        )
        
        with self.assertRaises(ValidationError) as context:
            line.full_clean() # Use full_clean to trigger model validation
            
        self.assertIn('sub_ledger_object_id', context.exception.message_dict)
        self.assertIn("A sub-ledger entry is required", str(context.exception))

    def test_je_line_to_control_account_with_wrong_sub_ledger_type_fails(self):
        """
        Verify that linking a sub-ledger of the wrong type (e.g., a Product
        to an A/R account) raises a ValidationError.
        """
        je = JournalEntry.objects.create(
            date=self.period.start_date,
            description="Manual A/R entry with wrong sub-ledger - SHOULD FAIL"
        )
        
        line = JournalEntryLine(
            journal_entry=je,
            account=self.ar_account,
            amount="200.00",
            entry_type='debit',
            sub_ledger_object=self.raw_material # Incorrect type
        )
        
        with self.assertRaises(ValidationError) as context:
            line.full_clean()
            
        self.assertIn('sub_ledger_content_type', context.exception.message_dict)
        self.assertIn("does not match the required type", str(context.exception))

    def test_je_line_to_control_account_with_correct_sub_ledger_succeeds(self):
        """
        Verify that a journal entry line for a control account with the
        correct sub-ledger link saves successfully.
        """
        je = JournalEntry.objects.create(
            date=self.period.start_date,
            description="Correct manual A/R entry"
        )
        
        # This line should be valid
        line = JournalEntryLine(
            journal_entry=je,
            account=self.ar_account,
            amount="300.00",
            entry_type='debit',
            sub_ledger_object=self.customer # Correct type
        )
        
        try:
            line.full_clean()
            line.save()
        except ValidationError:
            self.fail("A valid JournalEntryLine for a control account raised an unexpected ValidationError.")
            
        self.assertEqual(je.lines.count(), 1)
        self.assertEqual(je.lines.first().sub_ledger_object, self.customer)

    def test_je_line_to_non_control_account_with_sub_ledger_is_allowed(self):
        """
        Verify that a line for a non-control account can optionally have a
        sub-ledger link without raising an error. This is allowed behavior.
        """
        je = JournalEntry.objects.create(
            date=self.period.start_date,
            description="Cash sale to customer"
        )
        
        line = JournalEntryLine(
            journal_entry=je,
            account=self.cash_account, # Non-control account
            amount="50.00",
            entry_type='debit',
            sub_ledger_object=self.customer # Optional, for traceability
        )
        
        try:
            line.full_clean()
            line.save()
        except ValidationError:
            self.fail("A JournalEntryLine for a non-control account with an optional sub-ledger link raised an unexpected ValidationError.")
            
        self.assertEqual(je.lines.count(), 1)
        self.assertIsNotNone(je.lines.first().sub_ledger_object)

    def test_account_clean_method_enforces_sub_ledger_model(self):
        """
        Verify the validation on the Account model itself.
        """
        # Case 1: is_control_account is True, but sub_ledger_model is None
        with self.assertRaises(ValidationError) as context:
            acc = Account(
                name="Test Control Account",
                code="9999",
                account_type=Account.AccountType.ASSET,
                is_control_account=True,
                sub_ledger_model=None
            )
            acc.clean()
        self.assertIn('sub_ledger_model', context.exception.message_dict)

        # Case 2: is_control_account is False, but sub_ledger_model is set
        with self.assertRaises(ValidationError) as context:
            acc = Account(
                name="Test Normal Account",
                code="9998",
                account_type=Account.AccountType.EXPENSE,
                is_control_account=False,
                sub_ledger_model=ContentType.objects.get_for_model(Customer)
            )
            acc.clean()
        self.assertIn('sub_ledger_model', context.exception.message_dict)
