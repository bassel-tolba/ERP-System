# File: inventory/services/approval_service.py
- **Purpose:** Provides services to approve or reject expense requests, which triggers the creation of the corresponding financial transactions like expense logs, inventory consumptions, or accruals.

- `_get_fifo_source_logs_for_consumption(product: inventory_models.Product, quantity_needed: Decimal)`: **ENHANCED:** Finds the oldest available `InventoryLog` records to satisfy a required quantity, implementing a true FIFO strategy that can draw from multiple source logs.
  - Calculates the remaining quantity for all available logs.
  - Returns a list of source logs and the specific quantity to consume from each to fulfill the total request.
  - Raises a `ValidationError` only if the *total* available inventory is insufficient.

- `_create_inventory_consumption_from_request(request: inventory_models.ExpenseRequest)`: Creates an `InventoryConsumption` record based on an approved expense request.
  - Determines the consumption type (Expense, Capitalize, or Amortize) from the request.
  - Uses a FIFO source log to determine the cost of the consumed item.
  - **Calls:** `_get_fifo_source_log()` from the current file.

- `_execute_approval(request: inventory_models.ExpenseRequest)`: A private dispatcher that creates the correct financial object based on the expense request type.
  - `DIRECT_EXPENSE`: Creates an `ExpenseLog`.
  - `INVOICE_PREPAID`: Creates a `PrepaidExpense`.
  - `INVENTORY_*`: Calls the creation of an `InventoryConsumption`.
  - `ACCRUAL`: Creates an `AccruedExpense`.
  - **Calls:** `_create_inventory_consumption_from_request()` from the current file.

- `approve_request(request_id: int, user)`: Approves a pending expense request, updating its status and creating the resulting financial transaction.
  - Checks that the request status is 'PENDING'.
  - Executes the main approval logic to create the transaction.
  - **Calls:** `_execute_approval()` from the current file.

- `reject_request(request_id: int, user, reason: str)`: Rejects a pending expense request, updating its status and recording the rejection reason.
  - Checks that the request status is 'PENDING'.
  - Requires a reason for the rejection.
