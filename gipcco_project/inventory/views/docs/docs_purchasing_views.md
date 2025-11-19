<!-- gipcco_project/inventory/views/docs/purchasing_views.md -->
<!-- gipcco_project/inventory/views/purchasing_views.py -->
# File: gipcco_project/inventory/views/purchasing_views.py
- **Purpose:** Provides the user interface (UI) layer for managing the supplier return workflow. These views handle HTTP requests, delegate all business logic to the `purchasing_service`, and render templates for creating, viewing, and processing purchase returns and their associated debit memos.

### Architectural Pattern
- **Thin View, Fat Service:** These views are intentionally kept "thin." Their primary responsibilities are:
    1.  Authenticating and authorizing the user via `@permission_required` decorators.
    2.  Parsing incoming `request.POST` data.
    3.  Calling the appropriate function in the `purchasing_service` to execute business logic.
    4.  Handling exceptions from the service layer and displaying user-friendly messages.
    5.  Rendering the correct full-page or partial HTML template.
- All complex validation, state transitions, and financial transaction creation are handled exclusively by the service layer, ensuring a clear separation of concerns.

### Functions

- `purchase_returns_list(request)`:
  - **Description:** Displays a list of all `PurchaseReturn` records.
  - **Integration Points:** Renders the `purchase_returns_list.html` template or the `partials/purchase_returns_list_content.html` partial for HTMX requests.
  - **Security:** Requires the `inventory.view_purchasereturn` permission.

- `create_purchase_return(request)`:
  - **Description:** Handles both displaying the creation form (GET) and processing the submission (POST) for a new supplier return.
  - **Workflow (POST):**
    1.  Extracts supplier, date, notes, and a list of returned items (receipt IDs and quantities) from `request.POST`.
    2.  Packages the data into `return_data` and `items_data` dictionaries.
    3.  Calls the `purchasing_service.create_purchase_return` function to execute the core business logic.
    4.  Catches `ValidationError` from the service to display specific error messages to the user.
    5.  On success, redirects the user to the detail view for the newly created return.
  - **Calls:** `purchasing_service.create_purchase_return()` from `gipcco_project/inventory/services/purchasing_service.py`.
  - **Security:** Requires the `inventory.add_purchasereturn` permission.

- `view_purchase_return(request, pk)`:
  - **Description:** Displays the detailed view of a single `PurchaseReturn`, including its items and the status of its associated debit memo.
  - **Integration Points:** Renders the `purchase_return_view.html` template or its partial equivalent.
  - **Security:** Requires the `inventory.view_purchasereturn` permission.

- `process_inventory_return_view(request, pk)`:
  - **Description:** A POST-only view that triggers the inventory processing step of a return. This is the point where stock is removed from the system.
  - **Workflow:**
    1.  Fetches the `PurchaseReturn` object.
    2.  Calls `purchasing_service.process_inventory_return` to create the necessary `InventoryAdjustment` records.
    3.  The creation of the financial journal entry is handled by signals triggered from the `InventoryAdjustment` model, not directly by this view or service.
    4.  Redirects back to the detail view.
  - **Calls:** `purchasing_service.process_inventory_return()` from `gipcco_project/inventory/services/purchasing_service.py`.
  - **Security:** Requires the `inventory.change_purchasereturn` permission.

- `create_debit_memo_from_return_view(request, pk)`:
  - **Description:** A POST-only view that triggers the financial processing step of a return, creating the official `SupplierDebitMemo`.
  - **Workflow:**
    1.  Fetches the `PurchaseReturn` object.
    2.  Extracts memo number and date from `request.POST`.
    3.  Calls `purchasing_service.create_debit_memo_from_return` to create the debit memo and its associated journal entry (Debit A/P).
    4.  Redirects back to the detail view.
  - **Calls:** `purchasing_service.create_debit_memo_from_return()` from `gipcco_project/inventory/services/purchasing_service.py`.
  - **Security:** Requires the `inventory.add_supplierdebitmemo` permission.