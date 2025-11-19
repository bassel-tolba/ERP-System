# File: gipcco_project/inventory/models/sub_ledger_banking.py
**Purpose:** This file defines models related to banking operations and introduces the `Employee` model as a sub-ledger for financial transactions involving staff, such as cash advances and settlements.

### Class: `BankAccount`
- **Description:** Represents a company bank account or a physical cash box/safe. It acts as the sub-ledger for cash and bank accounts in the General Ledger.
- **Key Fields & Relationships:**
    - `gl_account`: A `OneToOneField` to an `Account`. This creates a direct and mandatory link, ensuring that every defined `BankAccount` corresponds to exactly one cash account in the Chart of Accounts. This enforces structural integrity.

### Class: `Payment`
- **Description:** A versatile model representing any movement of cash, whether it's a payment made, a payment received, or an internal transfer.
- **Key Fields & Relationships:**
    - `payment_type`: A critical field (`out`, `in`, `transfer`, `other`) that determines the context and accounting treatment of the payment.
    - `supplier`, `customer`: Links the payment to the relevant A/P or A/R sub-ledger entity.
    - `source_object`: A `GenericForeignKey` providing a traceable link to the origin of the payment if it's part of a larger workflow (e.g., a `BankTransfer` record).
    - `reconciliation`, `cleared_date`: Fields used by the bank reconciliation process to mark this payment as "cleared" and link it to a specific `BankReconciliation` event.
- **Business Logic:**
    - `total_applied` and `unapplied_amount` properties provide real-time calculation of how much of the payment has been allocated to `SupplierInvoice` or `LandedCostInvoice` records.
    - Supports application to multiple invoice types via `PaymentApplication` (for standard A/P) and `LandedCostPaymentApplication` (for landed costs).

### Employee Sub-Ledger

#### Class: `Employee`
- **Description:** The master data model for an employee. In the financial context, it serves as the sub-ledger for employee-related accounts, such as "Employee Advances Receivable".
- **Business Logic:**
    - The properties (`total_advances`, `total_settled_from_advances`, `outstanding_advance_balance`) provide a live, calculated summary of the employee's financial standing with the company regarding cash advances, directly on the model.

#### Class: `EmployeeAdvance`
- **Description:** Records a single disbursement of funds to an employee, creating a receivable for the company. This is the core transactional model for the employee financial sub-ledger.
- **Key Fields & Relationships:**
    - `employee`: Links the advance to the specific employee.
    - `source_payment`: A `OneToOneField` to the `Payment` record that documents the actual cash outflow from a `BankAccount`, providing a complete audit trail from the advance request to the cash disbursement.
    - `status`: A state machine (`Open`, `Partially Settled`, `Settled`) tracking the lifecycle of the advance.
- **Business Logic:**
    - The `update_status()` method automatically transitions the status as settlement transactions are recorded against the advance.

#### Class: `EmployeeAdvanceSettlement`
- **Description:** A linking model that formally settles an `EmployeeAdvance` by connecting it to a justifying business transaction. This model closes the loop on an advance, proving how the funds were used.
- **Key Fields & Relationships:**
    - `advance`: The specific advance being settled.
    - `source_transaction`: A `GenericForeignKey` that points to the document justifying the expenditure, which could be an `ExpenseLog` (for a purchased service) or an `InventoryLog` (for goods purchased directly by the employee).
    - `journal_entry`: A link to the JE created upon settlement, which typically credits the "Employee Advances Receivable" account, clearing the employee's debt.
- **Financial Impact:**
    - The creation of a settlement triggers a journal entry to clear the receivable and correctly account for the expense or asset that was acquired with the advanced funds.
