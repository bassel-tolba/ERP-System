# File: gipcco_project/inventory/services/accounting/asset_transactions.py
- **Purpose:** Handles journal entries related to fixed assets, primarily depreciation.

### Functions:

- `create_je_for_depreciation(depreciation_log: DepreciationLog)`:
  - **Description:** Creates a journal entry for a single asset's monthly depreciation charge. This function is typically triggered by a signal from the `DepreciationLog` model.
  - **Accounting Logic:**
    - **Debit:** The specific "Depreciation Expense" account linked to the fixed asset.
    - **Credit:** The specific "Accumulated Depreciation" account linked to the fixed asset.
  - **Key Features:**
    - Ensures the depreciation is recorded in an open financial period.
    - Links the journal entry back to the `DepreciationLog` for a clear audit trail.
    - Links the fixed asset as a sub-ledger to both the debit and credit lines for detailed asset reporting.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
