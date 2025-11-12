# gipcco_project/inventory/services/accounting/payment_transactions.py

import logging
from typing import Optional

from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    Payment, EmployeeAdvance, EmployeeAdvanceSettlement, ExpenseLog
)
from ._builder import JournalEntryBuilder

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

    settings = GeneralAccountingSettings.load()
    ap_account = settings.accounts_payable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ap_account, bank_gl_account]):
        raise ValueError(_("A/P account or the Bank's GL account is not configured."))
        
    description = _("Payment to supplier '%(supplier)s'. Ref: %(desc)s") % {
        'supplier': payment.supplier.name,
        'desc': payment.description
    }

    builder = JournalEntryBuilder(source_object=payment)
    builder.set_description(description)
    builder.debit(payment.amount, ap_account, sub_ledger_object=payment.supplier)
    builder.credit(payment.amount, bank_gl_account, sub_ledger_object=payment.bank_account)
    return builder.post()

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

    settings = GeneralAccountingSettings.load()
    ar_account = settings.accounts_receivable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ar_account, bank_gl_account]):
        raise ValueError(_("A/R account or the Bank's GL account is not configured."))
        
    is_on_account = not payment.customer_applications.exists()

    description = _("Payment received from customer '%(customer)s'. Ref: %(desc)s") % {
        'customer': payment.customer.name,
        'desc': payment.description
    }

    if is_on_account:
        credit_account = settings.customer_deposits_account
        if not credit_account:
            raise ValueError(_("Customer Deposits account not configured in General Settings."))
    else:
        credit_account = settings.accounts_receivable

    builder = JournalEntryBuilder(source_object=payment)
    builder.set_description(description)
    builder.debit(payment.amount, bank_gl_account, sub_ledger_object=payment.bank_account)
    builder.credit(payment.amount, credit_account, sub_ledger_object=payment.customer)
    return builder.post()


def create_je_for_employee_advance(advance: EmployeeAdvance) -> Optional[JournalEntry]:
    """
    Creates a journal entry when funds are advanced to an employee.

    Accounting Logic:
    - DEBIT: Employee Advances Receivable (an asset, representing money owed to the company)
    - CREDIT: Bank/Cash Account (the source of the funds)
    """
    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    bank_gl_account = advance.source_payment.bank_account.gl_account

    if not all([employee_advances_account, bank_gl_account]):
        raise ValueError(_("The Employee Advances Receivable account or the source Bank's GL account is not configured in General Settings."))
        
    description = _("Advance of %(amount)s to employee '%(employee)s'") % {
        'amount': advance.amount,
        'employee': advance.employee.full_name
    }

    builder = JournalEntryBuilder(source_object=advance)
    builder.set_description(description)
    builder.debit(advance.amount, employee_advances_account, sub_ledger_object=advance.employee)
    builder.credit(advance.amount, bank_gl_account, sub_ledger_object=advance.source_payment.bank_account)
    return builder.post()

def create_je_for_employee_advance_settlement(settlement: EmployeeAdvanceSettlement) -> Optional[JournalEntry]:
    """
    Creates a journal entry when an employee advance is settled.
    """
    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    if not employee_advances_account:
        raise ValueError(_("The Employee Advances Receivable account is not configured in General Settings."))

    source = settlement.source_transaction

    if isinstance(source, ExpenseLog):
        debit_account = settings.accrued_expenses_account
        if not debit_account:
            raise ValueError(_("The Accrued Expenses account is not configured in General Settings for expense-based settlement."))
        description = _("Settlement of advance for '%(employee)s' with expense log #%(log_id)s") % {
            'employee': settlement.advance.employee.full_name,
            'log_id': source.id
        }
    else:
        debit_account = settings.default_cash_account
        if not debit_account:
            raise ValueError(_("The Default Cash Account is not configured in General Settings for direct advance repayment."))
        description = _("Direct repayment of advance for '%(employee)s'") % {
            'employee': settlement.advance.employee.full_name
        }

    builder = JournalEntryBuilder(source_object=settlement)
    builder.set_description(description)
    builder.debit(settlement.amount_settled, debit_account)
    builder.credit(settlement.amount_settled, employee_advances_account, sub_ledger_object=settlement.advance.employee)
    return builder.post()
