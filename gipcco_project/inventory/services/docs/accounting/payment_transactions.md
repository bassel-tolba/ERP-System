# File: gipcco_project/inventory/services/accounting/payment_transactions.py
- **Purpose:** Manages journal entries related to all forms of cash movements, including payments to suppliers, receipts from customers, and employee advances.

### Functions:

- `create_je_for_supplier_payment(payment: Payment)`:
  - **Description:** Creates a journal entry when a payment is made to a supplier.
  - **Accounting Logic:**
    - **Debit:** Accounts Payable (reducing the liability owed to the supplier).
    - **Credit:** The specific Bank/Cash account from which the payment was made.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_customer_payment(payment: Payment)`:
  - **Description:** Creates a journal entry when a payment is received from a customer.
  - **Accounting Logic:**
    - **Debit:** The specific Bank/Cash account where the payment was received.
    - **Credit:** Accounts Receivable (if the payment is applied to specific invoices) OR Customer Deposits (if it is an on-account payment).
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_employee_advance(advance: EmployeeAdvance)`:
  - **Description:** Creates a journal entry when a cash advance is issued to an employee.
  - **Accounting Logic:**
    - **Debit:** Employee Advances Receivable (an asset representing money owed to the company).
    - **Credit:** The source Bank/Cash account.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_employee_advance_settlement(settlement: EmployeeAdvanceSettlement)`:
  - **Description:** Creates a journal entry to settle an outstanding employee advance.
  - **Accounting Logic (depends on the source of settlement):**
    - **Settlement via Expense:** Debits "Accrued Expenses" and credits "Employee Advances Receivable".
    - **Settlement via Direct Repayment:** Debits a "Cash" account and credits "Employee Advances Receivable".
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
