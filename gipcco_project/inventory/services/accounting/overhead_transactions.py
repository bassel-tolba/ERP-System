# gipcco_project/inventory/services/accounting/overhead_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    OverheadAllocationRun, CostPool, ExpenseLog
)
from ._helpers import _check_period_is_open

logger = logging.getLogger(__name__)


def create_je_for_overhead_allocation(run: OverheadAllocationRun) -> Optional[JournalEntry]:
    """
    Creates a consolidated journal entry for an overhead allocation run.
    """
    if run.status != OverheadAllocationRun.Status.CALCULATED:
        logger.warning(f"Attempted to post JE for allocation run {run.id} which has not been calculated. Status is '{run.status}'.")
        return None
    
    if run.journal_entry:
        logger.warning(f"Journal entry for allocation run {run.id} already exists (JE ID: {run.journal_entry.id}). Aborting.")
        return None

    period = run.financial_period
    _check_period_is_open(period.end_date)

    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    if not wip_account:
        raise ValueError(_("Work-in-Progress (WIP) account is not configured in General Accounting Settings."))

    all_pools = [run.cost_pool]
    descendants = run.cost_pool.children.all()
    while descendants:
        all_pools.extend(descendants)
        descendants = CostPool.objects.filter(parent__in=descendants)

    expenses_in_pool = ExpenseLog.objects.filter(
        expense_date__gte=period.start_date,
        expense_date__lte=period.end_date,
        cost_pool__in=all_pools
    ).select_related('cost_pool__gl_account')
    
    credits_by_account = {}
    for expense in expenses_in_pool:
        account_to_credit = expense.cost_pool.gl_account
        if account_to_credit:
            credits_by_account[account_to_credit] = credits_by_account.get(account_to_credit, Decimal('0.0')) + expense.amount
        else:
            raise ValueError(
                _("Accounting configuration error: The cost pool '%(pool_name)s' has expenses logged against it but is not mapped to a GL account. Please configure it in the Cost Pool Management page.")
                % {'pool_name': expense.cost_pool.name}
            )

    total_allocated_amount = run.total_pool_amount
    if total_allocated_amount <= 0:
        logger.info(f"Total allocated amount for run {run.id} is zero. No JE will be created.")
        run.status = OverheadAllocationRun.Status.POSTED
        run.save()
        return None

    with transaction.atomic():
        description = _(
            "Allocation of %(pool_name)s overhead for period %(period_name)s"
        ) % {
            'pool_name': run.cost_pool.name,
            'period_name': period.name
        }
        je = JournalEntry.objects.create(
            date=period.end_date,
            description=description,
            source_object=run,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je,
            account=wip_account,
            amount=total_allocated_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )

        for account, credit_amount in credits_by_account.items():
            if credit_amount > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=account,
                    amount=credit_amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )
        
        je.validate_balance()
        run.journal_entry = je
        run.status = OverheadAllocationRun.Status.POSTED
        run.posted_at = timezone.now()
        run.save()

        logger.info(f"Successfully created JE-{je.id} for Overhead Allocation Run ID {run.id}.")
    return je


def create_je_for_overhead_application(run: OverheadAllocationRun, total_applied_cost: Decimal) -> Optional[JournalEntry]:
    """
    Creates the second journal entry in the overhead process.
    """
    if run.status != OverheadAllocationRun.Status.POSTED:
        raise ValueError("Cannot create application JE for a run that is not in 'Posted' status.")
    if run.application_journal_entry:
        logger.warning(f"Application JE for run {run.id} already exists. Aborting.")
        return None
    if total_applied_cost <= 0:
        logger.info(f"Total applied overhead for run {run.id} is zero. No application JE will be created.")
        run.status = OverheadAllocationRun.Status.APPLIED
        run.save()
        return None

    period = run.financial_period
    _check_period_is_open(period.end_date)

    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory

    if not all([wip_account, fg_account]):
        raise ValueError("WIP or Finished Goods inventory account is not configured in General Settings.")

    with transaction.atomic():
        description = _(
            "Application of %(pool_name)s overhead to Finished Goods for period %(period_name)s"
        ) % {
            'pool_name': run.cost_pool.name,
            'period_name': period.name
        }
        je = JournalEntry.objects.create(
            date=period.end_date,
            description=description,
            source_object=run,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=total_applied_cost, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=total_applied_cost, entry_type=JournalEntryLine.EntryType.CREDIT
        )

        je.validate_balance()
        run.application_journal_entry = je
        run.status = OverheadAllocationRun.Status.APPLIED
        run.save()

        logger.info(f"Successfully created Application JE-{je.id} for Overhead Allocation Run ID {run.id}.")
    return je
