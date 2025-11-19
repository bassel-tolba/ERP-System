# File: gipcco_project/inventory/models/expense_workflow.py
**Purpose:** Defines the models for a structured expense management workflow. This system separates the *request* for an expense from the final, *posted* expense log, allowing for an approval process before any financial impact occurs.

### Class: `ExpenseLog`
- **Description:** Represents a final, posted general expense. This record is created *after* an `ExpenseRequest` has been approved. It serves as a line item on a supplier invoice or as the source for a direct payment.
- **Key Fields & Relationships:**
    - `classification`: Categorizes the expense for high-level reporting (`Manufacturing Overhead` vs. `SG&A`).
    - `category`: Provides more granular categorization (`Salaries`, `Utilities`, `Rent`).
    - `cost_pool`: A crucial link that assigns the expense to a specific cost center for overhead allocation and departmental reporting.
    - `source_request`: A foreign key linking the final log back to the `ExpenseRequest` that initiated it, providing end-to-end traceability.
    - `settlement_status`: Tracks whether this expense has been paid (`Unsettled`, `Settled`).
    - `settlement_object`: A `GenericForeignKey` that points to the document that settled this expense (e.g., a `SupplierInvoice` or a `Payment`).
- **Financial Impact:**
    - The creation of an `ExpenseLog` typically triggers a journal entry to Debit an expense account (derived from the `cost_pool`) and Credit an "Accrued Expenses" liability account.

### Class: `ExpenseRequest`
- **Description:** Represents a formal request for an expenditure. This is the entry point into the expense workflow and must be approved before becoming an `ExpenseLog` or other financial transaction. It is a highly flexible model designed to handle many different types of expense scenarios.
- **Key Fields & Relationships:**
    - `status`: The core state machine for the approval workflow (`Pending`, `Approved`, `Rejected`, `Cancelled`).
    - `request_type`: A critical field that dictates the purpose and outcome of the request. The approval service uses this type to determine what kind of transaction to create (e.g., `DIRECT_EXPENSE` creates an `ExpenseLog`, `INVENTORY_EXPENSE` creates an `InventoryConsumption`, `INVOICE_PREPAID` creates a `PrepaidExpense`).
    - `settlement_method`: For direct expenses, this specifies how the expense will be paid (`Accrue and Pay Later` vs. `Direct Payment`). This choice determines the credit side of the resulting journal entry (Accrued Liability vs. Bank/Cash).
    - `supplier`, `bank_account`: Conditional fields required based on the chosen `settlement_method`.
- **User Journey:**
    1. A user creates an `ExpenseRequest` with a specific `request_type`.
    2. The request enters the `Pending` status.
    3. An authorized user approves or rejects the request.
    4. If approved, the `approval_service` reads the `request_type` and creates the appropriate downstream object (`ExpenseLog`, `InventoryConsumption`, `PrepaidExpense`, etc.), which then triggers its own financial journal entry.
