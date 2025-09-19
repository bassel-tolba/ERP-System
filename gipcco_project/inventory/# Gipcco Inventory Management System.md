# Gipcco Inventory Management System - Logical Representation

This document provides a high-level overview of the files, models, views, and services in the Gipcco project. It is intended as a context file for AI assistants to understand the application's structure without needing the full source code.

---

## 1. Core Data Structure (`inventory/models.py`)

This file defines the database schema and core business logic.

### Operational Models
- **`Company`**: Represents suppliers.
- **`Product`**: Represents all inventory items (raw materials, finished goods, MRO, etc.). Includes fields for overriding default GL accounts.
- **`ProductTag`**: Tags for categorizing products.
- **`InventoryLog`**: Represents a single receipt of materials from a supplier. It has a status (`QUARANTINED`, `RELEASED`, etc.) and contains all pricing and tax information.
- **`ShopOrderTemplate`**: A bill of materials (BOM) for a finished product.
- **`TemplateItem`**: A single line item within a `ShopOrderTemplate`.
- **`Batch`**: A production plan or shop order created from a `ShopOrderTemplate`. Can be a main batch or a `continuation` of a `parent_batch`.
- **`BatchItem`**: A single raw material line item consumed in a `Batch`. Links to a specific `InventoryLog` (or `OpeningBalance`) as its source.
- **`OpeningBalance`**: Records the initial stock quantity and value for a product at a specific date.
- **`ProductionReturn`**: Records raw materials returned from production back to inventory.
- **`PurchaseOrder`**: A purchase order sent to a supplier.
- **`PurchaseOrderItem`**: A line item on a `PurchaseOrder`.
- **`FinishedProductReceipt`**: Records the receipt of finished goods from a `Batch`. Has a status (`QUARANTINED`, `RELEASED`).
- **`ReceiptSubBatch`**: Details of sub-batches within a single `FinishedProductReceipt`.
- **`Customer`**: Represents a sales customer.
- **`SalesOrder`**: A sales order from a `Customer`.
- **`SalesOrderItem`**: A line item on a `SalesOrder`, linking to a specific `FinishedProductReceipt`.
- **`FinishedProductDispatch`**: Records the shipment of finished goods against a `SalesOrderItem`.
- **`InventoryConsumption`**: Records the internal use of MRO or Consumable items.
- **`ExpenseLog`**: Records general, non-inventory expenses.

### Accounting & Financial Models
- **`FixedAsset`**: The fixed asset sub-ledger.
- **`BankAccount`**: Represents a bank account or cash box, linked to a GL account.
- **`Payment`**: A single payment transaction (in or out), linked to a `BankAccount`.
- **`FiscalYear`**: Defines a fiscal year.
- **`FinancialPeriod`**: Defines a monthly accounting period within a `FiscalYear`. Has a status (`OPEN`, `CLOSED`, etc.).
- **`Account`**: A single account in the Chart of Accounts.
- **`JournalEntry`**: The header for a journal entry. Can be linked to a source object (e.g., `InventoryLog`, `Batch`).
- **`JournalEntryLine`**: A debit or credit line within a `JournalEntry`.
- **`ProductTypeAccountingSettings`**: Maps product types to default GL accounts (Inventory, COGS, Sales).
- **`GeneralAccountingSettings`**: A singleton model holding system-wide default accounts (A/P, A/R, WIP, etc.).
- **`SupplierInvoice`**: An A/P invoice from a supplier, linking one or more `InventoryLog` receipts.
- **`SupplierInvoiceItem`**: Links a receipt to a `SupplierInvoice`.
- **`PaymentApplication`**: Links a `Payment` to a `SupplierInvoice`.
- **`CustomerInvoice`**: An A/R invoice sent to a customer, linking one or more `FinishedProductDispatch` records.
- **`CustomerInvoiceItem`**: Links a dispatch to a `CustomerInvoice`.
- **`CustomerPaymentApplication`**: Links a received `Payment` to a `CustomerInvoice`.
- **`BankTransfer`**: Records fund movement between two `BankAccount`s.
- **`DepreciationLog`**: Records a monthly depreciation event for a `FixedAsset`.
- **`PeriodClosingAuditLog`**: An audit trail for `FinancialPeriod` status changes.
- **`BankReconciliation`**: Represents a bank reconciliation period.
- **`BankStatementLine`**: A line item from a bank statement, used in reconciliation.

