# File: gipcco_project/inventory/views/docs/receipts.md

- **Purpose:** This file contains the views related to the inventory receiving process, including the main dashboard for creating new receipts, managing the quarantine list, and voiding records.

## Functions

- `index(request)`:
  - **Description:** Renders the main dashboard page, which includes a form to create new inventory receipts (`InventoryLog`).
  - **On POST:**
    - It creates a new `InventoryLog` with a default status of `QUARANTINED`.
    - It handles both receipts linked to a `PurchaseOrderItem` and standalone receipts.
    - If linked to a PO, it calculates the `base_unit_price`, `vat_amount`, and `withholding_tax_amount` based on the PO item's data. It also handles logic for over-delivery where the excess is free.
    - After creating the log, it calls `purchasing_service.update_po_status_after_receipt` to ensure the PO's status is updated correctly.

- `records(request)`:
  - **Description:** Displays a comprehensive list of all `InventoryLog` records. It supports filtering by status.

- `quarantine_list(request)`:
  - **Description:** Shows a dedicated view of all inventory receipts that are currently in the `QUARANTINED` status, awaiting inspection and release.

- `release_from_quarantine(request, pk)`:
  - **Description:** Handles the action of releasing an item from quarantine.
  - **On POST:**
    - It updates the `InventoryLog`'s status to `RELEASED`.
    - It saves the Quality Control number (`qc_no`) and the `release_timestamp`.
    - **Crucially, it triggers the `costing_service.recalculate_cost_history_for_product` function to update the product's cost history now that a new receipt has been officially added to stock.**
  - **Guard:** Prevents setting a release date that is earlier than the original receipt date.

- `void_record_view(request, pk)`:
  - **Description:** Handles the user request to void an inventory receipt from the UI.
  - **On POST:**
    - It calls the `purchasing_service.void_inventory_receipt` service function, passing the log entry, user, and a justification.
    - It catches and displays any `ValidationError` or `PermissionError` raised by the service (e.g., trying to void a consumed receipt).
