# gipcco_project/inventory/services/adjusting_entries_service.py

import logging
from decimal import Decimal
from datetime import date
from dateutil.relativedelta import relativedelta

from django.db import transaction
from django.db.models import Sum, F, Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import (
    FinancialPeriod, PrepaidExpense, AmortizationLog, AccruedExpense, AccrualLog,
    ExpenseLog, PeriodCloseChecklist, SupplierInvoice, JournalEntry, JournalEntryLine, GeneralAccountingSettings
)
from .accounting_service import create_je_for_amortization, create_je_for_accrual, _check_period_is_open

logger = logging.getLogger(__name__)


def settle_accrual_with_invoice(accrual_log: AccrualLog, invoice: SupplierInvoice) -> JournalEntry:
    """
    Creates a "true-up" journal entry when an actual invoice is received for
    a previously accrued expense. This reverses the original accrual and books
    the actual cost in a single, balanced entry.

    The resulting JE has a net effect of expensing the variance in the current period.

    JE Logic:
    - DEBIT: Accrued Liability (to reverse the original credit)
    - DEBIT/CREDIT: Expense Account (for the VARIANCE between actual and accrued)
    - CREDIT: Accounts Payable (for the full actual invoice amount)
    """
    logger.info(f"Starting accrual settlement for AccrualLog ID {accrual_log.id} with Invoice {invoice.invoice_number}.")
    _check_period_is_open(invoice.invoice_date)

    settings = GeneralAccountingSettings.load()
    accrual = accrual_log.accrued_expense
    original_accrual_amount = accrual_log.amount
    actual_invoice_amount = invoice.total_amount
    variance = actual_invoice_amount - original_accrual_amount

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=f"True-up for {accrual.description} with Invoice {invoice.invoice_number}",
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )

        # 1. DEBIT: Reverse the original accrual from the liability account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=accrual.target_liability_account,
            amount=original_accrual_amount,
            entry_type='debit'
        )

        # 2. DEBIT/CREDIT: Book the variance to the expense account.
        # If the actual was higher, this is a debit (more expense).
        # If the actual was lower, this will be a credit (less expense).
        if variance != 0:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=accrual.target_expense_account,
                amount=abs(variance),
                entry_type='debit' if variance > 0 else 'credit'
            )

        # 3. CREDIT: Create the final Accounts Payable liability
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=settings.accounts_payable,
            amount=actual_invoice_amount,
            entry_type='credit',
            sub_ledger_object=invoice.supplier
        )

        # 4. VALIDATE the final entry before committing.
        je.validate_balance()

        # Link the invoice to the log for a complete audit trail
        accrual_log.settling_invoice = invoice
        accrual_log.true_up_journal_entry = je
        accrual_log.save(update_fields=['settling_invoice', 'true_up_journal_entry'])

        logger.info(f"Successfully created and validated true-up JE-{je.id} for AccrualLog ID {accrual_log.id}.")

    return je


