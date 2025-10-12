# gipcco_project/inventory/services/accounting/payment_transactions.py

import logging
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    Payment, EmployeeAdvance, EmployeeAdvanceSettlement, ExpenseLog
)
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)


def create_je_for_supplier_payment(payment: Payment) -> Optional[JournalEntry]:
    """
    Creates a journal entry when a payment is made to a supplier.

    Accounting Logic:
    - DEBIT: Accounts Payable (reducing the liability)
    - CREDIT: Bank/Cash Account (reducing the asset)
    """
    if payment.payment_type != Payment.PaymentType.PAYMENT_OUT or not payment.supplier:
        logger.debug(f"JE creation skipped for Payment ID {payment.id}: Not an outgoing supplier payment.")
        return None

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(payment), object_id=payment.id
    ).exists():
        logger.debug(f"Journal entry for Payment ID {payment.id} already exists. Aborting.")
        return None

    _check_period_is_open(payment.payment_date)
    
    settings = GeneralAccountingSettings.load()
    ap_account = settings.accounts_payable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ap_account, bank_gl_account]):
        raise ValueError(_("A/P account or the Bank's GL account is not configured."))
        
    with transaction.atomic():
        description = _(
            "Payment to supplier '%(supplier)s'. Ref: %(desc)s"
        ) % {
            'supplier': payment.supplier.name,
            'desc': payment.description
        }
        je = JournalEntry.objects.create(
            date=payment.payment_date, description=description, source_object=payment,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=payment.supplier
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=payment.bank_account
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for supplier Payment ID {payment.id}.")
    return je

def create_je_for_customer_payment(payment: Payment) -> Optional[JournalEntry]:
    """
    Creates a journal entry when a payment is received from a customer.

    Accounting Logic:
    - DEBIT: Bank/Cash Account (increasing the asset)
    - CREDIT: Accounts Receivable (reducing the asset)
    """
    if payment.payment_type != Payment.PaymentType.PAYMENT_IN or not payment.customer:
        logger.debug(f"JE creation skipped for Payment ID {payment.id}: Not an incoming customer payment.")
        return None

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(payment), object_id=payment.id
    ).exists():
        logger.debug(f"Journal entry for Payment ID {payment.id} already exists. Aborting.")
        return None

    _check_period_is_open(payment.payment_date)
    
    settings = GeneralAccountingSettings.load()
    ar_account = settings.accounts_receivable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ar_account, bank_gl_account]):
        raise ValueError(_("A/R account or the Bank's GL account is not configured."))
        
    is_on_account = not payment.customer_applications.exists()

    with transaction.atomic():
        description = _(
            "Payment received from customer '%(customer)s'. Ref: %(desc)s"
        ) % {
            'customer': payment.customer.name,
            'desc': payment.description
        }
        je = JournalEntry.objects.create(
            date=payment.payment_date, description=description, source_object=payment,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=payment.bank_account
        )
        if is_on_account:
            credit_account = settings.customer_deposits_account
            if not credit_account:
                raise ValueError(_("Customer Deposits account not configured in General Settings."))
        else:
            credit_account = settings.accounts_receivable
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=credit_account,
            amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=payment.customer
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for customer Payment ID {payment.id}.")
    return je


def create_je_for_employee_advance(advance: EmployeeAdvance) -> Optional[JournalEntry]:
    """
    Creates a journal entry when funds are advanced to an employee.

    Accounting Logic:
    - DEBIT: Employee Advances Receivable (an asset, representing money owed to the company)
    - CREDIT: Bank/Cash Account (the source of the funds)
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(advance), object_id=advance.id
    ).exists():
        logger.debug(f"Journal entry for EmployeeAdvance ID {advance.id} already exists. Aborting.")
        return None

    _check_period_is_open(advance.advance_date)
    
    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    bank_gl_account = advance.source_payment.bank_account.gl_account

    if not all([employee_advances_account, bank_gl_account]):
        raise ValueError(_("The Employee Advances Receivable account or the source Bank's GL account is not configured in General Settings."))
        
    with transaction.atomic():
        description = _(
            "Advance of %(amount)s to employee '%(employee)s'"
        ) % {
            'amount': advance.amount,
            'employee': advance.employee.full_name
        }
        je = JournalEntry.objects.create(
            date=advance.advance_date, description=description, source_object=advance,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=employee_advances_account, amount=advance.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=advance.employee
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=advance.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=advance.source_payment.bank_account
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for EmployeeAdvance ID {advance.id}.")
    return je

def create_je_for_employee_advance_settlement(settlement: EmployeeAdvanceSettlement) -> Optional[JournalEntry]:
    """
    Creates a journal entry when an employee advance is settled.
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(settlement), object_id=settlement.id
    ).exists():
        logger.debug(f"Journal entry for EmployeeAdvanceSettlement ID {settlement.id} already exists. Aborting.")
        return None

    _check_period_is_open(settlement.settlement_date)

    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    if not employee_advances_account:
        raise ValueError(_("The Employee Advances Receivable account is not configured in General Settings."))

    description = ""
    debit_account = None
    source = settlement.source_transaction

    if isinstance(source, ExpenseLog):
        debit_account = settings.accrued_expenses_account
        if not debit_account:
            raise ValueError(_("The Accrued Expenses account is not configured in General Settings for expense-based settlement."))
        
        description = _(
            "Settlement of advance for '%(employee)s' with expense log #%(log_id)s"
        ) % {
            'employee': settlement.advance.employee.full_name,
            'log_id': source.id
        }
    else:
        debit_account = settings.default_cash_account
        if not debit_account:
            raise ValueError(_("The Default Cash Account is not configured in General Settings for direct advance repayment."))

        description = _(
            "Direct repayment of advance for '%(employee)s'"
        ) % {
            'employee': settlement.advance.employee.full_name
        }

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=settlement.settlement_date, description=description, source_object=settlement,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=settlement.amount_settled,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=employee_advances_account, amount=settlement.amount_settled,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=settlement.advance.employee
        )

        je.validate_balance()
        settlement.journal_entry = je
        settlement.save(update_fields=['journal_entry'])

        logger.info(f"Successfully created JE-{je.id} for EmployeeAdvanceSettlement ID {settlement.id}.")
    return je
