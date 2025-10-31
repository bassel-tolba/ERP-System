# File: gipcco_project/inventory/views/financials/docs/ar_views.md

- **Purpose:** This file contains views related to Accounts Receivable (A/R), including customer invoices and payments.

---

## `customer_invoices(request)`

- **Purpose:** Lists all customer invoices with filtering options.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of customer invoices.

## `create_customer_invoice(request)`

- **Purpose:** Handles creating a new customer invoice from a sales order.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the form for creating a customer invoice.

## `view_customer_invoice(request, pk)`

- **Purpose:** Displays invoice details and handles payment application.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the customer invoice.
- **Returns:** An HTTP response with the customer invoice details.

## `delete_customer_invoice(request, pk)`

- **Purpose:** Deletes a customer invoice, but only if no payments are applied.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the customer invoice.
- **Returns:** A redirect to the customer invoices list.

## `receive_payment_for_invoice(request, invoice_pk)`

- **Purpose:** Creates a payment received and applies it to a specific invoice.
- **Args:**
  - `request`: The HTTP request object.
  - `invoice_pk`: The primary key of the customer invoice.
- **Returns:** A redirect to the customer invoice detail view.

## `api_get_uninvoiced_dispatches(request, so_id)`

- **Purpose:** Returns dispatches for a sales order that are not yet on an invoice.
- **Args:**
  - `request`: The HTTP request object.
  - `so_id`: The primary key of the sales order.
- **Returns:** A JSON response with the list of uninvoiced dispatches.
