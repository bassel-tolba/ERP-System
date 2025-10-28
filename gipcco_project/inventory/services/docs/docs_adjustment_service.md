# File: gipcco_project/inventory/services/adjustment_service.py

- **Purpose:** Manages the lifecycle of inventory counts and the creation of inventory adjustments.

## Functions

- `start_inventory_count(product_ids: List[int], reason: str, user: User, include_quarantined: bool)`:
  - **Description:** Initiates a new physical inventory count event.
  - **Workflow:**
    1. Creates an `InventoryCount` header record.
    2. For each specified product, it snapshots the current system quantity by calling `get_inventory_state_at_datetime`.
    3. Creates `InventoryCountItem` records with the snapshot quantity.
  - **Calls:** `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_adjustments_from_form(count_item_id: int, allocations: List[dict], reason: str, notes: str)`:
  - **Description:** Creates granular `InventoryAdjustment` records in `DRAFT` status based on manual allocation from the user.
  - **Workflow:**
    1. Deletes any pre-existing `DRAFT` adjustments for the item to prevent duplication.
    2. Iterates through user-provided allocations to create new `InventoryAdjustment` records, linking them to the specific source log or receipt.
    3. If the cost cannot be determined from the source, it calculates the current moving average cost as a fallback.
  - **Implementation notes:**
    - The service intentionally removes existing `DRAFT` adjustments for the same `inventory_count` and `product` before creating new ones to avoid duplicate draft entries.
    - Created adjustments are initially `DRAFT` so that the UI or finalization step can review allocations before they are `POSTED`.

- `auto_distribute_finished_good_shortage(count_item_id: int, reason: str, notes: str, receipt_ids: List[int])`:
  - **Description:** Automatically creates `DRAFT` negative adjustments for a finished good shortage, distributing the shortage proportionally across selected receipts.
  - **Workflow:**
    1. Deletes any pre-existing `DRAFT` adjustments for the same `inventory_count` and `product` to avoid duplication.
    2. Uses a robust subquery-based approach (two `Subquery` aggregations with `Coalesce` into `FloatField`) to compute for each `FinishedProductReceipt` the correct `remaining_quantity = total_quantity_produced - total_dispatched + total_adjusted` while preventing join multiplication and over-counting.
    3. Filters out receipts with effectively zero remaining stock (thresholded at `> 0.001`) and orders by `release_date` (oldest first) when selecting receipts; although the method name previously implied LIFO, the implementation distributes from oldest receipts (FIFO) when ordering by release_date.
    4. If the total available across selected receipts is less than the shortage quantity the function raises a `ValidationError` explaining the shortfall.
    5. The shortage is distributed proportionally across the selected receipts' remaining quantities. The code builds an `adjustments_to_make` mapping and converts computed floats to `Decimal` with quantization at 3 decimal places for safe accounting.
    6. Creates `DRAFT` `InventoryAdjustment` records for each proportionate share and links them to the appropriate `FinishedProductReceipt` (via `source_finished_product_id`) so the origin is auditable.
    7. The function deletes `DRAFT` adjustments again just before creating new ones as an extra safety guard to ensure idempotence in concurrent flows.

- `finalize_inventory_count(count_id: int)`:
  - **Description:** **REDEFINED:** Finalizes an inventory count by changing the status of all its `DRAFT` adjustments to `POSTED`.
  - **Workflow:**
    1. Finds all `InventoryAdjustment` records linked to the count that are in `DRAFT` status.
    2. Updates their status to `POSTED`. This action relies on a `post_save` signal on the `InventoryAdjustment` model to trigger the creation of the corresponding financial journal entries.
    3. **CRITICAL:** This function no longer calls the cost recalculation service, adhering to the immutable ledger principle.
  - **Notes & safety:**
    - Finalization is the point at which financial JEs are created via model signals; the service intentionally avoids performing cost history mutation itself.
    - All numeric quantities created by the auto-distribution logic are stored using `Decimal`-quantized values to three decimal places to remain consistent with other inventory calculations.
