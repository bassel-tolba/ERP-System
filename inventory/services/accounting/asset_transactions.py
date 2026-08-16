# gipcco_project/inventory/services/accounting/asset_transactions.py

import logging
from typing import Optional

from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, DepreciationLog
)
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def create_je_for_depreciation(depreciation_log: DepreciationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly depreciation log.

    Accounting Logic:
    - DEBIT: Depreciation Expense Account (from the asset)
    - CREDIT: Accumulated Depreciation Account (from the asset)
    """
    asset = depreciation_log.asset
    depreciation_amount = depreciation_log.amount

    expense_account = asset.depreciation_expense_account
    accumulated_dep_account = asset.accumulated_depreciation_account

    if not all([expense_account, accumulated_dep_account]):
        raise ValueError(_(f"The fixed asset '{asset.name}' is missing its depreciation or accumulated depreciation account configuration."))
        
    description = _(
        "Monthly depreciation for asset '%(asset_name)s' (%(asset_tag)s)"
    ) % {
        'asset_name': asset.name,
        'asset_tag': asset.asset_tag
    }

    builder = JournalEntryBuilder(source_object=depreciation_log)
    builder.set_description(description)
    builder.debit(depreciation_amount, expense_account, sub_ledger_object=asset)
    builder.credit(depreciation_amount, accumulated_dep_account, sub_ledger_object=asset)
    return builder.post()