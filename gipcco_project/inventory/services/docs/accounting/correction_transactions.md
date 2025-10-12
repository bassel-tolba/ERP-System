# File: gipcco_project/inventory/services/accounting/correction_transactions.py
- **Purpose:** Implements the "Immutable Ledger" pattern by providing a structured and auditable way to correct posted transactions. Instead of deleting or changing original records, this service creates reversing entries.

### Functions:

- `correct_approved_expense(request_id: int, user, justification: str)`:
  - **Description:** A high-level function to find an approved expense request and create a full reversal for its associated financial transaction.
  - **Workflow:**
    1. Finds the `ExpenseRequest` and its resulting transaction (`ExpenseLog` or `InventoryConsumption`).
    2. Calls `create_reversing_je_for_correction()` to generate the reversing journal entry.
    3. Creates a `TransactionCorrection` audit record linking the original transaction to the new reversing entry.
    4. Appends a note to the original request indicating it has been corrected.
  - **Calls:** `create_reversing_je_for_correction()` from the current file.

- `create_reversing_je_for_correction(original_object, justification: str, user, correction_date)`:
  - **Description:** The core function for creating a reversing journal entry. It finds the original journal entry and creates a new one that perfectly mirrors and inverts it.
  - **Accounting Logic:**
    - For every debit line in the original entry, it creates a corresponding credit line in the new entry.
    - For every credit line in the original entry, it creates a corresponding debit line in the new entry.
  - **Key Features:**
    - The new reversing entry is posted in the *current open* financial period, not the original (potentially closed) period.
    - Creates a `TransactionCorrection` record to provide a clear, two-way audit trail between the original and the correcting entry.
    - Prevents a transaction from being corrected more than once.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
