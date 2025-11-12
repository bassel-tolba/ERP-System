# gipcco_project/inventory/services/accounting/overhead_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, GeneralAccountingSettings,
    OverheadAllocationRun, CostPool, ExpenseLog
)
from ._builder import JournalEntryBuilder

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
                _("Accounting configuration error: The cost pool '%(pool_name)s' has expenses logged against it but is not mapped to a GL account.")
                % {'pool_name': expense.cost_pool.name}
            )

    total_allocated_amount = run.total_pool_amount
    if total_allocated_amount <= 0:
        logger.info(f"Total allocated amount for run {run.id} is zero. No JE will be created.")
        with transaction.atomic():
            run.status = OverheadAllocationRun.Status.POSTED
            run.save()
        return None

    description = _("Allocation of %(pool_name)s overhead for period %(period_name)s") % {
        'pool_name': run.cost_pool.name,
        'period_name': period.name
    }

    builder = JournalEntryBuilder(source_object=run)
    builder.set_description(description)
    builder.debit(total_allocated_amount, wip_account)
    for account, credit_amount in credits_by_account.items():
        builder.credit(credit_amount, account)
    
    # The builder will link the JE to run.journal_entry by default.
    je = builder.post()
    if je:
        with transaction.atomic():
            run.status = OverheadAllocationRun.Status.POSTED
            run.posted_at = timezone.now()
            run.save(update_fields=['status', 'posted_at'])

    return je


def create_je_for_overhead_application(run: OverheadAllocationRun, total_applied_cost: Decimal) -> Optional[JournalEntry]:
    """
    Creates the second journal entry in the overhead process (application to FG).
    """
    if run.status != OverheadAllocationRun.Status.POSTED:
        raise ValueError("Cannot create application JE for a run that is not in 'Posted' status.")
    if run.application_journal_entry:
        logger.warning(f"Application JE for run {run.id} already exists. Aborting.")
        return None
    if total_applied_cost <= 0:
        logger.info(f"Total applied overhead for run {run.id} is zero. No application JE will be created.")
        with transaction.atomic():
            run.status = OverheadAllocationRun.Status.APPLIED
            run.save()
        return None

    period = run.financial_period
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory

    if not all([wip_account, fg_account]):
        raise ValueError("WIP or Finished Goods inventory account is not configured in General Settings.")

    description = _("Application of %(pool_name)s overhead to Finished Goods for period %(period_name)s") % {
        'pool_name': run.cost_pool.name,
        'period_name': period.name
    }

    builder = JournalEntryBuilder(source_object=run)
    builder.set_description(description)
    builder.debit(total_applied_cost, fg_account)
    builder.credit(total_applied_cost, wip_account)
    
    # FIX: Tell the builder NOT to auto-link, so we can manually link to the correct field.
    je = builder.post(link_to_source_field=None)
    if je:
        with transaction.atomic():
            run.application_journal_entry = je
            run.status = OverheadAllocationRun.Status.APPLIED
            run.save(update_fields=['application_journal_entry', 'status'])

    return je