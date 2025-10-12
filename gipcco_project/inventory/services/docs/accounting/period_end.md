# File: gipcco_project/inventory/services/accounting/period_end.py
- **Purpose:** Contains service functions that are specifically designed to be run as part of the month-end or period-end closing process.

### Functions:

- `run_monthly_depreciation(period: FinancialPeriod)`:
  - **Description:** A batch process that calculates and posts depreciation for all eligible fixed assets for a given financial period.
  - **Workflow:**
    1. Identifies all 'In Service' assets that should be depreciated in the period.
    2. Excludes any assets for which a `DepreciationLog` has already been created for the period to prevent duplicates.
    3. For each eligible asset, it calculates the straight-line monthly depreciation amount.
    4. It handles the final depreciation entry to ensure the asset's net book value does not fall below its salvage value.
    5. Creates a `DepreciationLog` record for each asset. This action, in turn, triggers a signal that calls `create_je_for_depreciation()` to post the individual journal entry.
    6. Updates the `PeriodCloseChecklist` to mark the depreciation task as complete for the period.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
