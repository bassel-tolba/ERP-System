# File: gipcco_project/inventory/services/adjusting_entries_service.py
- **Purpose:** Manages the creation, settlement, and reversal of period-end adjusting entries, specifically amortization and accruals.

- `settle_accrual_with_invoice(accrual_log: AccrualLog, invoice: SupplierInvoice)`: Creates a "true-up" journal entry to reconcile a previously accrued expense with a final supplier invoice.
  - Reverses the original accrued liability and expense.
  - Books the actual expense and accounts payable liability from the invoice.
  - **Calls:** `_check_period_is_open()` from `accounting_service.py`.

- `run_monthly_amortization(period: FinancialPeriod)`: Processes and posts monthly amortization for all eligible prepaid expenses.
  - Calculates prorated amortization amounts, handling partial periods.
  - Creates an `AmortizationLog` record to trigger journal entry creation.
  - Creates `ExpenseLog` records if the prepaid expense is split across cost pools.
  - Updates the period close checklist.
  - **Calls:** `create_je_for_amortization()` from `accounting_service.py`.

- `run_monthly_accruals(period: FinancialPeriod)`: Processes and posts monthly journal entries for all active, recurring accrued expenses.
  - Identifies active accruals for the given period.
  - Creates an `AccrualLog` for each, which in turn triggers journal entry creation.
  - Updates the period close checklist.

- `revert_adjusting_entry_run(period: FinancialPeriod, run_type: str)`: Reverts a completed amortization or accrual run for an open financial period.
  - Deletes all logs (`AmortizationLog` or `AccrualLog`) for the period.
  - Deletes all associated `JournalEntry` and `ExpenseLog` records.
  - Resets the corresponding period close checklist flag.