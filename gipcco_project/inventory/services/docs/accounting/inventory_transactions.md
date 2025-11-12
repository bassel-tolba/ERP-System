<!-- gipcco_project/inventory/services/docs/accounting/inventory_transactions.md -->
# File: gipcco_project/inventory/services/accounting/inventory_transactions.py
- **Purpose:** Handles the creation of journal entries related to core inventory movements, such as receipts from suppliers and internal adjustments, using the `JournalEntryBuilder`.

### Functions:

- `create_je_for_inventory_adjustment(adjustment: InventoryAdjustment)`:
  - **Description:** Creates a journal entry to reflect the financial impact of an inventory adjustment. It contains distinct logic for standard adjustments versus those originating from a sales return.
  - **Accounting Logic (Standard):**
    - **Shortage:** Debits a "Loss/Expense" account and credits the "Inventory" account.
    - **Overage:** Debits the "Inventory" account and credits a "Gain" account.
  - **Accounting Logic (from Sales Return):**
    - **Return to Stock (Overage):** Debits "Inventory" and credits "Sales Returns Clearing".
    - **Scrap (Shortage):** Debits "Damaged Goods Expense" and credits "Sales Returns Clearing".
  - **Key Features:**
    - Uses `JournalEntryBuilder` to handle JE creation, period validation, and duplicate prevention.
  - **Calls:** `_get_product_inventory_account()` from `_helpers.py`.

- `create_je_for_inventory_receipt(inventory_log: InventoryLog)`:
  - **Description:** Creates a comprehensive, balanced journal entry for a released inventory receipt, capitalizing a prorated share of the PO's estimated landed costs.
  - **Accounting Logic:**
    - **Debit:** Inventory account (at the item's costing value, including prorated landed costs).
    - **Debit:** VAT Receivable account (if VAT is recoverable).
    - **Credit:** Goods Received, Not Invoiced (GRNI) account (a temporary liability).
    - **Credit:** Accrued Landed Costs account (for the estimated third-party costs).
    - **Credit:** Withholding Tax Payable account (if applicable).
  - **Key Features:**
    - Only processes logs with a status of `RELEASED`.
    - Uses `JournalEntryBuilder` to handle JE creation, period validation, and duplicate prevention.
    - Persists the calculated `costing_unit_price` and `landed_cost_component` back onto the `InventoryLog` for auditability.
  - **Calls:** `_get_product_inventory_account()` from `_helpers.py`.