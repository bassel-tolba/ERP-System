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

- `auto_distribute_finished_good_shortage(count_item_id: int, reason: str, notes: str, receipt_ids: List[int])`:
  - **Description:** Automatically creates `DRAFT` negative adjustments for a finished good shortage, distributing the shortage proportionally across selected receipts.
  - **Workflow:**
    1. Deletes any pre-existing `DRAFT` adjustments.
    2. Uses a robust subquery-based approach to accurately calculate the remaining quantity on each `FinishedProductReceipt`.
    3. Distributes the total shortage quantity proportionally across the available stock of the selected receipts.
    4. Creates a `DRAFT` `InventoryAdjustment` for each receipt's share of the shortage.

- `finalize_inventory_count(count_id: int)`:
  - **Description:** **REDEFINED:** Finalizes an inventory count by changing the status of all its `DRAFT` adjustments to `POSTED`.
  - **Workflow:**
    1. Finds all `InventoryAdjustment` records linked to the count that are in `DRAFT` status.
    2. Updates their status to `POSTED`. This action relies on a `post_save` signal on the `InventoryAdjustment` model to trigger the creation of the corresponding financial journal entries.
    3. **CRITICAL:** This function no longer calls the cost recalculation service, adhering to the immutable ledger principle.
