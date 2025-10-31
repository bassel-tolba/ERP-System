# File: gipcco_project/inventory/services/accounting/inventory_transactions.py
- **Purpose:** Handles the creation of journal entries related to core inventory movements, such as receipts from suppliers and internal adjustments.

### Functions:

- `create_je_for_inventory_adjustment(adjustment: InventoryAdjustment)`:
  - **Description:** Creates a journal entry to reflect the financial impact of an inventory adjustment. It contains distinct logic for standard adjustments versus those originating from a sales return.
  - **Accounting Logic (Standard):**
    - **Shortage:** Debits a "Loss/Expense" account and credits the "Inventory" account.
    - **Overage:** Debits the "Inventory" account and credits a "Gain" account.
  - **Accounting Logic (from Sales Return):**
    - **Return to Stock (Overage):** Debits the "Inventory" account and credits the "Sales Returns Clearing" account.
    - **Scrap (Shortage):** Debits the "Damaged Goods Expense" account and credits the "Sales Returns Clearing" account.
  - **Key Features:**
    - Prevents duplicate journal entry creation.
    - Verifies that the adjustment date falls within an open financial period.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.

- `create_je_for_inventory_receipt(inventory_log: InventoryLog)`:
  - **Description:** Creates a comprehensive, balanced journal entry for a released inventory receipt from a supplier, capitalizing a prorated share of the PO's estimated landed costs and accruing the liability to a temporary account.
  - **Accounting Logic:**
    - **Debit:** Inventory account (at the item's costing value, including prorated landed costs).
    - **Debit:** VAT Receivable account (if VAT is recoverable).
    - **Credit:** Goods Received, Not Invoiced (GRNI) account (a temporary liability).
    - **Credit:** Accrued Landed Costs account (for the estimated third-party costs).
    - **Credit:** Withholding Tax Payable account (if applicable).
  - **Key Features:**
    - Only processes logs with a status of `RELEASED`.
    - Prevents duplicate journal entry creation.
    - Ensures the transaction is posted into an open financial period.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.