def run_monthly_amortization(period: FinancialPeriod) -> dict:
    """
    Calculates and posts amortization for all active prepaid expenses for a given period.
    - Handles daily prorating for partial periods.
    - Creates AmortizationLog and triggers JE creation.
    - Creates ExpenseLog records based on cost pool splits for overhead allocation.
    - Updates the period close checklist.
    """
    logger.info(f"Starting monthly amortization run for period '{period.name}'.")
    
    # Find all prepaid assets that are active and overlap with the current period.
    active_prepaids = PrepaidExpense.objects.filter(
        status=PrepaidExpense.Status.ACTIVE,
        amortization_start_date__lte=period.end_date,
        amortization_end_date__gte=period.start_date
    )

    # Exclude assets for which amortization has already been logged for this period.
    existing_logs = AmortizationLog.objects.filter(
        prepaid_expense__in=active_prepaids,
        financial_period=period
    ).values_list('prepaid_expense_id', flat=True)

    prepaids_to_process = active_prepaids.exclude(id__in=existing_logs)

    # Update the checklist regardless of whether items were found.
    try:
        checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)
        checklist.is_amortization_run = True
        checklist.save()
        logger.info(f"Updated period close checklist for {period.name}: is_amortization_run=True.")
    except Exception as e:
        logger.error(f"Could not update period close checklist for '{period.name}': {e}", exc_info=True)

    if not prepaids_to_process.exists():
        logger.info("No new prepaid assets found to amortize for this period.")
        return {"status": "success", "message": "No new prepaid assets to amortize.", "processed_count": 0, "total_amortized": Decimal("0.0")}

    processed_count = 0
    total_amortized_posted = Decimal("0.0")

    for prepaid in prepaids_to_process:
        with transaction.atomic():
            # 1. Calculate daily rate
            total_days = (prepaid.amortization_end_date - prepaid.amortization_start_date).days + 1
            daily_rate = prepaid.initial_amount / total_days

            # 2. Calculate days in this specific period
            start_of_amortization_in_period = max(prepaid.amortization_start_date, period.start_date)
            end_of_amortization_in_period = min(prepaid.amortization_end_date, period.end_date)
            days_in_period = (end_of_amortization_in_period - start_of_amortization_in_period).days + 1

            # 3. Calculate amount to amortize this period
            period_amortization_amount = (Decimal(days_in_period) * daily_rate).quantize(Decimal('0.001'))

            # 4. Handle final period rounding to ensure remaining balance is zero
            amortized_so_far = prepaid.amortization_logs.aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
            remaining_balance = prepaid.initial_amount - amortized_so_far

            if period_amortization_amount > remaining_balance or prepaid.amortization_end_date <= period.end_date:
                period_amortization_amount = remaining_balance
                prepaid.status = PrepaidExpense.Status.FULLY_AMORTIZED
                prepaid.save(update_fields=['status'])

            if period_amortization_amount <= 0:
                continue

            # 5. Create AmortizationLog, which will be linked to a JE
            log = AmortizationLog.objects.create(
                prepaid_expense=prepaid,
                financial_period=period,
                amount=period_amortization_amount
            )
            # This service creates the JE and links it back to the log.
            create_je_for_amortization(log)

            # 6. Create ExpenseLog entries for overhead allocation
            if prepaid.cost_pool_splits.exists():
                for split in prepaid.cost_pool_splits.all():
                    split_amount = (period_amortization_amount * (split.percentage / Decimal(100))).quantize(Decimal('0.001'))
                    ExpenseLog.objects.create(
                        description=f"Amortization allocation for {prepaid}",
                        expense_date=period.end_date,
                        amount=split_amount,
                        category=ExpenseLog.Category.OTHER,
                        classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD,
                        cost_pool=split.cost_pool,
                        notes=f"Source: AmortizationLog ID {log.id}"
                    )
            
            processed_count += 1
            total_amortized_posted += period_amortization_amount

    summary = {
        "status": "success",
        "message": f"Amortization run completed for period '{period.name}'.",
        "processed_count": processed_count,
        "total_amortized": total_amortized_posted
    }
    logger.info(f"Finished amortization run. Processed {processed_count} assets with a total value of {total_amortized_posted}.")
    return summary


