<!-- gipcco_project/inventory/services/docs/accounting/correction_transactions.md -->
# File: gipcco_project/inventory/services/accounting/correction_transactions.py
- **Purpose:** Implements the "Immutable Ledger" pattern by providing a structured and auditable way to correct posted transactions. Instead of deleting or changing original records, this service creates reversing entries.

### Functions:

- `correct_approved_expense(request_id: int, user, justification: str)`:
  - **Description:** A high-level function to find an approved expense request and create a full reversal for its associated financial transaction.
  - **Workflow:**
    1. Finds the `ExpenseRequest` and its resulting transaction (`ExpenseLog` or `InventoryConsumption`).
    2. Calls `create_reversing_je_for_correction()` to generate the reversing journal entry.
    3. Appends a note to the original request indicating it has been corrected.
  - **Calls:** `create_reversing_je_for_correction()` from the current file.

- `create_reversing_je_for_correction(original_object, justification: str, user, correction_date)`:
  - **Description:** The core function for creating a reversing journal entry. It finds the original journal entry and creates a new one that perfectly mirrors and inverts it. **Note:** This function intentionally creates the JE manually instead of using the builder due to the complex, stateful relationship between the JE and the `TransactionCorrection` record.
  - **Accounting Logic:**
    - For every debit line in the original entry, it creates a corresponding credit line in the new entry.
    - For every credit line in the original entry, it creates a corresponding debit line in the new entry.
  - **Key Features:**
    - The new reversing entry is posted in the *current open* financial period, not the original (potentially closed) period.
    - Creates a `TransactionCorrection` record to provide a clear, two-way audit trail. The JE is first created with the original object as a temporary source, then the `TransactionCorrection` is created linking to the new JE, and finally, the JE's source is updated to point to the `TransactionCorrection` record.
    - Prevents a transaction from being corrected more than once.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.