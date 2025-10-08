# File: gipcco_project/inventory/views/expense_views.py
- **Purpose:** Provides a Django view to manage the lifecycle of expense requests, from creation and approval to correction and settlement.

- `manage_expense_requests(request)`: A single view that handles both displaying data (GET) and processing actions (POST) for expense requests.
  - On a `POST` request, it routes logic based on an 'action' parameter to create, approve, reject, cancel, correct, or settle requests.
    - The 'create' action further branches based on the request type (e.g., direct expense, inventory capitalization, accrual), calling a specific service function for each.
    - Other actions like 'approve' or 'reject' call the appropriate service functions.
    - A `try/except` block catches validation, permission, and other errors, displaying them to the user.
  - On a `GET` request, it fetches pending and processed requests, unsettled accruals, and related data to populate the management page.
  - **Calls:** `request_direct_expense()`, `request_inventory_expense()`, `request_inventory_capitalization()`, `request_inventory_prepaid()`, `request_prepaid_from_invoice()`, `request_accrual()`, `cancel_pending_request()`, `correct_approved_request()`, `settle_accrual()` from `services/expense_service.py`, and `approve_request()`, `reject_request()` from `services/approval_service.py`.