# File: gipcco_project/inventory/models/bank_reconciliation.py
**Purpose:** This file defines the models required for the bank reconciliation process. These models allow users to match the company's internal transaction records (`Payment`, `BankTransfer`) against an imported bank statement, identifying outstanding items and ensuring the cash balance is accurate.

### Class: `BankReconciliation`
- **Description:** The header model for a single bank reconciliation event. It represents the reconciliation of one `BankAccount` for a specific period, defined by the `statement_date`. It holds the key summary figures from the bank statement.
- **Key Fields & Relationships:**
    - `bank_account`: The specific account being reconciled.
    - `statement_date`: The end date of the bank statement, which defines the reconciliation period.
    - `statement_opening_balance`, `statement_closing_balance`: The starting and ending balances as reported by the bank. These are the target numbers for the reconciliation.
    - `status`: Tracks the state of the reconciliation (`Open`, `Reconciled`).
- **Business Logic:**
    - `unmatch_all_transactions()`: A utility method to reset the reconciliation. It removes the link from all associated `Payment` and `BankTransfer` records, effectively "un-clearing" them and allowing the user to start the matching process over.
- **Data Integrity:**
    - `unique_together = ('bank_account', 'statement_date')`: A critical constraint that prevents more than one reconciliation from being created for the same bank account on the same date.

### Class: `BankStatementLine`
- **Description:** Represents a single transaction line imported from a physical or electronic bank statement. These are the external records that need to be matched against the system's internal records.
- **Key Fields & Relationships:**
    - `reconciliation`: Links the statement line to its parent `BankReconciliation` event.
    - `amount`: The value of the transaction. A positive value represents a deposit, and a negative value represents a withdrawal.
    - `is_reconciled`: A boolean flag indicating whether this line has been successfully matched to an internal transaction.
    - `reconciled_object`: A `GenericForeignKey` that points to the specific internal transaction (`Payment`, `BankTransfer`, etc.) that this statement line was matched against. This creates the explicit link between the bank's view and the system's view of a transaction.