---

## 2. URL Routing (`inventory/urls.py`)

This file maps URLs to view functions. Key routes include:
- `/`: Dashboard (`index`)
- `/products/`, `/companies/`, `/customers/`: CRUD for core data.
- `/purchase_orders/`, `/sales_orders/`: PO and SO management.
- `/batches/`: Production plan management.
- `/finished_goods_status/`: View for production pipeline.
- `/financials/`: Namespace for all accounting views (invoices, banking, journal, etc.).
- `/financials/periods/`: Fiscal year and period management.
- `/reports/`: Namespace for all financial reports (GL, P&L, Balance Sheet, etc.).
- `/api/`: Namespace for all API endpoints.

---

## 3. Business Logic Services

### `inventory/services/costing_service.py`
- **`get_inventory_state_at_datetime(product_id, target_datetime)`**:
  - **Purpose**: Calculates the historical stock quantity and total value for a product at a specific moment. Core function for valuation.
  - **Returns**: A dictionary `{'quantity': Decimal, 'value': Decimal}`.
- **`recalculate_cost_history_for_product(product_id, start_datetime)`**:
  - **Purpose**: The "master" costing function. Iterates through all transactions for a product from a start date, recalculates the moving average cost at each step, updates the `cost_at_consumption` on `BatchItem`s, and finally updates the `moving_average_cost` on the `Product` model.
  - **Returns**: `None`.

### `inventory/services/accounting_service.py`
- **`_check_period_is_open(date)`**: Helper that raises a `PermissionError` if the date falls in a closed `FinancialPeriod`. Used as a gatekeeper for all financial transactions.
- **`create_je_for_*` functions**: A series of functions that create balanced, double-entry `JournalEntry` records for specific business events.
  - `...inventory_receipt`: DEBIT Inventory, DEBIT VAT Receivable; CREDIT A/P, CREDIT WHT Payable.
  - `...production_consumption`: DEBIT WIP Inventory; CREDIT Raw Material Inventory.
  - `...internal_consumption`: DEBIT Expense Account; CREDIT Inventory.
  - `...finished_goods_receipt`: DEBIT Finished Goods Inventory; CREDIT WIP Inventory.
  - `...production_return`: DEBIT Raw Material Inventory; CREDIT WIP Inventory.
  - `...sales_dispatch`: DEBIT COGS, DEBIT A/R; CREDIT Finished Goods Inventory, CREDIT Sales Revenue, CREDIT VAT Payable.
  - `...supplier_payment`: DEBIT A/P; CREDIT Bank Account.
  - `...customer_payment`: DEBIT Bank Account; CREDIT A/R.
  - `...bank_transfer`: DEBIT Destination Bank; CREDIT Source Bank.
  - `...monthly_depreciation`: DEBIT Depreciation Expense; CREDIT Accumulated Depreciation.

---

## 4. Middleware (`inventory/middleware.py`)

- **`FinancialPeriodExceptionHandlerMiddleware`**: Catches the specific `PermissionError` raised by `_check_period_is_open` when a user tries to post to a closed period. It shows a user-friendly error message and redirects them back.

---

## 5. Application Views (`inventory/views/`)

