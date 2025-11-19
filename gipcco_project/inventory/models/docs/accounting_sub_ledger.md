# File: gipcco_project/inventory/models/accounting_sub_ledger.py
**Purpose:** This file defines the detailed data models that act as sub-ledgers for key control accounts, primarily Accounts Payable (A/P) and Accounts Receivable (A/R). These models track the transactional details behind the summary balances in the General Ledger.

### Class: `SupplierInvoice`
- **Description:** Represents a bill received from a supplier. It is the primary document in the Accounts Payable sub-ledger, tracking the amount owed, due date, and payment status for each supplier bill.
- **Key Fields & Relationships:**
    - `supplier`: Links to the `Company` model, identifying who is owed money.
    - `status`: A state machine (`Draft`, `Awaiting Payment`, `Partially Paid`, `Paid`, `Cancelled`) that tracks the invoice's lifecycle.
    - `actual_subtotal`, `actual_vat`: Fields that capture the values directly from the physical supplier invoice, enabling the three-way match process (PO vs. Receipt vs. Invoice).
    - `journal_entry`: A foreign key to the `JournalEntry` created when the invoice is officially posted, providing a direct audit trail to the General Ledger.
- **State Transitions & Business Logic:**
    - An invoice is created in `Draft` status.
    - Upon posting (via `purchasing_service.post_supplier_invoice`), its status moves to `Awaiting Payment`.
    - The `update_status()` method automatically transitions the status to `Partially Paid` or `Paid` as payments are applied.
- **Integration Points:**
    - **Upstream:** Linked to `InventoryLog` or `ExpenseLog` via `SupplierInvoiceItem`.
    - **Downstream:** Cleared by `Payment` records via the `PaymentApplication` linking table.

### Class: `SupplierInvoiceItem`
- **Description:** A line item on a `SupplierInvoice`. It provides the crucial link between a supplier's bill and the specific goods received (`InventoryLog`) or services rendered (`ExpenseLog`) that the bill is for.
- **Data Integrity:**
    - The `clean()` method enforces that a line item can be for either a goods receipt or an expense, but not both, ensuring transactional clarity.

### Class: `PaymentApplication`
- **Description:** A linking table that records the application of a specific amount from a `Payment` to a `SupplierInvoice`. This model is what reduces the `balance_due` on an invoice and is essential for accurate A/P aging.

### Class: `CustomerInvoice`
- **Description:** Represents a bill sent to a customer. It is the primary document in the Accounts Receivable sub-ledger, tracking the amount owed by a customer.
- **Key Fields & Relationships:**
    - `customer`: Identifies who owes the company money.
    - `status`: Tracks the invoice's payment lifecycle (`Draft`, `Awaiting Payment`, `Partially Paid`, `Paid`, `Cancelled`).
- **State Transitions & Business Logic:**
    - The `update_status()` method automatically updates the status as customer payments are applied.
- **Integration Points:**
    - **Upstream:** Created from `FinishedProductDispatch` records via `CustomerInvoiceItem`.
    - **Downstream:** Cleared by `Payment` records via `CustomerPaymentApplication` or by `CustomerCreditMemo` via `CustomerCreditMemoApplication`.

### Class: `CustomerInvoiceItem`
- **Description:** A line item on a `CustomerInvoice`, linking the invoice back to a specific `FinishedProductDispatch`. The `OneToOneField` ensures that a single dispatch cannot be invoiced more than once.

### Class: `CustomerPaymentApplication`
- **Description:** Records the application of a customer's `Payment` to a `CustomerInvoice`, reducing the A/R balance.

### Class: `CustomerCreditMemoApplication`
- **Description:** Records the application of a `CustomerCreditMemo` to a `CustomerInvoice`, reducing the amount the customer owes.

### Class: `CustomerCreditMemo`
- **Description:** Represents a credit issued to a customer, typically arising from a `SalesReturn`. It acts as a negative invoice, reducing the customer's outstanding balance in the A/R sub-ledger.
- **Key Fields & Relationships:**
    - `status`: Tracks how much of the credit has been used (`Open`, `Partially Applied`, `Applied`).
    - `unapplied_amount`: A calculated field that tracks the remaining value of the credit memo available to be applied to invoices.
    - `source_object`: A `GenericForeignKey` linking the credit memo back to its origin (e.g., a `SalesReturn`).
- **Business Logic:**
    - The `save()` method automatically calculates `total_amount` from `base_amount` and `vat_amount`.
    - The `update_status()` method is called after an application to recalculate the `unapplied_amount` and update the status accordingly.

### Class: `SalesReturn`
- **Description:** The header record for a customer return event. It groups all items being returned by a customer and tracks the overall status of the return process.
- **Key Fields & Relationships:**
    - `status`: A state machine (`Pending Inspection`, `Pending Processing`, `Completed`) that guides the physical return workflow.
    - `cogs_reversal_journal_entry`: A link to the single, consolidated JE that reverses the Cost of Goods Sold for the entire return, providing a clear financial audit trail.
- **Integration Points:**
    - A processed `SalesReturn` is the source for creating `InventoryAdjustment` records (for restocked/scrapped items) and a `CustomerCreditMemo` (for the financial credit).

### Class: `SalesReturnItem`
- **Description:** A line item on a `SalesReturn`, representing a specific product being returned.
- **Key Fields & Relationships:**
    - `original_dispatch`: A critical link back to the `FinishedProductDispatch` record from the original sale. This allows the system to retrieve the exact cost (COGS) that needs to be reversed.
    - `disposition`: The result of the inspection (`Return to Stock` or `Scrap`). This decision drives the subsequent inventory and financial transactions.

### Class: `BankTransfer`
- **Description:** Records the movement of funds between two internal `BankAccount` entities (e.g., from a main bank account to a petty cash box).
- **Key Fields & Relationships:**
    - `source_reconciliation`, `destination_reconciliation`: Separate fields to link the transfer to two different bank reconciliation events, as it will appear on both statements (one as a withdrawal, one as a deposit).
- **Data Integrity:**
    - The `clean()` method prevents a transfer from being created where the source and destination accounts are the same.

### Class: `DepreciationLog`
- **Description:** An audit and control model that records a single depreciation event for a specific `FixedAsset` in a specific month.
- **Data Integrity:**
    - The `unique_together = ('asset', 'period_date')` constraint is critical. It programmatically prevents the system from accidentally posting depreciation for the same asset twice in the same period.
- **Financial Impact:**
    - Creation of a `DepreciationLog` record (typically via the period-end service) triggers the creation of the corresponding depreciation `JournalEntry`.
