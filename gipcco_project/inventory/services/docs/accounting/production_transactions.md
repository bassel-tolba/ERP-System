<!-- gipcco_project/inventory/services/docs/accounting/production_transactions.md -->
# File: gipcco_project/inventory/services/accounting/production_transactions.py
- **Purpose:** Manages the creation of journal entries for all stages of the production lifecycle, from raw material consumption to the receipt of finished goods, using the `JournalEntryBuilder`.

### Functions:

- `create_je_for_production_consumption(batch: Batch)`:
  - **Description:** Creates a journal entry to move the value of consumed raw materials from inventory into the production process.
  - **Accounting Logic:**
    - **Debit:** Work-in-Progress (WIP) Inventory account.
    - **Credit:** The respective inventory accounts for each raw material consumed.
  - **Key Features:**
    - Aggregates costs from all items in a batch into a single, consolidated journal entry.
    - If an item's cost is missing, it calculates it on-the-fly to prevent errors.
    - The `JournalEntryBuilder` handles period validation, balance checks, and duplicate prevention.
  - **Calls:** `_get_product_inventory_account()` from `_helpers.py`, and `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt)`:
  - **Description:** Creates a journal entry to transfer the value of completed goods from the production process into sellable inventory.
  - **Accounting Logic:**
    - **Debit:** Finished Goods Inventory account.
    - **Credit:** Work-in-Progress (WIP) Inventory account.
  - **Key Features:**
    - Triggered upon the creation of a `FinishedProductReceipt`.
    - The `JournalEntryBuilder` ensures the value transfer occurs in an open financial period.

- `create_je_for_production_return(prod_return: ProductionReturn)`:
  - **Description:** Creates a journal entry to account for unused raw materials that are returned from the production floor to the warehouse.
  - **Accounting Logic:**
    - **Debit:** The specific Raw Material Inventory account.
    - **Credit:** Work-in-Progress (WIP) Inventory account.
  - **Key Features:**
    - Calculates the value of the returned materials based on the Moving Average Cost at the time of return.
    - The `JournalEntryBuilder` handles the creation of the reversing JE.
  - **Calls:** `_get_product_inventory_account()` from `_helpers.py`, and `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_je_for_production_supplemental_issue(item: BatchItem)`:
  - **Description:** Creates a specific, auditable journal entry for a single supplemental item added to a production batch. This is used for correcting material usage without altering the original consumption JE.
  - **Accounting Logic:**
    - **Debit:** Work-in-Progress (WIP) Inventory account.
    - **Credit:** The specific Raw Material Inventory account.
  - **Key Features:**
    - Creates a separate JE linked directly to the `BatchItem` for clear traceability.
    - The `JournalEntryBuilder` ensures the cost is added to WIP in the correct, open financial period.
  - **Calls:** `_get_product_inventory_account()` from `_helpers.py`.