### `dashboard.py`
- **`index(request)`**: (GET/POST) Displays the main dashboard and handles creation of new `InventoryLog` records (receipts) with a `QUARANTINED` status.
- **`records(request)`**: (GET) Displays a filterable list of all `InventoryLog` records.
- **`edit_record(request, pk)`**: (POST) Updates an `InventoryLog`. Triggers `recalculate_cost_history_for_product` if the record was released.
- **`delete_record(request, pk)`**: (POST) Deletes an `InventoryLog`. Triggers cost recalculation if it was released.
- **`quarantine_list(request)`**: (GET) Shows all `InventoryLog` records with `QUARANTINED` status.
- **`release_from_quarantine(request, pk)`**: (POST) Changes an `InventoryLog` status to `RELEASED`, sets QC number and release date. Triggers `recalculate_cost_history_for_product`.

### `companies_products.py`
- **`companies(request)`**: (GET/POST) Manages suppliers.
- **`products(request)`**: (GET/POST) Manages products, including setting accounting override accounts.
- **`*_tag(request)`**: (POST) CRUD operations for `ProductTag`s.

### `purchase_orders.py`
- **`purchase_orders(request)`**: (GET) Lists all `PurchaseOrder`s.
- **`create_purchase_order(request)`**: (GET/POST) Form to create a new `PurchaseOrder` and its items.
- **`view_purchase_order(request, pk)`**: (GET) Displays details of a PO, including received vs. remaining quantities.
- **`edit_purchase_order(request, pk)`**: (GET/POST) Edits a PO. Blocked if receipts exist.
- **`delete_purchase_order(request, pk)`**: (POST) Deletes a PO. Blocked if receipts exist.

### `sales.py`
- **`customers(request)`**: (GET/POST) Manages customers.
- **`sales_orders(request)`**: (GET) Lists all `SalesOrder`s.
- **`create_sales_order(request)`**: (GET/POST) Form to create a new `SalesOrder`.
- **`view_sales_order(request, pk)`**: (GET) Displays details of an SO.
- **`dispatch_from_sales_order(request, pk)`**: (POST) Creates `FinishedProductDispatch` records against an SO, shipping goods from inventory.

### `templates.py`
- **`shop_order_templates(request)`**: (GET/POST) Manages (create/list) `ShopOrderTemplate` (bills of material).
- **`view_shop_order_template(request, pk)`**: (GET) Displays a single template.
- **`edit_shop_order_template(request, pk)`**: (GET/POST) Edits a template.

### `batches.py`
- **`batches(request)`**: (GET) Lists all `Batch` (production plan) records.
- **`create_batch(request)`**: (GET/POST) Creates a new `Batch` and its `BatchItem`s. Performs stock validation via `validate_stock_availability`. Triggers cost recalculation for all consumed products.
- **`view_batch(request, pk)`**: (GET) The main detail view for a production plan. Shows consumed items, costs, and the status of finished good receipts.
- **`update_batch_items_bulk(request, batch_pk)`**: (POST) The main update function for a batch. Handles changes to quantities, sources, and batch header info. Performs stock validation and triggers cost recalculation.
- **`add_batch_item`, `delete_batch_item`**: (POST) Add/remove items from a batch, triggering cost recalculation.

### `finished_products.py`
- **`finished_goods_status(request)`**: (GET) A pipeline view showing plans "In Production", receipts "In Quarantine", and "Released" stock.
- **`receive_finished_product(request, batch_pk, ...)`**: (GET/POST) Form to create a `FinishedProductReceipt` against a `Batch`. Calculates the proportional cost of the batch.
- **`release_from_quarantine(request, pk)`**: (POST) Changes a `FinishedProductReceipt` status to `RELEASED`.
- **`view_finished_product(request, pk)`**: (GET) Shows details of a specific finished good receipt, including a full cost breakdown from its parent and continuation batches.

### `production_returns.py`
- **`production_returns(request)`**: (GET/POST) Manages `ProductionReturn` records. Triggers `recalculate_cost_history_for_product` on creation.
- **`delete_production_return(request, pk)`**: (POST) Deletes a return and triggers cost recalculation.

