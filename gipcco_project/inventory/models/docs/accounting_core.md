# File: gipcco_project/inventory/models/accounting_core.py
**Purpose:** This file establishes the absolute foundation of the ERP's financial system. It defines the core structures required for double-entry bookkeeping: the fiscal calendar, the chart of accounts, and the journal entry mechanism. All financial transactions throughout the system culminate in records created from these models.

### Class: `FiscalYear`
- **Description:** Represents a company's official accounting year. It acts as a container for all the financial periods within that year, providing a high-level structure for financial reporting and year-end closing processes.
- **Key Fields & Relationships:**
    - `start_date`, `end_date`: Define the boundaries of the financial year.
    - `is_closed`: A critical boolean flag that, when true, signifies that the year's accounting is finalized and no more transactions should be posted to it.
- **Business Logic:**
    - The `clean()` method enforces that the `start_date` cannot be after the `end_date`, ensuring logical consistency.

### Class: `FinancialPeriod`
- **Description:** Represents a single accounting period, typically a month, within a `FiscalYear`. This is the most granular level at which the books are controlled (opened/closed). The status of a `FinancialPeriod` dictates whether new transactions can be posted.
- **Key Fields & Relationships:**
    - `fiscal_year`: A foreign key linking each period to its parent `FiscalYear`. `on_delete=models.PROTECT` prevents the deletion of a fiscal year if it still contains periods.
    - `status`: A state machine field (`Open`, `Pending Close`, `Closed`, `Permanently Locked`) that controls the period's lifecycle. This is the primary gatekeeper for posting new transactions.
- **State Transitions & Business Logic:**
    - **`Open`**: The default state. Transactions can be freely posted.
    - **`Pending Close`**: A transitional state used during the period-end review process.
    - **`Closed`**: No new transactions can be posted. Re-opening requires special permissions (`can_reopen_period`).
    - **`Permanently Locked`**: An irreversible state, typically used after audits are complete.
- **Security and Compliance:**
    - Custom permissions (`can_reopen_period`, `can_permanently_lock_period`) are defined to restrict sensitive actions to authorized users.

### Class: `Account`
- **Description:** Defines a single account in the Chart of Accounts (CoA). This model creates the hierarchical structure of all assets, liabilities, equity, revenue, and expenses, which is the backbone of all financial reporting.
- **Key Fields & Relationships:**
    - `parent`: A self-referential foreign key that builds the tree structure of the CoA (e.g., "Cash at Bank ABC" is a child of "Cash and Banks").
    - `is_control_account`: A boolean that designates this account as a control account in the General Ledger (GL). This is a critical flag.
    - `sub_ledger_model`: A foreign key to `ContentType`. If `is_control_account` is true, this field specifies which model acts as the detailed sub-ledger (e.g., for "Accounts Receivable", the sub-ledger model would be `Customer`).
- **Data Integrity:**
    - The `clean()` method enforces that an account marked as a control account *must* have a `sub_ledger_model` defined, and vice-versa. This ensures the structural integrity of the sub-ledger system.

### Class: `JournalEntry`
- **Description:** Represents a single, balanced financial transaction (e.g., an invoice posting, a payment). It serves as the header for a set of `JournalEntryLine` records. This model is the atomic unit of the General Ledger; every financial event in the ERP creates a `JournalEntry`.
- **Key Fields & Relationships:**
    - `source_object`: A `GenericForeignKey` that provides a direct, traversable link from the financial entry back to the operational document that created it (e.g., an `InventoryLog`, `Payment`, `FinishedProductDispatch`). This is essential for auditability and drill-down reporting.
- **Business Logic & Validation:**
    - `is_balanced()` / `validate_balance()`: Core methods that enforce the fundamental accounting principle: Debits must equal Credits. Services that create journal entries are required to call `validate_balance()` before finalizing the transaction.
    - `get_description()`: A powerful method that generates a dynamic, user-friendly, and translated description of the transaction's purpose based on its `source_object`. This abstracts complex logic away from templates and reports.
- **Data Integrity:**
    - This model represents the "Immutable Ledger". Once posted, a `JournalEntry` should not be altered or deleted. Corrections are handled by creating new, reversing journal entries.

### Class: `JournalEntryLine`
- **Description:** A single line within a `JournalEntry`, representing either a debit or a credit to a specific `Account`.
- **Key Fields & Relationships:**
    - `journal_entry`: Links the line back to its header. `on_delete=models.CASCADE` ensures that if a JE is deleted (which should not happen in practice), its lines are also removed.
    - `account`: The GL account being affected.
    - `sub_ledger_object`: A `GenericForeignKey`. If the line's `account` is a control account, this field *must* point to the specific sub-ledger record (e.g., the specific `Customer` or `Supplier` instance) being affected.
- **Data Integrity:**
    - The `clean()` method provides robust validation. It ensures that for control accounts, a sub-ledger object is provided and that its type matches the `sub_ledger_model` defined on the `Account`. This is a critical guardrail that maintains consistency between the GL and its sub-ledgers.

### Class: `ProductTypeAccountingSettings`
- **Description:** A configuration model that maps high-level product categories (`RAW_MATERIAL`, `FINAL_PRODUCT`, etc.) to default GL accounts (Inventory, COGS/Expense, Sales Revenue). This decouples the accounting logic from the product definitions, allowing for flexible configuration.
- **Business Logic:**
    - The `clean()` method enforces that any product type that can be sold (`FINAL_PRODUCT`) must have a `sales_revenue_account` defined.

### Class: `GeneralAccountingSettings`
- **Description:** A singleton model that acts as a central registry for critical, system-wide accounts (e.g., A/P, A/R, WIP, GRNI). This is a crucial design pattern that eliminates hard-coded account codes from the business logic (services), making the system highly configurable and maintainable.
- **Design Pattern:** Singleton. The `save()` method prevents the creation of more than one instance, and the `load()` classmethod provides a convenient, cached way to access the single settings object.
- **Integration Points:** This model is referenced by nearly every service that creates a financial transaction to look up the correct GL account for a given process (e.g., posting an invoice, consuming materials for production, paying a supplier).
