# gipcco_project/inventory/services/ar_service.py
from decimal import Decimal
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from ..models import (
    CustomerInvoice, Payment, CustomerCreditMemo, JournalEntry, JournalEntryLine, GeneralAccountingSettings
)

def apply_customer_credit(invoice: CustomerInvoice, credit_source, amount_to_apply: Decimal):
    """
    Applies a credit source (unapplied Payment or CreditMemo) to an invoice.
    Generates a JE to move value from Deposits/Returns to A/R.
    """
    # ... validation logic (ensure invoice is open, credit is available, etc.) ...
    
    with transaction.atomic():
        # ... update invoice.amount_paid, credit_source.unapplied_amount ...

        # Create the application JE
        settings = GeneralAccountingSettings.load()
        ar_account = settings.accounts_receivable
        
        if isinstance(credit_source, Payment):
            debit_account = settings.customer_deposits_account
        elif isinstance(credit_source, CustomerCreditMemo):
            debit_account = settings.sales_returns_account
        else:
            raise TypeError("Invalid credit source type.")

        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=_(f"Apply credit to invoice {invoice.invoice_number}"),
            source_object=invoice
        )
        # Debit Customer Deposits or Sales Returns
        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=amount_to_apply,
            entry_type='debit', sub_ledger_object=invoice.customer
        )
        # Credit Accounts Receivable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar_account, amount=amount_to_apply,
            entry_type='credit', sub_ledger_object=invoice.customer
        )
