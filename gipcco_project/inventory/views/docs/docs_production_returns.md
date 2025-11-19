<!-- gipcco_project/inventory/views/docs/production_returns.md -->
<!-- gipcco_project/inventory/views/production_returns.py -->
# File: gipcco_project/inventory/views/production_returns.py
- **Purpose:** Provides the UI for managing the return of unused raw materials from the production floor back into the warehouse. It handles the creation, listing, and cancellation of `ProductionReturn` records.

### Architectural Pattern
- **Thin View, Fat Service:** Adheres to the standard architectural pattern where views handle HTTP interactions and delegate all business logic (validation, state changes, triggering financial transactions) to the `production_returns_service`.

### Functions

- `production_returns(request)`:
  - **Description:** A multi-purpose view that lists existing production returns and handles the form submission for creating a new one.
  - **Workflow (POST):**
    1.  Extracts product, source log, quantity, date, and other details from `request.POST`.
    2.  Calls `production_returns_service.create_production_return` to execute the core business logic. This service validates that the return quantity is not excessive.
    3.  The service creates the `ProductionReturn` record, which triggers a `post_save` signal to create the journal entry (Debit Inventory, Credit WIP).
    4.  Handles `ValidationError` from the service and displays appropriate user feedback.
  - **Calls:** `production_returns_service.create_production_return()` from `gipcco_project/inventory/services/production_returns_service.py`.

- `cancel_production_return_view(request, pk)`:
  - **Description:** A POST-only view that triggers the non-destructive cancellation of a `ProductionReturn`.
  - **Workflow:**
    1.  Fetches the `ProductionReturn` object and extracts the justification.
    2.  Calls `production_returns_service.cancel_production_return`. This service validates that the returned stock hasn't already been re-consumed and then creates a reversing journal entry via the `accounting_service`.
    3.  Redirects back to the main list view.
  - **Calls:** `production_returns_service.cancel_production_return()` from `gipcco_project/inventory/services/production_returns_service.py`.