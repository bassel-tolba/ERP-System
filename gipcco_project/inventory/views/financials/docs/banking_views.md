# File: gipcco_project/inventory/views/financials/docs/banking_views.md

- **Purpose:** This file contains views related to banking, including bank accounts, transfers, and reconciliation.

---

## `bank_accounts_dashboard(request)`

- **Purpose:** Displays a list of bank accounts, their balances, and recent transactions.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the banking dashboard.

## `create_bank_account(request)`

- **Purpose:** Handles creation of a new bank account.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** A redirect to the banking dashboard.

## `edit_bank_account(request, pk)`

- **Purpose:** Handles editing an existing bank account.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank account.
- **Returns:** A redirect to the banking dashboard.

## `delete_bank_account(request, pk)`

- **Purpose:** Handles deleting a bank account.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank account.
- **Returns:** A redirect to the banking dashboard.

## `create_payment(request)`

- **Purpose:** Handles creation of a standalone payment.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** A redirect to the banking dashboard.

## `edit_payment(request, pk)`

- **Purpose:** Handles editing a standalone payment.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the payment.
- **Returns:** A redirect to the banking dashboard.

## `delete_payment(request, pk)`

- **Purpose:** Handles deleting a standalone payment.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the payment.
- **Returns:** A redirect to the banking dashboard.

## `bank_reconciliations_list(request)`

- **Purpose:** Lists all bank reconciliations with filtering.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of bank reconciliations.

## `create_bank_reconciliation(request)`

- **Purpose:** Handles the creation of a new bank reconciliation period.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the form for creating a bank reconciliation.

## `manage_bank_reconciliation(request, pk)`

- **Purpose:** Displays the main reconciliation workspace for matching transactions.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** An HTTP response with the reconciliation workspace.

## `delete_bank_reconciliation(request, pk)`

- **Purpose:** Deletes a bank reconciliation, but only if it is still open.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** A redirect to the bank reconciliations list.

## `api_unmatch_transaction(request, pk)`

- **Purpose:** API endpoint to unmatch a previously reconciled transaction.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** A redirect to the reconciliation workspace.

## `api_create_adjustment_and_match(request, pk)`

- **Purpose:** Creates a new journal entry for a bank adjustment and matches it to a statement line.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** A JSON response with the status of the operation.

## `api_match_transactions(request, pk)`

- **Purpose:** API endpoint to match a statement line with an internal transaction.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** A JSON response with the status of the operation.

## `finalize_reconciliation(request, pk)`

- **Purpose:** Marks a reconciliation as complete if the difference is zero.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the bank reconciliation.
- **Returns:** A redirect to the bank reconciliations list.
