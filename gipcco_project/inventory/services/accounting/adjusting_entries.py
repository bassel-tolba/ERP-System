# gipcco_project/inventory/services/accounting/adjusting_entries.py

import logging
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    AmortizationLog, AccrualLog
)
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def create_je_for_amortization(amortization_log: AmortizationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly prepaid expense amortization.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the PrepaidExpense record.
    - CREDIT: The master Prepaid Expenses control account.
    """
    prepaid = amortization_log.prepaid_expense
    amortization_amount = amortization_log.amount
    debit_account = prepaid.expense_account

    settings = GeneralAccountingSettings.load()
    credit_account = settings.prepaid_expenses_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The prepaid expense '{prepaid}' is missing its target expense account or the master prepaid account is not set."))
        
    description = _("Monthly amortization for: %(prepaid_desc)s") % {'prepaid_desc': str(prepaid)}

    builder = JournalEntryBuilder(source_object=amortization_log)
    builder.set_description(description)
    builder.debit(amortization_amount, debit_account)
    builder.credit(amortization_amount, credit_account, sub_ledger_object=prepaid)

    return builder.post()


def create_je_for_accrual(accrual_log: AccrualLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly expense accrual.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the AccruedExpense record.
    - CREDIT: The specific accrued liability account defined on the AccruedExpense record.
    """
    accrual = accrual_log.accrued_expense
    accrual_amount = accrual_log.amount
    debit_account = accrual.target_expense_account
    credit_account = accrual.target_liability_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The accrued expense '{accrual.description}' is missing its target expense or liability account configuration."))
        
    description = _("Monthly expense accrual for: %(accrual_desc)s") % {'accrual_desc': accrual.description}

    builder = JournalEntryBuilder(source_object=accrual_log)
    builder.set_description(description)
    builder.debit(accrual_amount, debit_account)
    builder.credit(accrual_amount, credit_account, sub_ledger_object=accrual)

    return builder.post()