### `opening_balances.py`
- **`opening_balances(request)`**: (GET/POST) Manages `OpeningBalance` records. Triggers `recalculate_cost_history_for_product` on create/edit/delete.

### `expenses.py`
- **`expenses_dashboard(request)`**: (GET/POST) A dashboard for logging `InventoryConsumption` (internal use) and `ExpenseLog` (general expenses). Triggers cost recalculation for inventory consumption.
- **`manage_expenses(request)`**: (GET) A unified view to filter, edit, and delete both types of expenses.
- **`edit_*`, `delete_*`**: (POST) Handlers for editing/deleting expense records, with cost recalculation triggers for inventory items.

### `financials.py`
- **A/P Views**: `supplier_invoices`, `create_supplier_invoice`, `view_supplier_invoice`, `apply_payment_to_invoice`. Standard CRUD and payment application for A/P.
- **A/R Views**: `customer_invoices`, `create_customer_invoice`, `view_customer_invoice`, `receive_payment_for_invoice`. Standard CRUD and payment application for A/R.
- **Banking**: `bank_accounts_dashboard` to view balances and create `BankTransfer`s.
- **Journal Entries**: `journal_entries` (list), `create_journal_entry` (form), `post_journal_entry` (action).
- **Fixed Assets**: `fixed_assets_dashboard` to view assets and depreciation logs.
- **Financial Period Management**:
  - `fiscal_year_list`: Main view for managing years and periods.
  - `create_fiscal_year`, `edit_fiscal_year`, `delete_fiscal_year`: CRUD for `FiscalYear`.
  - `change_period_status`: Changes period status (e.g., Open -> Pending Close).
  - `close_period_view`: Displays the pre-closing checklist.
  - `close_period_action`: The final action to change status to `CLOSED`.
- **Bank Reconciliation**:
  - `bank_reconciliations_list`, `create_bank_reconciliation`: List/Create reconciliation periods.
  - `manage_bank_reconciliation`: The main workspace for matching statement lines to internal transactions.
  - `finalize_reconciliation`: Closes a reconciliation period if the difference is zero.

### `financial_reports.py`
- **`general_ledger(request)`**: (GET) Detailed transaction listing for a selected account and its children.
- **`trial_balance(request)`**: (GET) Hierarchical trial balance showing debits and credits for all accounts.
- **`profit_and_loss_statement(request)`**: (GET) Hierarchical income statement (Revenues - Expenses).
- **`balance_sheet(request)`**: (GET) Hierarchical balance sheet (Assets = Liabilities + Equity) at a specific point in time.
- **`tax_reconciliation_report(request)`**: (GET) Summarizes VAT Receivable, VAT Payable, and WHT Payable accounts.
- **`batch_production_variance_report(request)`**: (GET) Compares theoretical vs. actual material consumption and cost for production batches.
- **`reconciliation_report(request)`**: (GET) Lists completed bank reconciliations and all outstanding (uncleared) payments and transfers.
- **`product_ledger(request)`**: (GET) A detailed stock card for a single product, showing every movement (in/out) with running quantity and value balances.

### `api.py`
- **`api_get_open_pos_for_supplier(supplier_id)`**: Returns open POs for a supplier.
- **`api_get_po_items(po_id)`**: Returns items with remaining quantities for a PO.
- **`api_get_sellable_stock()`**: Returns all released, in-stock finished goods.
- **`api_get_available_stock(product_pk)`**: Returns available `InventoryLog` sources for a product for internal consumption.
- **`api_get_uninvoiced_receipts(supplier_id)`**: Returns receipts not yet on a supplier invoice.
- **`api_get_uninvoiced_dispatches(so_id)`**: Returns dispatches not yet on a customer invoice.
- **`api_period_checklist_status(period_id)`**: JSON endpoint that validates pre-closing conditions for a financial period.
- **Reconciliation APIs**: `api_match_transactions`, `api_unmatch_transaction`, `api_create_adjustment_and_match` handle the interactive matching logic on the reconciliation page.