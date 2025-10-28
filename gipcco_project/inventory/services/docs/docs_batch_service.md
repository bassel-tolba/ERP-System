# File: gipcco_project/inventory/services/batch_service.py

- **Purpose:** Manages the complete lifecycle of production batches (shop orders), including creation, updates, and modifications.

## Functions

- `create_batch(...)`:
  - **Description:** Creates a new `Batch` and its associated `BatchItem` records.
  - **Workflow:**
    1. Validates that there is sufficient stock for all raw materials.
    2. Creates the `Batch` and `BatchItem` records.
    3. **Calls `recalculate_cost_history_for_product` to calculate the cost snapshot used for new `BatchItem.cost_at_consumption`.** Note: the current `recalculate_cost_history_for_product` implementation is non-destructive — it computes the appropriate MAC and updates the `Product.moving_average_cost`; cost snapshots used for a batch are calculated from historical state as needed.
    4. Calls `create_je_for_production_consumption` to create a single, consolidated journal entry for the entire consumption. If the total consumption cost is zero the JE is not created.
  - **Calls:** `validate_stock_availability()` from `batch_helpers.py`, `recalculate_cost_history_for_product()` from `costing_service.py`, `create_je_for_production_consumption()` from `accounting_service.py`.

- `update_batch(...)`:
  - **Description:** Updates an existing `Batch` and its items.
  - **Workflow:**
    1. Deletes the original journal entry associated with the batch.
    2. Updates the batch header and item details.
    3. Recalculates and updates the `cost_at_consumption` for all items (using `recalculate_cost_history_for_product` anchored at the batch creation timestamp).
    4. Re-creates the journal entry with the new, updated values.
  - **Calls:** `validate_stock_availability()` from `batch_helpers.py`, `recalculate_cost_history_for_product()` from `costing_service.py`, `create_je_for_production_consumption()` from `accounting_service.py`.

- `add_item_to_batch(...)`:
  - **Description:** **REDEFINED:** Adds a single supplemental item to an existing batch in an auditable, non-destructive way.
  - **Workflow:**
    1. Validates stock for the new item.
    2. Creates the new `BatchItem` record.
    3. Calls `recalculate_cost_history_for_product` to set the cost snapshot on the new item.
    4. **Calls `create_je_for_production_supplemental_issue` to create a separate, dedicated journal entry for just this addition.** This preserves the integrity of the original consumption JE — the supplemental JE is auditable and linked to the new `BatchItem`.
  - **Calls:** `validate_stock_availability()` from `batch_helpers.py`, `recalculate_cost_history_for_product()` from `costing_service.py`, `create_je_for_production_supplemental_issue()` from `accounting_service.py`.

- `delete_item_from_batch(...)`:
  - **Description:** Deletes an item from a batch and recreates the journal entry to reflect the reduced consumption value.

- `delete_batch(...)`:
  - **Description:** Deletes an entire batch and triggers a cost recalculation to reverse the financial impact of the consumption.
  - **Description:** Deletes an entire batch and triggers a cost recalculation to reflect the deletion's effect on product MACs (non-destructive to historical records).

Other notes:
- After batch creation/update the service calls `check_and_update_batch_customization` to handle product-specific customization hooks.
- Stock validation uses `validate_stock_availability` which can exclude the current batch during updates to avoid false positives.
