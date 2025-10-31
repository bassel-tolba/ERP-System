# File: gipcco_project/inventory/views/docs/api.md

- **Purpose:** This file documents the API endpoints used by the frontend to fetch data dynamically, populate form fields, and retrieve detailed information for various models without full page reloads.

## Functions

- `api_get_inventory_log_history(request, log_pk)`:
  - **Description:** Retrieves the complete transaction history for a single `InventoryLog`, including consumptions, production issues, adjustments, and returns.

- `get_used_qc_sources(request, product_pk)`:
  - **Description:** Fetches `InventoryLog` sources for a product that have been consumed in production and still have a quantity that can be returned.

- `api_get_batches_for_source_log(request, log_pk)`:
  - **Description:** Returns a list of all production `Batch`es that have consumed materials from a specific `InventoryLog`.

- `api_batch_details(request, batch_pk)`:
  - **Description:** Provides detailed information about a single `Batch`, including its template, final product, and a list of all its raw material items.

- `api_get_full_batch_analysis(request, batch_pk)`:
  - **Description:** Returns a comprehensive cost and production analysis for a completed `Batch`, including total raw material cost, total quantity produced, average cost per unit, and details of all finished product receipts.

- `get_product_tags(request, product_id)`:
  - **Description:** Gets all `ProductTag`s associated with a specific product. If none are specifically linked, it returns all available tags as a fallback.

- `api_get_open_pos_for_supplier(request, supplier_id)`:
  - **Description:** Fetches all `PurchaseOrder`s for a given supplier that are still in `Pending` or `Partially_Received` status.

- `api_get_po_items(request, po_id)`:
  - **Description:** Returns the items of a specific `PurchaseOrder` that still have a remaining quantity to be received. It calculates this by subtracting the total received quantity from the quantity ordered.

- `api_get_sellable_stock(request)`:
  - **Description:** Retrieves all `FinishedProductReceipt`s that are `Released` and have a positive available quantity. It uses a robust subquery-based calculation to accurately determine the available stock by accounting for all dispatches and adjustments, avoiding common ORM join issues.

- `api_get_unallocated_landed_cost_invoices(request)`:
  - **Description:** Fetches all `LandedCostInvoice`s that are in the `Awaiting Allocation` status, ready to be allocated to inventory receipts.

- `api_get_receipts_for_allocation(request)`:
  - **Description:** Returns all `Released` `InventoryLog`s that have not yet had any landed costs allocated to them, making them candidates for allocation.

- `api_get_available_stock(request, product_pk)`:
  - **Description:** A corrected and robust endpoint to get all available stock for a given raw material or MRO product. It uses multiple subqueries to accurately calculate the remaining quantity on each `InventoryLog` by accounting for production consumption, internal consumption, returns, and adjustments.

- `api_get_stock_sources_for_product(request, product_id)`:
  - **Description:** Provides a detailed list of all stock sources for a product, whether it's a raw material (`InventoryLog`) or a finished good (`FinishedProductReceipt`). It uses the same robust subquery approach to ensure accurate remaining quantities for each source.

- `api_get_uninvoiced_receipts(request, supplier_id)`:
  - **Description:** Fetches all `Released` `InventoryLog`s for a specific supplier that have not yet been linked to a `SupplierInvoice`.

- `api_get_uninvoiced_dispatches(request, so_id)`:
  - **Description:** Returns all `FinishedProductDispatch`es for a specific `SalesOrder` that have not yet been included in a customer invoice.

- `api_get_unsettled_transactions(request, employee_id)`:
  - **Description:** Finds all `InventoryLog` and `ExpenseLog` transactions assigned to an employee that have not yet been used in an `EmployeeAdvanceSettlement`.

- `api_get_journal_entry_details(request, je_id)`:
  - **Description:** Retrieves the details of a single `JournalEntry`, including all of its lines with account information.

- `api_get_undispatched_so_items(request, so_id)`:
  - **Description:** Gets items from a `SalesOrder` that still have a remaining quantity to be dispatched.
