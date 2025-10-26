# File: gipcco_project/inventory/services/batch_helpers.py

- **Purpose:** Provides helper and utility functions specifically for the batch creation and management process.

## Functions

- `get_batch_form_context()`:
  - **Description:** A data preparation function that gathers all necessary information for rendering the batch creation user interface.
  - **Logic:**
    - Fetches all `ShopOrderTemplate` records.
    - Calculates the current available stock for all primitive products by aggregating all inflows and outflows (`BatchItem`, `InventoryConsumption`, `ProductionReturn`, `InventoryAdjustment`).
    - Returns a context dictionary containing templates, stock levels, and product lists, formatted for both Django templates and JSON consumption.

- `validate_stock_availability(...)`:
  - **Description:** A critical validation function that checks if sufficient inventory is available from specified source logs to fulfill a batch consumption.
  - **Logic:**
    1. Aggregates all requested quantities by their source `InventoryLog`.
    2. For each source log, it calculates the precise available quantity by subtracting all previous consumptions and adding any returns.
    3. It verifies that the requested quantity does not exceed the available stock.
    4. It also ensures the source log is `RELEASED` and its release date is not after the batch creation date.
  - **Returns:** A tuple `(bool, str)` indicating success or failure, with an error message if validation fails.

- `check_and_update_batch_customization(batch_id: int)`:
  - **Description:** A utility function that compares a batch's items against its source template to determine if it has been customized.
  - **Logic:** It checks if the number of items or the quantities differ between the `Batch` and its `ShopOrderTemplate`, updating the `is_customized` flag on the `Batch` record accordingly.
