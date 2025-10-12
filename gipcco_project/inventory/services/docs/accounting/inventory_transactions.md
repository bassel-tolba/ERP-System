# File: gipcco_project/inventory/services/accounting/inventory_transactions.py
- **Purpose:** Handles the creation of journal entries related to core inventory movements, such as receipts from suppliers and internal adjustments.

### Functions:

- `create_je_for_inventory_adjustment(adjustment: InventoryAdjustment)`:
  - **Description:** Creates a journal entry to reflect the financial impact of an inventory adjustment.
  - **Accounting Logic:**
    - **Shortage (Negative Quantity):** Debits an "Inventory Adjustment Loss" account and credits the specific "Inventory" account.
    - **Overage (Positive Quantity):** Debits the specific "Inventory" account and credits an "Inventory Adjustment Gain" account.
  - **Key Features:**
    - Prevents duplicate journal entry creation.
    - Verifies that the adjustment date falls within an open financial period.
    - Uses the appropriate loss account for damaged goods vs. other reasons.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.

- `create_je_for_inventory_receipt(inventory_log: InventoryLog)`:
  - **Description:** Creates a comprehensive, balanced journal entry for a released inventory receipt from a supplier.
  - **Accounting Logic:**
    - **Debit:** Inventory account (at the item's costing value).
    - **Debit:** VAT Receivable account (if VAT is recoverable).
    - **Credit:** Accounts Payable account (for the net amount owed to the supplier).
    - **Credit:** Withholding Tax Payable account (if applicable).
  - **Key Features:**
    - Only processes logs with a status of `RELEASED`.
    - Prevents duplicate journal entry creation.
    - Ensures the transaction is posted into an open financial period.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.
