# File: gipcco_project/inventory/services/sales_return_service.py
- **Purpose:** Handles the accounting and inventory adjustments required when a customer returns a sold product.

- `process_return_item(return_item: SalesReturnItem)`: Processes a single returned item by creating the necessary financial and inventory transactions within a database transaction.
  - Creates a journal entry to reverse the Cost of Goods Sold (COGS), debiting inventory and crediting the COGS account.
  - If the item's disposition is 'SCRAP', it creates an `InventoryAdjustment` record to write off the item's value, which in turn triggers its own journal entry.
  - **Calls:** `_get_product_expense_account()` from `services/accounting_service.py`.