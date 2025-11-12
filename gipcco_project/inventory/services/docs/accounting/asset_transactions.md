<!-- gipcco_project/inventory/services/docs/accounting/asset_transactions.md -->
# File: gipcco_project/inventory/services/accounting/asset_transactions.py
- **Purpose:** Handles journal entries related to fixed assets, primarily depreciation.

### Functions:

- `create_je_for_depreciation(depreciation_log: DepreciationLog)`:
  - **Description:** Creates a journal entry for a single asset's monthly depreciation charge using the `JournalEntryBuilder`. This function is typically triggered by a signal from the `DepreciationLog` model.
  - **Accounting Logic:**
    - **Debit:** The specific "Depreciation Expense" account linked to the fixed asset.
    - **Credit:** The specific "Accumulated Depreciation" account linked to the fixed asset.
  - **Key Features:**
    - The `JournalEntryBuilder` ensures the depreciation is recorded in an open financial period and links the JE back to the `DepreciationLog`.
    - Links the fixed asset as a sub-ledger to both the debit and credit lines for detailed asset reporting.