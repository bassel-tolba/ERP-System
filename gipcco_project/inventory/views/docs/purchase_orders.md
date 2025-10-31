# File: gipcco_project/inventory/views/docs/purchase_orders.md

- **Purpose:** This file contains the views that handle the user interface for creating, viewing, editing, and deleting Purchase Orders. These views are responsible for rendering templates, processing form data, and calling the appropriate services to perform business logic.

## Functions

- `purchase_orders(request)`:
  - **Description:** Displays a list of all `PurchaseOrder`s. It supports search functionality by PO number or supplier name. It handles both full page loads and partial updates for HTMX requests.

- `create_purchase_order(request)`:
  - **Description:** Handles the rendering of the form to create a new `PurchaseOrder` and processes the POST request upon submission.
  - **On POST:**
    - It gathers all data from the form, including header details, line items, and estimated landed costs.
    - It structures this data into dictionaries and lists.
    - It calls the `purchasing_service.create_purchase_order` function to execute the creation logic.
    - Handles `ValidationError` and other exceptions, displaying appropriate error messages to the user.

- `view_purchase_order(request, pk)`:
  - **Description:** Displays a detailed view of a single `PurchaseOrder`.
  - **Key Features:**
    - It calculates display-centric values like total received quantity, remaining quantity, and total prices for each line item.
    - It calculates the estimated allocated landed cost for each item based on the PO-level estimates and the item's allocation percentage.
    - It gathers and displays a unique list of all `SupplierInvoice`s that are linked to any of the receipts associated with this PO.

- `edit_purchase_order(request, pk)`:
  - **Description:** Renders the form to edit an existing `PurchaseOrder` and processes the POST request.
  - **On POST:**
    - It gathers the updated data from the form.
    - It calls the `purchasing_service.update_purchase_order` function to perform the update.
    - It handles potential `PermissionDenied` errors if the user tries to edit a PO that has already been partially or fully received.

- `delete_purchase_order(request, pk)`:
  - **Description:** Handles the deletion of a `PurchaseOrder`.
  - **Guard:** It prevents deletion if any item on the PO has been received, ensuring data integrity.
