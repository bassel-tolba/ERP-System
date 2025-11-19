<!-- gipcco_project/inventory/views/docs/finished_products.md -->
<!-- gipcco_project/inventory/views/finished_products.py -->
# File: gipcco_project/inventory/views/finished_products.py
- **Purpose:** Provides the UI layer for managing the finished goods lifecycle. This includes a status dashboard, receiving goods from production, quality control release, viewing receipt details, and handling cancellations.

### Architectural Pattern
- **Thin View, Fat Service:** These views delegate all significant business logic, especially costing and state management, to the `finished_product_service`. The views are responsible for request handling, pre-validation, and rendering.

### Functions

- `finished_goods_status(request)`:
  - **Description:** Renders a dashboard that provides a comprehensive overview of the finished goods pipeline.
  - **Workflow:**
    1.  Calls a single service function to get all necessary data in a structured format.
    2.  Passes the data to the template for rendering.
  - **Calls:** `finished_product_service.get_finished_goods_status_data()` from `gipcco_project/inventory/services/finished_product_service.py`.

- `release_from_quarantine(request, pk)`:
  - **Description:** A POST-only view that transitions a `FinishedProductReceipt` from `QUARANTINED` to `RELEASED`, making the stock available for sale.
  - **Workflow:**
    1.  Fetches the specific `FinishedProductReceipt`.
    2.  Calls the service to perform the status change and any associated logic (like setting the `release_date`).
  - **Calls:** `finished_product_service.release_receipt_from_quarantine()` from `gipcco_project/inventory/services/finished_product_service.py`.

- `receive_finished_product(request, batch_pk, individual_batch_number)`:
  - **Description:** Handles the form for recording the receipt of finished goods from an `IN_PROGRESS` production plan.
  - **Validation (View-Level):** This view performs critical pre-validation before calling the service:
    1.  Ensures receipts are not created against `continuation_batches`.
    2.  Ensures the parent `Batch` is in the `IN_PROGRESS` state.
    3.  Ensures all associated `continuation_batches` have also been started (`IN_PROGRESS` or beyond) to guarantee accurate cost calculation.
  - **Workflow (POST):**
    1.  Extracts receipt data and sub-batch (e.g., pallet) details from `request.POST`.
    2.  Calls `finished_product_service.create_finished_product_receipt` to perform the core logic of cost calculation, record creation, and parent batch status updates.
    3.  The service call triggers a `post_save` signal on the `FinishedProductReceipt` model, which in turn calls the `accounting_service` to create the WIP-to-Finished-Goods journal entry.
  - **Calls:**
    - `finished_product_service.get_proportional_cost_for_receipt()` (on GET)
    - `finished_product_service.create_finished_product_receipt()` (on POST)

- `view_finished_product(request, pk)`:
  - **Description:** Displays the details of a single `FinishedProductReceipt`.
  - **Business Logic:** A key feature is providing a detailed cost breakdown, showing how the total cost is aggregated from the main production plan and all its continuation batches.
  - **Calls:** `finished_product_service.get_finished_product_cost_breakdown()` from `gipcco_project/inventory/services/finished_product_service.py`.

- `cancel_finished_product_receipt_view(request, pk)`:
  - **Description:** A POST-only view that triggers the non-destructive cancellation of a finished goods receipt.
  - **Workflow:**
    1.  Fetches the `FinishedProductReceipt` and extracts the justification from the form.
    2.  Calls `finished_product_service.cancel_finished_product_receipt`, which handles validation (e.g., cannot cancel if sold), status changes, and creation of a reversing journal entry.
  - **Calls:** `finished_product_service.cancel_finished_product_receipt()` from `gipcco_project/inventory/services/finished_product_service.py`.