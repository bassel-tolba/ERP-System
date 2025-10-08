# File: gipcco_project/inventory/services/period_closing_service.py
- **Purpose:** Orchestrates and verifies all automated tasks required for closing a financial period.

- `run_all_period_end_tasks(period: FinancialPeriod)`: A master function that executes all automated period-end financial tasks in a specific sequence.
  - Runs amortization for prepaid expenses.
  - Runs accruals for recurring expenses.
  - Runs depreciation for fixed assets.
  - Processes all overhead allocation runs for the period, including calculation and journal entry creation.
  - Updates the period close checklist with final calculated values.
  - **Calls:** `run_monthly_amortization()`, `run_monthly_accruals()` from `services/adjusting_entries_service.py`, `run_monthly_depreciation()`, `create_je_for_overhead_allocation()`, `create_je_for_overhead_application()` from `services/accounting_service.py`, `execute_overhead_allocation_run()`, `apply_overhead_to_finished_goods()` from `services/overhead_service.py`, and `update_checklist_for_period()` from the current file.

- `update_checklist_for_period(period: FinancialPeriod)`: Updates calculated flags on the `PeriodCloseChecklist` for a given financial period to reflect its real-time status.
  - Checks if all bank accounts have a reconciled entry for the period.
  - Checks for any manual journal entries that are still in 'DRAFT' status.
  - Checks for any supplier or customer invoices that are still in 'DRAFT' status.
  - Saves the updated checklist.