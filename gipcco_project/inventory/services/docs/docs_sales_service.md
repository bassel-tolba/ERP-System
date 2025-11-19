# File: gipcco_project/inventory/services/sales_service.py
- **Purpose:** Manages the complete sales workflow, from creating sales orders and dispatching goods to generating invoices and applying customer payments.

- `create_sales_order(customer_id, order_date, so_number, items, notes)`: Creates a new `SalesOrder` and its associated line items within a database transaction.
  - Validates customer existence and pre-fetches product data for efficiency.
  - Includes a placeholder for stock availability validation.
  - Creates the main `SalesOrder` record, then loops to create each `SalesOrderItem`.

- `dispatch_from_sales_order(sales_order_id, dispatch_date, dispatches)`: Creates dispatch records for items on a sales order, fulfilling the order.
  - Fetches and locks the `SalesOrder` to prevent race conditions.
  - **NEW:** Performs a robust, scalable stock availability check for all requested items *before* creating any dispatches by calling the authoritative `FinishedProductReceipt.objects.with_remaining_quantity()` manager method.
  - Calculates the cost for each dispatch at the time of the transaction.
  - Creates `FinishedProductDispatch` records for each item.
  - Automatically updates the parent `SalesOrder` status to `PARTIALLY_SHIPPED` or `COMPLETED`.
  - **Calls:** `get_inventory_state_at_datetime()` from `services/costing_service.py`.

- `create_invoice_from_dispatches(customer_id, invoice_number, invoice_date, due_date, dispatch_ids)`: Creates a `CustomerInvoice` from a list of `FinishedProductDispatch` records.
  - Validates that dispatches exist, are not already invoiced, and belong to the correct customer.
  - Calculates the total invoice amount from the dispatch data.
  - Creates the `CustomerInvoice` and links it to the dispatches via `CustomerInvoiceItem` records.

- `cancel_sales_order(sales_order: SalesOrder)`: Cancels a sales order by updating its status, but only if no items have been dispatched.

- `update_sales_order_item(so_item: SalesOrderItem, new_quantity: float)`: Updates the quantity of a sales order item, validating that the new quantity is not less than what has already been dispatched.

- `cancel_dispatch(dispatch: FinishedProductDispatch, user, justification: str)`: **REDEFINED:** Cancels a dispatch non-destructively.
  - Instead of deleting the record, it updates the dispatch's `status` to `CANCELLED`.
  - It creates a formal reversing journal entry via the correction service to ensure the financial impact is perfectly mirrored and the audit trail is complete.
  - **Calls:** `create_reversing_je_for_correction()` from `correction_transactions.py`.

- `apply_payment_to_invoices(payment: Payment, applications: List[Dict[str, any]])`: Applies a single customer payment to one or more outstanding invoices within a database transaction.
  - Validates that the total application amount does not exceed the payment's unapplied balance.
  - Fetches and locks invoice rows to prevent race conditions during application.
  - Validates that each application amount does not exceed the corresponding invoice's balance due.
  - Creates `CustomerPaymentApplication` records to link the payment and invoices.
  - Updates each invoice's paid amount and status.
