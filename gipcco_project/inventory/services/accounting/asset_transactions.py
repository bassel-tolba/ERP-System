# gipcco_project/inventory/services/accounting/asset_transactions.py

import logging
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    JournalEntry, JournalEntryLine, DepreciationLog
)
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)


def create_je_for_depreciation(depreciation_log: DepreciationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly depreciation log.

    Accounting Logic:
    - DEBIT: Depreciation Expense Account (from the asset)
    - CREDIT: Accumulated Depreciation Account (from the asset)
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(depreciation_log), object_id=depreciation_log.id
    ).exists():
        logger.debug(f"Journal entry for DepreciationLog ID {depreciation_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(depreciation_log.period_date)
    
    asset = depreciation_log.asset
    depreciation_amount = depreciation_log.amount
    
    expense_account = asset.depreciation_expense_account
    accumulated_dep_account = asset.accumulated_depreciation_account

    if not all([expense_account, accumulated_dep_account]):
        raise ValueError(_(f"The fixed asset '{asset.name}' is missing its depreciation or accumulated depreciation account configuration."))
        
    with transaction.atomic():
        description = _(
            "Monthly depreciation for asset '%(asset_name)s' (%(asset_tag)s)"
        ) % {
            'asset_name': asset.name,
            'asset_tag': asset.asset_tag
        }
        je = JournalEntry.objects.create(
            date=depreciation_log.period_date,
            description=description,
            source_object=depreciation_log,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=expense_account, amount=depreciation_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=asset
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=accumulated_dep_account, amount=depreciation_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=asset
        )
        
        je.validate_balance()
        depreciation_log.journal_entry = je
        depreciation_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for DepreciationLog ID {depreciation_log.id}.")
    return je
