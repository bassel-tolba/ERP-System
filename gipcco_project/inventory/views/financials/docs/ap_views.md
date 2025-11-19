# File: gipcco_project/inventory/views/financials/docs/ap_views.md

- **Purpose:** This file contains views related to Accounts Payable (A/P), including supplier invoices and landed costs.

---

## `landed_cost_invoices(request)`

- **Purpose:** Lists all landed cost invoices with filtering options.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of landed cost invoices.

## `create_landed_cost_invoice(request)`

- **Purpose:** Handles the creation of a new DRAFT landed cost invoice.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the form for creating a landed cost invoice.

## `supplier_invoices(request)`

- **Purpose:** Lists all supplier invoices with filtering options.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of supplier invoices.

## `create_supplier_invoice(request)`

- **Purpose:** Handles the creation of a new DRAFT supplier invoice from unbilled receipts.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the form for creating a supplier invoice.

## `view_supplier_invoice(request, pk)`

- **Purpose:** Displays invoice details and handles payment application.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the supplier invoice.
- **Returns:** An HTTP response with the supplier invoice details.

## `post_supplier_invoice_view(request, pk)`

- **Purpose:** Handles the action of posting a single draft supplier invoice.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the supplier invoice.
- **Returns:** A redirect to the supplier invoice detail view.
- **Calls:** `accounting_service.post_supplier_invoice()`

## `allocate_landed_costs_view(request, pk)`

- **Purpose:** Handles adding a landed cost item and then triggering the allocation service.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the supplier invoice.
- **Returns:** A redirect to the supplier invoice detail view.
- **Calls:** `accounting_service.allocate_landed_costs()`

## `apply_payment_to_landed_cost_invoice_view(request, pk)`

- **Purpose:** Handles applying a payment to a landed cost invoice.
- **Args:**
  - `request`: The HTTP request object containing payment details (amount, bank account, date).
  - `pk`: The primary key of the landed cost invoice.
- **Returns:** A redirect to the landed cost invoice detail view.
- **Calls:** `purchasing_service.apply_payment_to_landed_cost_invoice()`

## `delete_supplier_invoice(request, pk)`

- **Purpose:** Deletes a supplier invoice, but only if no payments are applied.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the supplier invoice.
- **Returns:** A redirect to the supplier invoices list.

## `api_get_uninvoiced_receipts(request, supplier_id)`

- **Purpose:** API endpoint to get all 'Released' InventoryLogs for a supplier that have not yet been invoiced.
- **Args:**
  - `request`: The HTTP request object.
  - `supplier_id`: The primary key of the supplier.
- **Returns:** A JSON response with the list of uninvoiced receipts.

## `api_get_unsettled_expenses(request, supplier_id)`

- **Purpose:** API endpoint to get all approved, unsettled ExpenseLogs for a supplier.
- **Args:**
  - `request`: The HTTP request object.
  - `supplier_id`: The primary key of the supplier.
- **Returns:** A JSON response with the list of unsettled expenses.

## `apply_payment_to_invoice(request, invoice_pk)`

- **Purpose:** Creates a payment and applies it to a specific invoice.
- **Args:**
  - `request`: The HTTP request object.
  - `invoice_pk`: The primary key of the supplier invoice.
- **Returns:** A redirect to the supplier invoice detail view.
