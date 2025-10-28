# File: gipcco_project/inventory/services/batch_service.py
- **Purpose:** Manages the lifecycle and business logic for production batches (shop orders).

- `create_batch`:
  - **NEW**: Creates a `Batch` in `DRAFT` status.
  - No longer creates journal entries or calculates costs. This is deferred until production starts.
  - Still performs stock validation to ensure the draft is feasible.

- `update_batch`:
  - **NEW**: Can only be called on batches in `DRAFT` status.
  - Performs a direct update of batch data and items, as no financial transactions have occurred yet.

- `submit_batch_for_approval`:
  - **NEW**: Moves a batch from `DRAFT` to `PENDING_APPROVAL`.
  - Records the user who submitted the batch.

- `approve_batch`:
  - **NEW**: Moves a batch from `PENDING_APPROVAL` to `APPROVED`.
  - Records the user who approved the batch.

- `reject_batch`:
  - **NEW**: Moves a batch from `PENDING_APPROVAL` back to `DRAFT`.
  - Allows for corrections before resubmission.

- `start_batch_production`:
  - **NEW**: This is the critical financial step.
  - Can only be called on an `APPROVED` batch.
  - Snapshots the `cost_at_consumption` for all batch items.
  - Creates the main production consumption journal entry.
  - Triggers the final recalculation of the moving average cost for consumed products.
  - Moves the batch status to `IN_PROGRESS`.

- `add_item_to_batch`:
  - If the batch is a `DRAFT`, it simply adds the new item.
  - If the batch is `IN_PROGRESS`, it adds the item, snapshots its cost, and creates a separate, auditable supplemental journal entry.

- `return_item_from_batch`:
  - Creates a `ProductionReturn` record to move a component from a batch back to inventory.
  - The post-save signal on `ProductionReturn` handles the JE creation and cost recalculation.

- `cancel_batch`:
  - If the batch was `IN_PROGRESS`, it creates a reversing journal entry and triggers cost recalculation.
  - If the batch was in a pre-production state (`DRAFT`, `PENDING_APPROVAL`, `APPROVED`), it simply marks it as `CANCELLED` with no financial impact.
