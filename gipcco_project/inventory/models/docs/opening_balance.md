# File: gipcco_project/inventory/models/opening_balance.py
**Purpose:** This file defines a set of temporary, data-migration-focused models used to import the company's opening trial balance into the ERP system during initial setup. These models provide a structured way to capture GL balances and their corresponding sub-ledger details before posting them as a single, massive journal entry.

### Class: `OpeningBalanceEntry`
- **Description:** The header model for a single opening balance migration event. It acts as a container for all the lines of the trial balance being imported.
- **Key Fields & Relationships:**
    - `migration_date`: The "go-live" date. All opening balances are posted as of this date.
    - `status`: A workflow field (`Draft`, `Posted`). Data is loaded and validated in `Draft` status. Changing the status to `Posted` triggers the creation of the final `JournalEntry`.
    - `journal_entry`: A `OneToOneField` link to the resulting master `JournalEntry` that is created when the opening balance is posted, providing a clear audit trail.

### Class: `OpeningBalanceEntryLine`
- **Description:** Represents a single line from the opening trial balance, corresponding to one General Ledger account.
- **Key Fields & Relationships:**
    - `account`: The GL account being imported.
    - `total_amount`: The total debit or credit balance for this account.
- **Data Integrity:**
    - `unique_together = ('opening_balance_entry', 'account')`: Ensures that each GL account appears only once in a single opening balance import.

### Class: `OpeningBalanceSubLedgerDetail`
- **Description:** The most granular model in the process. If an `OpeningBalanceEntryLine` is for a control account (like Accounts Receivable), this model is used to break down the `total_amount` into its constituent parts. For A/R, there would be one `OpeningBalanceSubLedgerDetail` record for each customer's outstanding balance.
- **Key Fields & Relationships:**
    - `line`: Links the detail record back to its parent GL account line.
    - `sub_ledger_object`: A `GenericForeignKey` that points to the specific sub-ledger record (e.g., a `Customer`, `Supplier`, `FixedAsset`, or `InventoryLog` instance). This is how the opening balances of sub-ledgers are established.
- **User Journey / Data Flow:**
    1. A developer or data migration specialist populates these three tables from an external source (e.g., a spreadsheet from the old accounting system).
    2. The data is validated to ensure the total debits equal total credits and that all sub-ledger details sum up to their parent control account totals.
    3. An administrator changes the `OpeningBalanceEntry` status from `Draft` to `Posted`.
    4. This triggers the `create_je_for_opening_balance` service, which reads all the data from these models and constructs one large, balanced `JournalEntry` to officially establish the company's financial position in the new ERP system.
