<!-- gipcco_project/inventory/services/docs/accounting/sales_transactions.md -->
# File: gipcco_project/inventory/services/accounting/sales_transactions.py
- **Purpose:** Handles the creation of journal entries related to customer sales and returns, using the `JournalEntryBuilder`.

### Functions:

- `create_je_for_sales_dispatch(dispatch: FinishedProductDispatch)`:
  - **Description:** Creates a single, compound journal entry that records both the Cost of Goods Sold (COGS) and the revenue from a customer sale at the time of dispatch.
  - **Accounting Logic:**
    - **COGS Entry:**
      - **Debit:** Cost of Goods Sold (COGS) Expense account.
      - **Credit:** Finished Goods Inventory account.
    - **Revenue Entry:**
      - **Debit:** Accounts Receivable account.
      - **Credit:** Sales Revenue account.
      - **Credit:** VAT Payable account (if applicable).
  - **Key Features:**
    - The `JournalEntryBuilder` combines two logical transactions into one balanced journal entry for efficiency.
    - Links the customer and final product as sub-ledgers for detailed reporting.
  - **Calls:** `_get_product_expense_account()`, `_get_product_revenue_account()` from `_helpers.py`.

- `create_je_for_credit_memo(memo: CustomerCreditMemo)`:
  - **Description:** Creates a journal entry for a customer credit memo, reversing the financial impact of a sale.
  - **Accounting Logic:**
    - **Debit:** Sales Returns & Allowances (contra-revenue).
    - **Debit:** VAT Payable (reversing the tax liability).
    - **Credit:** Accounts Receivable (reducing the customer's balance).
  - **Key Features:**
    - Uses the `JournalEntryBuilder` to ensure the transaction is correctly posted to an open period.