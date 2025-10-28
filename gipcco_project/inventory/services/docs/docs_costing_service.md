# File: gipcco_project/inventory/services/costing_service.py
- **Purpose:** Provides services to calculate historical inventory states and recalculate moving average costs for products.

- `get_inventory_state_at_datetime(product_id, target_datetime, include_quarantined)`: Calculates the total quantity and value of a product's inventory up to a specific point in time.
  - Aggregates inflows from `InventoryLog` (receipts), `FinishedProductReceipt` (production), and `ProductionReturn` (returns from production).
  - Aggregates outflows from `BatchItem` (production consumption), `InventoryConsumption` (internal use), and `FinishedProductDispatch` (sales).
  - Accounts for both positive and negative `InventoryAdjustment` transactions.
  - Returns a dictionary containing the final calculated `quantity` and `value`.

- `recalculate_cost_history_for_product(product_id, start_datetime)`: **REDEFINED:** A non-destructive calculator that re-computes a product's current `moving_average_cost` based on its transaction history.
  - **CRITICAL:** This function **no longer modifies historical outflow records** (like `cost_at_consumption`). Its only write operation is to update the `moving_average_cost` field on the `Product` model itself.
  - It is used to ensure the product's cost is accurate for *future* transactions after a historical event (like a landed cost allocation) has been posted.
  - **Calls:** `get_inventory_state_at_datetime()` from the current file.

- Implementation notes (current behavior):
  - Enforces period-safety by calling `_check_period_is_open(start_datetime.date())` before performing the recalculation.
  - Runs as a non-destructive calculation wrapped in a transaction; it only writes the new `moving_average_cost` to the `Product` record.
  - Designed to be triggered after historical corrections (e.g. reversing a JE, landed-cost postings) so that future transactions use the corrected MAC while preserving ledger immutability.

- `get_inventory_state_at_datetime` additional details:
  - Final products are calculated from `FinishedProductReceipt` rows rather than raw `InventoryLog` rows (those are ignored for final products).
  - Uses aggregation and `Coalesce` to produce robust `quantity` and `value` results and quantizes results to 3 decimal places.
  - Correctly accounts for VAT treatment (capitalized VAT is included in the inflow value expression) and excludes rejected/scrapped/voided logs when `include_quarantined=False`.
  - For finished goods it aggregates `total_quantity_produced` and `total_cost + allocated_overhead_cost` from receipts.
  - Outflows (consumptions, internal use, dispatches) are aggregated with `Decimal`-safe expressions to compute the running value used for MAC calculations.
