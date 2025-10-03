# gipcco_project/inventory/services/period_closing_service.py

from django.db.models import Q
from ..models import (
    FinancialPeriod, BankReconciliation, JournalEntry, SupplierInvoice, CustomerInvoice, BankAccount, PeriodCloseChecklist,
    OverheadAllocationRun
)
from . import accounting_service
from .accounting_service import run_monthly_depreciation
from .overhead_service import execute_overhead_allocation_run, apply_overhead_to_finished_goods
from .adjusting_entries_service import run_monthly_amortization, run_monthly_accruals


def run_all_period_end_tasks(period: FinancialPeriod):
    """
    Master orchestrator for all automated period-end financial tasks.
    This ensures a logical and auditable sequence of operations.
    """
    # 1. Run Amortization for Prepaid Expenses
    run_monthly_amortization(period)

    # 2. Run Accruals for recurring expenses
    run_monthly_accruals(period)

    # 3. Run Depreciation for Fixed Assets
    run_monthly_depreciation(period)

    # 4. Run all Overhead Allocations
    # Find all top-level cost pools to initiate runs
    allocation_runs = OverheadAllocationRun.objects.filter(financial_period=period)
    for run in allocation_runs:
        if run.status == OverheadAllocationRun.Status.PENDING:
            execute_overhead_allocation_run(run)
            run.refresh_from_db()
        
        if run.status == OverheadAllocationRun.Status.CALCULATED:
            # This service creates the first JE (Expenses -> WIP)
            accounting_service.create_je_for_overhead_allocation(run)
            run.refresh_from_db()

        if run.status == OverheadAllocationRun.Status.POSTED:
            # This service applies cost to FG receipts
            total_applied_cost = apply_overhead_to_finished_goods(run)
            # This service creates the second JE (WIP -> FG)
            accounting_service.create_je_for_overhead_application(run, total_applied_cost)

    # 5. Update the Period Close Checklist with the final calculated values
    update_checklist_for_period(period)


def update_checklist_for_period(period: FinancialPeriod):
    """
    Updates calculated flags on the PeriodCloseChecklist for a given financial period.
    This function is designed to be called to get the real-time status of calculated checks.
    """
    # --- FIX: Always fetch the checklist directly from the database ---
    # This avoids using a potentially stale `period.checklist` object that might have been
    # prefetched or cached on the period instance from a previous operation.
    checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)
    
    # 1. Check Bank Reconciliations
    # CORRECTED LOGIC: Ensure every bank account has a reconciled entry within the period.
    all_bank_accounts = BankAccount.objects.all()
    reconciled_banks_in_period_pks = BankReconciliation.objects.filter(
        statement_date__gte=period.start_date,
        statement_date__lte=period.end_date,
        status=BankReconciliation.Status.RECONCILED
    ).values_list('bank_account_id', flat=True)
    
    unreconciled_bank_objects = all_bank_accounts.exclude(pk__in=reconciled_banks_in_period_pks)
    checklist.all_banks_reconciled = not unreconciled_bank_objects.exists()

    # 2. Check for Draft Manual Journal Entries
    draft_jes = JournalEntry.objects.filter(
        date__gte=period.start_date,
        date__lte=period.end_date,
        status=JournalEntry.Status.DRAFT,
        content_type__isnull=True  # Manual entries only
    ).exists()
    checklist.no_draft_manual_jes = not draft_jes

    # 3. Check for Unposted Invoices (assuming a 'DRAFT' status exists)
    unposted_supplier_invoices = SupplierInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=SupplierInvoice.InvoiceStatus.DRAFT
    ).exists()
    unposted_customer_invoices = CustomerInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=CustomerInvoice.InvoiceStatus.DRAFT
    ).exists()
    checklist.no_unposted_invoices = not unposted_supplier_invoices and not unposted_customer_invoices

    # Note: is_depreciation_run, is_overhead_posted, is_amortization_run, and is_accruals_run
    # are updated by their respective services. This function just reads their final state.

    # Save the entire object. The checklist object was loaded from the DB,
    # so it already contains the correct state for the manually-set flags.
    # We are just updating the calculated flags and persisting the whole object.
    # This is more robust than using `update_fields` in a complex transactional test.
    checklist.save()
    
    # Refresh the instance from the database to ensure all fields (including
    # manually set ones not touched by this service) are up-to-date on the
    # returned object. This prevents returning a partially stale object.
    checklist.refresh_from_db()
    return checklist
