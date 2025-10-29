# `adjustments.py` Manifest

This file contains the Django views that handle the user interface and interactions for the inventory counting and adjustment process. These views connect the user's actions in the web interface to the business logic encapsulated in the `adjustment_service`.

## Key Views and Functionalities:

### 1. **`inventory_counts_list`**
   - **Purpose**: Displays a list of all past and present `InventoryCount` events.
   - **Functionality**: Retrieves all `InventoryCount` objects from the database and renders them in a template, providing an overview of all stock-taking activities.

### 2. **`create_inventory_count`**
   - **Purpose**: Provides the form for initiating a new inventory count and handles its submission.
   - **Functionality**:
     - **GET**: Renders a form where the user can select which `Product`s to include in the count and provide a `reason` for the event.
     - **POST**:
       - Receives the list of product IDs and the reason from the form.
       - Calls the `adjustment_service.start_inventory_count` function, passing the user, reason, and product list.
       - This service call creates the `InventoryCount` header and snapshots the current system quantities for each selected product.
       - Upon successful creation, it redirects the user to the `manage_inventory_count` workspace.

### 3. **`manage_inventory_count`**
   - **Purpose**: This is the main workspace for data entry during a physical count.
   - **Functionality**:
     - **GET**: Displays a form or "count sheet" listing all the `InventoryCountItem`s for the event. For each item, it shows the product name and the `system_quantity` that was snapshotted when the count began. It provides an input field for the user to enter the `counted_quantity`.
     - **POST**:
       - Receives the submitted form containing the physically counted quantities for each item.
       - It iterates through the items and updates the `counted_quantity` field on each `InventoryCountItem` record.
       - After saving the counted quantities, it updates the status of the parent `InventoryCount` to `PENDING_ALLOCATION`.
       - It then redirects the user to the `allocate_inventory_variances` view, where they will deal with any discrepancies.

### 4. **`allocate_inventory_variances`**
   - **Purpose**: This is the workspace where users address the discrepancies (variances) found during the count.
   - **Functionality**:
     - **GET**:
       - It displays only the `InventoryCountItem`s that have a non-zero `variance_quantity`.
       - For each variance, it provides tools for the user to decide how to handle it. This typically involves selecting the specific `InventoryLog` (for raw materials) or `FinishedProductReceipt` (for finished goods) that should be adjusted.
       - It fetches and provides the available stock sources for each product to the frontend, usually via an API call, so the user can make an informed decision.
     - **POST**:
       - This view handles multiple types of POST requests, often distinguished by a specific parameter in the request.
       - **Manual Allocation**: When a user manually assigns a variance to a specific stock source, this view calls the `adjustment_service.create_adjustments_from_form` function to create the `InventoryAdjustment` records in a `DRAFT` status.
       - **Automatic Allocation**: If the user chooses an automatic allocation method (like FIFO or LIFO for shortages), this view calls the corresponding service function (e.g., `adjustment_service.auto_allocate_variances`).
       - **Finalization**: When the user is finished with all allocations and wants to post the financial transaction, a POST request to this view will trigger the `adjustment_service.finalize_inventory_count` function. This service function is the final step that changes the `InventoryAdjustment` records to `POSTED`, which in turn triggers the creation of the journal entries.

These views provide a structured and user-friendly workflow for the complex process of physical inventory counting, from initiation to final financial posting.
