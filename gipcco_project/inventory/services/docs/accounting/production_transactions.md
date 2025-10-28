# File: gipcco_project/inventory/services/accounting/production_transactions.py
- **Purpose:** Manages the creation of journal entries for all stages of the production lifecycle, from raw material consumption to the receipt of finished goods.

### Functions:

- `create_je_for_production_consumption(batch: Batch)`:
  - **Description:** Creates a journal entry to move the value of consumed raw materials from inventory into the production process.
  - **Accounting Logic:**
    - **Debit:** Work-in-Progress (WIP) Inventory account.
    - **Credit:** The respective inventory accounts for each raw material consumed.
  - **Key Features:**
    - Aggregates costs from all items in a batch into a single, consolidated journal entry.
    - If an item's cost is missing, it calculates it on-the-fly to prevent errors.
    - Links the final product as a sub-ledger to the WIP line for traceability.
  - **Behavioural details:**
    - Performs pre-checks: returns early (no JE) if the batch has no items or if a JE already exists for that batch.
    - Calls `_check_period_is_open(batch.creation_date)` and will raise if the period is closed.
    - Aggregates credit lines by inventory account (multiple raw-material accounts result in separate credit lines grouped by account).
    - If the calculated total consumption cost is zero or negative, no JE is created (the function returns `None`).
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`, and `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt)`:
  - **Description:** Creates a journal entry to transfer the value of completed goods from the production process into sellable inventory.
  - **Accounting Logic:**
    - **Debit:** Finished Goods Inventory account.
    - **Credit:** Work-in-Progress (WIP) Inventory account.
  - **Key Features:**
    - Triggered upon the creation of a `FinishedProductReceipt`.
    - Ensures the value transfer occurs in an open financial period.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_production_return(prod_return: ProductionReturn)`:
  - **Description:** Creates a journal entry to account for unused raw materials that are returned from the production floor to the warehouse.
  - **Accounting Logic:**
    - **Debit:** The specific Raw Material Inventory account.
    - **Credit:** Work-in-Progress (WIP) Inventory account.
  - **Key Features:**
  - Calculates the value of the returned materials based on the Moving Average Cost at the time of return.
  - Reverses the value transfer that occurred during consumption.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`, and `get_inventory_state_at_datetime()` from `costing_service.py`.

    - **Behavioural details:**
      - Computes the MAC at the `prod_return.return_date` using `get_inventory_state_at_datetime` and derives the return value as `quantity * mac_before_return`, quantized to 3 decimal places.
      - If the resulting return value is zero or negative it will not create a JE.
      - Uses `GeneralAccountingSettings` to obtain WIP and inventory accounts; missing configuration will raise a clear error.

- `create_je_for_production_supplemental_issue(item: BatchItem)`:
  - **Description:** Creates a specific, auditable journal entry for a single supplemental item added to a production batch. This is used for correcting material usage without altering the original consumption JE.
  - **Accounting Logic:**
    - **Debit:** Work-in-Progress (WIP) Inventory account.
    - **Credit:** The specific Raw Material Inventory account.
  - **Key Features:**
    - Creates a separate JE linked directly to the `BatchItem` for clear traceability.
    - Ensures the cost is added to WIP in the correct, open financial period.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.
