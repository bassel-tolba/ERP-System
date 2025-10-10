# File: inventory/services/expense_service.py
- **Purpose:** Provides a service layer for creating, reading, updating, and managing the lifecycle of `ExpenseRequest` objects.

- `_can_user_modify_request(user: User, request: ExpenseRequest)`: An internal helper that checks if a user has permission to modify a given expense request.

- `request_direct_expense(user, amount, request_date, description, cost_pool_id, category, classification)`: Creates an `ExpenseRequest` for a direct, non-inventory expense.

- `request_inventory_expense(user, product_id, quantity, request_date, description, cost_pool_id)`: Creates an `ExpenseRequest` for consuming an inventory item as an expense.

- `request_inventory_capitalization(user, product_id, quantity, request_date, description, fixed_asset_id)`: Creates an `ExpenseRequest` to consume an inventory item and capitalize its value into a fixed asset.

- `settle_employee_advance_with_expense(user, advance_id, expense_log_id, settlement_date)`: Settles an employee's cash advance using an approved `ExpenseLog`.
  - Validates that the advance is unsettled and the expense log has not already been used for settlement.
  - Creates an `EmployeeAdvanceSettlement` record.
  - **Updates the `ExpenseLog`'s `settlement_status` to `SETTLED` to prevent reuse.**
  - Relies on a `post_save` signal on the settlement model to create the corresponding journal entry.

- `request_inventory_prepaid(user, product_id, quantity, request_date, description, asset_account_id, expense_account_id, start_date, end_date)`: Creates an `ExpenseRequest` to consume an inventory item and record it as a prepaid asset for future amortization.

- `request_prepaid_from_invoice(user, invoice_id, description, asset_account_id, expense_account_id, start_date, end_date)`: Creates an `ExpenseRequest` to treat a supplier invoice as a prepaid expense.

- `request_accrual(user, amount, request_date, description, expense_account_id, start_date, end_date)`: Creates an `ExpenseRequest` to schedule a recurring expense accrual.

- `get_expense_request(request_id: int)`: Retrieves a single `ExpenseRequest` by its primary key.

- `query_expense_requests(filters: dict)`: Returns a QuerySet of `ExpenseRequest` objects based on a dictionary of filters.

- `update_pending_request(request_id: int, user: User, **data)`: Updates the data of an existing `ExpenseRequest` that is still in a 'PENDING' state.
  - **Calls:** `get_expense_request()`, `_can_user_modify_request()` from the current file.

- `link_invoice_to_prepaid(user: User, prepaid_asset_id: int, invoice_id: int)`: Adds a note to a `PrepaidExpense` record to link it to a specific supplier invoice for audit purposes.

- `settle_accrual(user: User, accrual_log_id: int, invoice_id: int)`: Settles a monthly accrual with an actual invoice, triggering a true-up journal entry.
  - **Calls:** `settle_accrual_with_invoice()` from `adjusting_entries_service.py`.

- `create_invoice_from_expense_logs(user: User, supplier_id: int, invoice_number: str, invoice_date: date, due_date: date, expense_log_ids: List[int])`: Creates a `SupplierInvoice` from one or more unsettled `ExpenseLog` records for the same supplier.
  - Marks the source `ExpenseLog` records as settled and links them to the new invoice.

- `settle_employee_advance_with_expense(user: User, advance_id: int, expense_log_id: int, settlement_date: date)`: Settles an employee's cash advance using an approved `ExpenseLog`.
  - Creates an `EmployeeAdvanceSettlement` record.
  - Creates a correcting journal entry to move the value from Accrued Expenses to Employee Advances Receivable.
  - Marks the source `ExpenseLog` as settled.

- `correct_approved_request(request_id: int, user: User, justification: str)`: Initiates the reversal of an already approved expense request and its associated financial transaction.
  - **Calls:** `correct_approved_expense()` from `accounting_service.py`.

- `cancel_pending_request(request_id: int, user: User)`: Cancels an `ExpenseRequest` that is still in a 'PENDING' state.
  - **Calls:** `get_expense_request()`, `_can_user_modify_request()` from the current file.