<!-- gipcco_project/inventory/services/docs/accounting/general_transactions.md -->
# File: gipcco_project/inventory/services/accounting/general_transactions.py
- **Purpose:** Handles a variety of miscellaneous but important accounting transactions that don't fit into the more specific categories like sales or production.

### Functions:

- `create_je_for_internal_consumption(consumption: InventoryConsumption)`:
  - **Description:** Creates a journal entry for items consumed internally, using the `JournalEntryBuilder`.
  - **Logic:**
    - **Debit:** The account depends on the `consumption_type`:
      - `EXPENSE`: A standard expense account.
      - `CAPITALIZE`: The Fixed Asset's GL control account.
      - `AMORTIZE`: The master Prepaid Expenses control account.
    - **Credit:** The inventory account of the consumed item.
  - **Calls:** `_get_product_inventory_account()`, `_get_product_expense_account()` from `_helpers.py`.

- `create_je_for_bank_transfer(transfer: BankTransfer)`:
  - **Description:** Creates a journal entry for moving funds between two internal bank accounts, using the `JournalEntryBuilder`.
  - **Logic:** Debits the destination bank's GL account and credits the source bank's GL account.

- `create_je_for_expense_log(expense_log: ExpenseLog)`:
  - **Description:** Creates the initial journal entry for a direct expense, accruing the liability, using the `JournalEntryBuilder`.
  - **Logic:** Debits the expense account (derived from the cost pool) and credits the master "Accrued Expenses" liability account.

- `create_transaction_for_direct_payment_expense(request: ExpenseRequest)`:
  - **Description:** Handles an expense that is paid directly via a bank transfer, bypassing the usual accrual process. It creates both the `ExpenseLog` and its `JournalEntry` using the builder.
  - **Logic:** Debits the expense account and directly credits the Bank/Cash account.

- `create_je_for_opening_balance(ob_entry: OpeningBalanceEntry)`:
  - **Description:** Creates the master, multi-line journal entry from a prepared `OpeningBalanceEntry` record. This is a critical step in data migration. **Note:** This function is too complex for the builder and creates the JE manually for explicit control.
  - **Logic:** Iterates through all lines and sub-ledger details in the `OpeningBalanceEntry` to build a single, balanced journal entry that establishes the company's financial position in the system.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.