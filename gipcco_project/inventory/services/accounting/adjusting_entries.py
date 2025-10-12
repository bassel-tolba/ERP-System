# gipcco_project/inventory/services/accounting/adjusting_entries.py

import logging
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    AmortizationLog, AccrualLog
)
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)


def create_je_for_amortization(amortization_log: AmortizationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly prepaid expense amortization.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the PrepaidExpense record.
    - CREDIT: The master Prepaid Expenses control account.
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(amortization_log), object_id=amortization_log.id
    ).exists():
        logger.debug(f"Journal entry for AmortizationLog ID {amortization_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(amortization_log.financial_period.end_date)
    
    prepaid = amortization_log.prepaid_expense
    amortization_amount = amortization_log.amount
    
    debit_account = prepaid.expense_account
    
    settings = GeneralAccountingSettings.load()
    credit_account = settings.prepaid_expenses_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The prepaid expense '{prepaid}' is missing its target expense account or the master prepaid account is not set."))
        
    with transaction.atomic():
        description = _(
            "Monthly amortization for: %(prepaid_desc)s"
        ) % {
            'prepaid_desc': str(prepaid)
        }
        je = JournalEntry.objects.create(
            date=amortization_log.financial_period.end_date,
            description=description,
            source_object=amortization_log,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=amortization_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=credit_account, amount=amortization_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=prepaid
        )
        
        je.validate_balance()
        amortization_log.journal_entry = je
        amortization_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for AmortizationLog ID {amortization_log.id}.")
    return je


def create_je_for_accrual(accrual_log: AccrualLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly expense accrual.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the AccruedExpense record.
    - CREDIT: The specific accrued liability account defined on the AccruedExpense record.
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(accrual_log), object_id=accrual_log.id
    ).exists():
        logger.debug(f"Journal entry for AccrualLog ID {accrual_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(accrual_log.financial_period.end_date)
    
    accrual = accrual_log.accrued_expense
    accrual_amount = accrual_log.amount
    
    debit_account = accrual.target_expense_account
    credit_account = accrual.target_liability_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The accrued expense '{accrual.description}' is missing its target expense or liability account configuration."))
        
    with transaction.atomic():
        description = _(
            "Monthly expense accrual for: %(accrual_desc)s"
        ) % {
            'accrual_desc': accrual.description
        }
        je = JournalEntry.objects.create(
            date=accrual_log.financial_period.end_date,
            description=description,
            source_object=accrual_log,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=accrual_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=credit_account, amount=accrual_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=accrual
        )
        
        je.validate_balance()
        accrual_log.journal_entry = je
        accrual_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for AccrualLog ID {accrual_log.id}.")
    return je
