# File: gipcco_project/inventory/services/sales_return_service.py
- **Purpose:** Handles the complete, multi-step workflow for customer returns, separating the physical/inventory processing from the financial crediting.

- `process_inspected_return(sales_return: SalesReturn)`: The primary inventory-side function for a return, executed after items have been inspected and assigned a disposition.
  - **Workflow:**
    1. Creates a single, consolidated journal entry to reverse the Cost of Goods Sold for all items in the return. This entry debits a temporary "Sales Returns Clearing" account and credits the COGS account(s).
    2. It then iterates through each `SalesReturnItem` and creates a corresponding `InventoryAdjustment` based on its disposition.
    3. If disposition is `RETURN_TO_STOCK`, a positive adjustment is created. The resulting JE will debit Inventory and credit the Clearing Account.
    4. If disposition is `SCRAP`, a negative adjustment is created. The resulting JE will debit a Damaged Goods Expense account and credit the Clearing Account.
  - This process ensures the clearing account is zeroed out, confirming that the total value of the reversed COGS has been fully accounted for as either returned stock or scrap.
  - **Calls:** `_check_period_is_open()`, `_get_product_expense_account()` from `services/accounting/_helpers.py`.

- `create_credit_memo_from_return(sales_return: SalesReturn, memo_number: str, memo_date: str)`: Creates a `CustomerCreditMemo` from a sales return, handling the financial (Accounts Receivable) side of the transaction. This is the final step after the inventory has been processed.
  - Calculates the total credit amount (base and VAT) from all items in the return.
  - Creates the `CustomerCreditMemo` record, which in turn triggers a signal to create the financial journal entry (debiting Sales Returns & Allowances and VAT Payable, crediting Accounts Receivable).
  - **Calls:** None. (Triggers `handle_credit_memo_save` signal).