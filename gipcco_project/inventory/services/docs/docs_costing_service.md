# File: gipcco_project/inventory/services/costing_service.py
- **Purpose:** Provides services to calculate historical inventory states and recalculate moving average costs for products.

- `get_inventory_state_at_datetime(product_id, target_datetime, include_quarantined)`: Calculates the total quantity and value of a product's inventory up to a specific point in time.
  - Aggregates inflows from `InventoryLog` (receipts), `FinishedProductReceipt` (production), and `ProductionReturn` (returns from production).
  - Aggregates outflows from `BatchItem` (production consumption), `InventoryConsumption` (internal use), and `FinishedProductDispatch` (sales).
  - Accounts for both positive and negative `InventoryAdjustment` transactions.
  - Returns a dictionary containing the final calculated `quantity` and `value`.

- `recalculate_cost_history_for_product(product_id, start_datetime)`: Re-evaluates and updates the moving average cost for all historical transactions of a product from a given start date.
  - Fetches the initial inventory state just before the `start_datetime`.
  - Gathers all subsequent inflow, outflow, and adjustment transactions from multiple models.
  - Sorts all transactions chronologically to create a unified event stream.
  - Iterates through the stream, recalculating the running cost at each step and updating the cost on each outflow record (e.g., `cost_at_consumption`).
  - Performs bulk updates on affected database records for efficiency.
  - Saves the final calculated moving average cost to the `Product` model.
  - **Calls:** `get_inventory_state_at_datetime()` from the current file.