def run_monthly_accruals(period: FinancialPeriod):
    """
    Processes and posts monthly journal entries for all active, recurring accrued expenses.
    """
    logger.info(f"Starting monthly accrual run for period: {period.name}")
    
    # Find all active accrual schedules that overlap with the given financial period
    active_accruals = AccruedExpense.objects.filter(
        status=AccruedExpense.Status.ACTIVE,
        accrual_start_date__lte=period.end_date,
        accrual_end_date__gte=period.start_date
    )
    
    # Get IDs of accruals that already have a log for this period to prevent duplicates
    existing_log_ids = AccrualLog.objects.filter(
        financial_period=period
    ).values_list('accrued_expense_id', flat=True)
    
    accruals_to_process = active_accruals.exclude(id__in=existing_log_ids)
    
    logs_created_count = 0
    for accrual in accruals_to_process:
        # Calculate the number of days in the accrual period that fall within the current financial period
        overlap_start = max(accrual.accrual_start_date, period.start_date)
        overlap_end = min(accrual.accrual_end_date, period.end_date)
        days_in_period = (overlap_end - overlap_start).days + 1
        
        # Calculate the total number of days in the entire accrual schedule
        total_days = (accrual.accrual_end_date - accrual.accrual_start_date).days + 1
        
        if total_days <= 0:
            logger.warning(f"Skipping accrual ID {accrual.id} due to invalid date range (total_days={total_days}).")
            continue
            
        # Prorate the amount for the current period
        prorated_amount = (accrual.total_estimated_amount / total_days) * days_in_period
        
        AccrualLog.objects.create(
            accrued_expense=accrual,
            financial_period=period,
            amount=prorated_amount
        )
        logs_created_count += 1
        logger.info(f"Created AccrualLog for '{accrual.description}' in period '{period.name}' for amount {prorated_amount:.2f}")

    # --- CORRECTED: Update the checklist directly ---
    if logs_created_count > 0:
        checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)
        checklist.is_accruals_run = True
        checklist.save(update_fields=['is_accruals_run'])
        
    logger.info(f"Monthly accrual run completed for period: {period.name}. Created {logs_created_count} new logs.")

def revert_adjusting_entry_run(period: FinancialPeriod, run_type: str):
    """
    Reverts an adjusting entry run (Amortization or Accrual) for a given period.
    This is a critical tool for correcting mistakes within an open period.

    This function will:
    1. Find all logs (AmortizationLog or AccrualLog) for the period.
    2. Find all associated Journal Entries and ExpenseLogs.
    3. Delete all found objects in a transaction.
    4. Reset the corresponding checklist flag.
    """
    if period.status != FinancialPeriod.Status.OPEN:
        raise PermissionError(f"Cannot revert run for period '{period.name}' as it is not Open.")

    logger.warning(f"Starting REVERSAL process for '{run_type}' in period '{period.name}'.")

    with transaction.atomic():
        if run_type == 'amortization':
            logs_to_revert = AmortizationLog.objects.filter(financial_period=period)
            log_ids = logs_to_revert.values_list('id', flat=True)
            
            # Delete associated ExpenseLogs
            ExpenseLog.objects.filter(notes__in=[f"Source: AmortizationLog ID {log_id}" for log_id in log_ids]).delete()
            
            # Delete associated Journal Entries
            je_ids = logs_to_revert.exclude(journal_entry__isnull=True).values_list('journal_entry_id', flat=True)
            JournalEntry.objects.filter(id__in=je_ids).delete()
            
            # Delete the logs themselves
            count, _ = logs_to_revert.delete()
            
            # Reset checklist flag
            PeriodCloseChecklist.objects.filter(financial_period=period).update(is_amortization_run=False)
            logger.info(f"Successfully reverted {count} amortization entries.")

        elif run_type == 'accrual':
            logs_to_revert = AccrualLog.objects.filter(financial_period=period)
            log_ids = logs_to_revert.values_list('id', flat=True)

            # Delete associated ExpenseLogs
            ExpenseLog.objects.filter(notes__in=[f"Source: AccrualLog ID {log_id}" for log_id in log_ids]).delete()

            # Delete associated Journal Entries
            je_ids = logs_to_revert.exclude(journal_entry__isnull=True).values_list('journal_entry_id', flat=True)
            JournalEntry.objects.filter(id__in=je_ids).delete()
            
            count, _ = logs_to_revert.delete()
            
            PeriodCloseChecklist.objects.filter(financial_period=period).update(is_accruals_run=False)
            logger.info(f"Successfully reverted {count} accrual entries.")
        else:
            raise ValueError("Invalid run_type specified. Must be 'amortization' or 'accrual'.")

    return {"status": "success", "message": f"{run_type.capitalize()} run for period '{period.name}' has been reverted."}
