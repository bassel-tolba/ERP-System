---
applyTo: '**'
---
# AI Agent Instructions for the Gipcco Inventory Management System (Exhaustive Edition)

This document provides a comprehensive, detailed set of instructions for AI coding agents to effectively contribute to the Gipcco Inventory Management System. It synthesizes all available project documentation into a single, authoritative source.

## 1. Project Overview

The Gipcco Inventory Management System is a comprehensive Django application designed to manage inventory, production, and accounting processes. The core functionality resides in the `inventory` app, which handles everything from raw material procurement to finished product sales, including complex costing, production planning (Bills of Material), and a full double-entry accounting backend.

### 1.1. Key Components

-   **`inventory` app**: The main application containing all models, views, templates, and business logic.
-   **`gipcco_project`**: The Django project directory, containing settings, URL configurations, and WSGI application.
-   **`static`**: Contains all frontend assets like CSS, JavaScript, and images.
-   **`templates`**: Contains Django templates for rendering HTML pages.

---

## 2. Backend Architecture

The project follows a standard Django architecture, with a clear separation of concerns between models, views, and templates, enhanced by a service layer for complex business logic.

### 2.1. Models (`inventory/models.py`)

This file defines the database schema and core business logic. The file follows a 'Fat Models' principle where business logic, calculations (via `@property`), and validation (via `clean()` methods) are often placed directly within the model classes.

#### 2.1.1. Operational Models
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
- **`InventoryCount`**: Header for a physical inventory counting event. Tracks the date, reason, and status of the count.
- **`InventoryCountItem`**: A line within an `InventoryCount`, snapshotting the system vs. counted quantity for a single product.
- **`InventoryAdjustment`**: The final, auditable record of a stock variance, linked to a specific source (`InventoryLog` or `FinishedProductReceipt`).

#### 2.1.2. Accounting & Financial Models
- **`FixedAsset`**: The fixed asset sub-ledger.
- **`BankAccount`**: Represents a bank account or cash box, linked to a GL account.
- **`Payment`**: A single payment transaction (in or out), linked to a `BankAccount`.
- **`FiscalYear`**: Defines a fiscal year.
- **`FinancialPeriod`**: Defines a monthly accounting period within a `FiscalYear`. Has a status (`OPEN`, `CLOSED`, etc.).
- **`Account`**: A single account in the Chart of Accounts.
- **`JournalEntry`**: The header for a journal entry. Can be linked to a source object (e.g., `InventoryLog`, `Batch`).
- **`JournalEntryLine`**: A debit or credit line within a `JournalEntry`.
- **`ProductTypeAccountingSettings`**: Maps product types to default GL accounts (Inventory, COGS, Sales).
- **`GeneralAccountingSettings`**: A singleton model holding system-wide default accounts (A/P, A/R, WIP, Inventory Adjustment Gain/Loss, etc.).
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

#### 2.1.3. Employee Financial Sub-Ledger Models
- **`Employee`**: Represents an employee, acting as a sub-ledger for employee-related accounts (e.g., advances).
- **`EmployeeAdvance`**: Records a single disbursement of funds to an employee, creating a receivable. It's linked to a `Payment` transaction.
- **`EmployeeAdvanceSettlement`**: A linking table that connects an `InventoryLog` or `ExpenseLog` to an `EmployeeAdvance` to justify the expenditure and settle the advance.

#### 2.1.4. Overhead Allocation Models
- **`CostPool`**: Represents a pool of indirect manufacturing costs (e.g., "Factory Rent", "Machine Maintenance"). Pools can be hierarchical. Each pool is linked to a specific GL expense account.
- **`AllocationDriver`**: Represents the basis for allocating cost pools (e.g., "Machine Hours", "Labor Hours", "Total Production Units").
- **`OverheadAllocationRun`**: An event record for calculating and posting overhead for a specific `CostPool` and `FinancialPeriod`. It stores the calculated rate and links to the resulting journal entries.

### 2.2. Services (`inventory/services/`)

The application uses a service layer to encapsulate complex business logic. This is a key architectural pattern.

-   **`costing_service.py`**:
    -   **`get_inventory_state_at_datetime(product_id, target_datetime)`**:
        -   **Purpose**: Calculates the historical stock quantity and total value for a product at a specific moment. Core function for valuation. Now includes `InventoryAdjustment` transactions.
        -   **Returns**: A dictionary `{'quantity': Decimal, 'value': Decimal}`.
    -   **`recalculate_cost_history_for_product(product_id, start_datetime)`**:
        -   **Purpose**: The "master" costing function. Iterates through all transactions for a product from a start date, recalculates the moving average cost at each step, updates the `cost_at_consumption` on `BatchItem`s, and finally updates the `moving_average_cost` on the `Product` model. Now includes `InventoryAdjustment` transactions.
        -   **Returns**: `None`.

-   **`overhead_service.py`**:
    -   **`calculate_cost_pool_total(cost_pool, period)`**: Calculates the total expenses assigned to a cost pool (and its children) for a period.
    -   **`calculate_driver_units_total(driver, period)`**: Calculates the total number of driver units (e.g., total machine hours) recorded in a period.
    -   **`execute_overhead_allocation_run(run)`**: The main calculation engine. It uses the above functions to determine the total pool amount, total driver units, and calculates the final overhead rate, saving it to the `OverheadAllocationRun` object.
    -   **`apply_overhead_to_finished_goods(run)`**: Applies the calculated overhead rate to all `FinishedProductReceipt` records within the period. It proportionally distributes the total pool cost to each receipt based on the driver units consumed by that receipt, updating the `allocated_overhead_cost` field.

-   **`accounting_service.py`**:
    -   **`_check_period_is_open(date)`**: Helper that raises a `PermissionError` if the date falls in a closed `FinancialPeriod`. Used as a gatekeeper for all financial transactions.
    -   **`create_je_for_*` functions**: A series of functions that create balanced, double-entry `JournalEntry` records for specific business events.
        -   `...inventory_receipt`: DEBIT Inventory, DEBIT VAT Receivable; CREDIT A/P, CREDIT WHT Payable.
        -   `...production_consumption`: DEBIT WIP Inventory; CREDIT Raw Material Inventory.
        -   `...internal_consumption`: DEBIT Expense Account; CREDIT Inventory.
        -   `...finished_goods_receipt`: DEBIT Finished Goods Inventory; CREDIT WIP Inventory.
        -   `...production_return`: DEBIT Raw Material Inventory; CREDIT WIP Inventory.
        -   `...sales_dispatch`: DEBIT COGS, DEBIT A/R; CREDIT Finished Goods Inventory, CREDIT Sales Revenue, CREDIT VAT Payable.
        -   `...supplier_payment`: DEBIT A/P; CREDIT Bank Account.
        -   `...customer_payment`: DEBIT Bank Account; CREDIT A/R.
        -   `...bank_transfer`: DEBIT Destination Bank; CREDIT Source Bank.
        -   `...monthly_depreciation`: DEBIT Depreciation Expense; CREDIT Accumulated Depreciation.
        -   `...inventory_adjustment`: DEBIT Inventory/Loss Account; CREDIT Inventory/Gain Account.
        -   `...employee_advance`: DEBIT Employee Advances Receivable; CREDIT Bank Account.
        -   `...overhead_allocation`: DEBIT WIP Inventory; CREDIT various Expense Accounts from the cost pool.
        -   `...overhead_application`: DEBIT Finished Goods Inventory; CREDIT WIP Inventory.

-   **`adjustment_service.py`**:
    -   **`start_inventory_count`**: Creates a count event and snapshots system quantities.
    -   **`create_adjustments_from_form`**: Creates `InventoryAdjustment` records based on user input from the allocation modal.
    -   **`auto_distribute_finished_good_shortage`**: Implements the special logic to automatically create shortage adjustments for finished goods from the newest batches first.
    -   **`finalize_inventory_count`**: Triggers cost recalculation for all affected products and marks the count as complete.

### 2.3. Signals (`inventory/signals.py`)

The application uses Django signals (`post_save`, `post_delete`) to automatically trigger the creation of journal entries when key models (like `InventoryLog`, `Batch`, `Payment`, `FinishedProductDispatch`, `InventoryAdjustment`) are saved or deleted. This decouples the accounting logic from the core business operations.

### 2.4. Views (`inventory/views/`)

The views are organized into separate files based on their functionality.

- **`dashboard.py`**:
    - `index(request)`: (GET/POST) Displays the main dashboard and handles creation of new `InventoryLog` records (receipts) with a `QUARANTINED` status.
    - `records(request)`: (GET) Displays a filterable list of all `InventoryLog` records.
    - `edit_record(request, pk)`: (POST) Updates an `InventoryLog`. Triggers `recalculate_cost_history_for_product` if the record was released.
    - `delete_record(request, pk)`: (POST) Deletes an `InventoryLog`. Triggers cost recalculation if it was released.
    - `quarantine_list(request)`: (GET) Shows all `InventoryLog` records with `QUARANTINED` status.
    - `release_from_quarantine(request, pk)`: (POST) Changes an `InventoryLog` status to `RELEASED`, sets QC number and release date. Triggers `recalculate_cost_history_for_product`.
- **`companies_products.py`**:
    - `companies(request)`: (GET/POST) Manages suppliers.
    - `products(request)`: (GET/POST) Manages products, including setting accounting override accounts.
    - `*_tag(request)`: (POST) CRUD operations for `ProductTag`s.
- **`purchase_orders.py`**:
    - `purchase_orders(request)`: (GET) Lists all `PurchaseOrder`s.
    - `create_purchase_order(request)`: (GET/POST) Form to create a new `PurchaseOrder` and its items.
    - `view_purchase_order(request, pk)`: (GET) Displays details of a PO, including received vs. remaining quantities.
    - `edit_purchase_order(request, pk)`: (GET/POST) Edits a PO. Blocked if receipts exist.
    - `delete_purchase_order(request, pk)`: (POST) Deletes a PO. Blocked if receipts exist.
- **`sales.py`**:
    - `customers(request)`: (GET/POST) Manages customers.
    - `sales_orders(request)`: (GET) Lists all `SalesOrder`s.
    - `create_sales_order(request)`: (GET/POST) Form to create a new `SalesOrder`.
    - `view_sales_order(request, pk)`: (GET) Displays details of an SO.
    - `dispatch_from_sales_order(request, pk)`: (POST) Creates `FinishedProductDispatch` records against an SO, shipping goods from inventory.
- **`templates.py`**:
    - `shop_order_templates(request)`: (GET/POST) Manages (create/list) `ShopOrderTemplate` (bills of material).
    - `view_shop_order_template(request, pk)`: (GET) Displays a single template.
    - `edit_shop_order_template(request, pk)`: (GET/POST) Edits a template.
- **`batches.py`**:
    - `batches(request)`: (GET) Lists all `Batch` (production plan) records.
    - `create_batch(request)`: (GET/POST) Creates a new `Batch` and its `BatchItem`s. Performs stock validation via `validate_stock_availability`. Triggers cost recalculation for all consumed products.
    - `view_batch(request, pk)`: (GET) The main detail view for a production plan. Shows consumed items, costs, and the status of finished good receipts.
    - `update_batch_items_bulk(request, batch_pk)`: (POST) The main update function for a batch. Handles changes to quantities, sources, and batch header info. Performs stock validation and triggers cost recalculation.
    - `add_batch_item`, `delete_batch_item`: (POST) Add/remove items from a batch, triggering cost recalculation.
- **`finished_products.py`**:
    - `finished_goods_status(request)`: (GET) A pipeline view showing plans "In Production", receipts "In Quarantine", and "Released" stock.
    - `receive_finished_product(request, batch_pk, ...)`: (GET/POST) Form to create a `FinishedProductReceipt` against a `Batch`. Calculates the proportional cost of the batch.
    - `release_from_quarantine(request, pk)`: (POST) Changes a `FinishedProductReceipt` status to `RELEASED`.
    - `view_finished_product(request, pk)`: (GET) Shows details of a specific finished good receipt, including a full cost breakdown from its parent and continuation batches.
- **`production_returns.py`**:
    - `production_returns(request)`: (GET/POST) Manages `ProductionReturn` records. Triggers `recalculate_cost_history_for_product` on creation.
    - `delete_production_return(request, pk)`: (POST) Deletes a return and triggers cost recalculation.
- **`opening_balances.py`**:
    - `opening_balances(request)`: (GET/POST) Manages `OpeningBalance` records. Triggers `recalculate_cost_history_for_product` on create/edit/delete.
- **`expenses.py`**:
    - `expenses_dashboard(request)`: (GET/POST) A dashboard for logging `InventoryConsumption` (internal use) and `ExpenseLog` (general expenses). Triggers cost recalculation for inventory consumption.
    - `manage_expenses(request)`: (GET) A unified view to filter, edit, and delete both types of expenses.
    - `edit_*`, `delete_*`: (POST) Handlers for editing/deleting expense records, with cost recalculation triggers for inventory items.
- **`adjustments.py`**:
    - `inventory_counts_list(request)`: (GET) Lists all inventory count events.
    - `create_inventory_count(request)`: (GET/POST) Form to start a new count and select products.
    - `manage_inventory_count(request, pk)`: (GET/POST) Workspace for entering physical counted quantities.
    - `allocate_inventory_variances(request, pk)`: (GET/POST) The main workspace for reviewing variances and allocating them to specific stock sources before final posting.
- **`employees.py`**:
    - `manage_employees(request)`: (GET/POST) CRUD operations for `Employee` records.
    - `employee_financials_dashboard(request)`: (GET) A dashboard showing all employees and their outstanding advance balances.
    - `employee_advance_detail(request, employee_id)`: (GET/POST) A detailed view for a single employee, showing all their advances and settlements. Handles the creation of new `EmployeeAdvance` records.
    - `settle_employee_advance(request, advance_id)`: (POST) Handles the settlement of an advance by linking it to selected `InventoryLog` or `ExpenseLog` transactions.
- **`financials.py`**: A large module containing views for:
    -   **A/P**: `supplier_invoices`, `create_supplier_invoice`, `view_supplier_invoice`, `apply_payment_to_invoice`.
    -   **A/R**: `customer_invoices`, `create_customer_invoice`, `view_customer_invoice`, `receive_payment_for_invoice`.
    -   **Banking**: `bank_accounts_dashboard` to view balances and create `BankTransfer`s.
    -   **Journal Entries**: `journal_entries` (list), `create_journal_entry` (form), `post_journal_entry` (action).
    -   **Fixed Assets**: `fixed_assets_dashboard` to view assets and depreciation logs.
    -   **Overhead & Configuration**: `cost_pools_list` (manage cost pool hierarchy), `allocation_drivers_list` (manage allocation drivers), `overhead_allocation_workspace` (the main screen to run, post, and apply period-end overhead calculations).
    -   **Period Management**: `fiscal_year_list`, `create_fiscal_year`, `edit_fiscal_year`, `delete_fiscal_year`, `change_period_status`, `close_period_view`, `close_period_action`.
    -   **Bank Reconciliation**: `bank_reconciliations_list`, `create_bank_reconciliation`, `manage_bank_reconciliation`, `finalize_reconciliation`.
- **`financial_reports.py`**:
    - `general_ledger(request)`: (GET) Detailed transaction listing for a selected account and its children.
    - `trial_balance(request)`: (GET) Hierarchical trial balance showing debits and credits for all accounts.
    - `profit_and_loss_statement(request)`: (GET) Hierarchical income statement (Revenues - Expenses).
    - `balance_sheet(request)`: (GET) Hierarchical balance sheet (Assets = Liabilities + Equity) at a specific point in time.
    - `tax_reconciliation_report(request)`: (GET) Summarizes VAT Receivable, VAT Payable, and WHT Payable accounts.
    - `batch_production_variance_report(request)`: (GET) Compares theoretical vs. actual material consumption and cost for production batches.
    - `reconciliation_report(request)`: (GET) Lists completed bank reconciliations and all outstanding (uncleared) payments and transfers.
    - `product_ledger(request)`: (GET) A detailed stock card for a single product, showing every movement (in/out) with running quantity and value balances.

### 2.5. URL Routing (`inventory/urls.py`)

This file maps URLs to view functions. Key routes include:
- `/`: Dashboard (`index`)
- `/products/`, `/companies/`, `/customers/`: CRUD for core data.
- `/purchase_orders/`, `/sales_orders/`: PO and SO management.
- `/batches/`: Production plan management.
- `/finished_goods_status/`: View for production pipeline.
- `/inventory_counts/`: Inventory count and adjustment management.
- `/employee_financials/`: Namespace for employee advance management.
- `/financials/`: Namespace for all accounting views (invoices, banking, journal, etc.).
- `/financials/periods/`: Fiscal year and period management.
- `/financials/cost_pools/`, `/financials/allocation_drivers/`, `/financials/overhead_allocation/`: Overhead configuration and execution URLs.
- `/reports/`: Namespace for all financial reports (GL, P&L, Balance Sheet, etc.).
- `/api/`: Namespace for all API endpoints.

### 2.6. API (`inventory/views/api.py`)

The API is primarily used by the frontend to create dynamic and interactive forms.
- **`api_get_open_pos_for_supplier(supplier_id)`**: Returns open POs for a supplier.
- **`api_get_po_items(po_id)`**: Returns items with remaining quantities for a PO.
- **`api_get_sellable_stock()`**: Returns all released, in-stock finished goods.
- **`api_get_available_stock(product_pk)`**: Returns available `InventoryLog` sources for a product for internal consumption.
- **`api_get_uninvoiced_receipts(supplier_id)`**: Returns receipts not yet on a supplier invoice.
- **`api_get_uninvoiced_dispatches(so_id)`**: Returns dispatches not yet on a customer invoice.
- **`api_get_stock_sources_for_product(product_id)`**: Returns a detailed list of all stock sources (`InventoryLog`s and `FinishedProductReceipt`s) for a product, used to populate the allocation modal.
- **`api_get_unsettled_transactions(employee_id)`**: Returns `InventoryLog` and `ExpenseLog` transactions for an employee that have not yet been used to settle an advance.
- **`api_period_checklist_status(period_id)`**: JSON endpoint that validates pre-closing conditions for a financial period.
- **Reconciliation APIs**: `api_match_transactions`, `api_unmatch_transaction`, `api_create_adjustment_and_match` handle the interactive matching logic on the reconciliation page.

### 2.7. Middleware (`inventory/middleware.py`)

- **`FinancialPeriodExceptionHandlerMiddleware`**: Catches the specific `PermissionError` raised by `_check_period_is_open` when a user tries to post to a closed period. It shows a user-friendly error message and redirects them back.

### 2.8. Accounting & Fiscal Period Workflow

A comprehensive workflow manages the accounting lifecycle, ensuring data integrity.
-   **Hierarchy**: `FiscalYear` contains multiple `FinancialPeriod` models.
-   **Period Status Lifecycle**: `Open` -> `Pending Close` -> `Closed`. The status transition is controlled and audited.
-   **Closing Checklist**: To move a period to `Closed`, a dedicated screen programmatically validates conditions (e.g., all bank accounts reconciled, no draft JEs) via an API call before enabling the action.
-   **Audit Trail**: Every status change is recorded in the `PeriodClosingAuditLog` model, capturing user, action, timestamp, and a mandatory justification.

---

## 3. Frontend Architecture: A "HTML-over-the-wire" SPA-like Experience

The frontend is a sophisticated system that dynamically loads HTML fragments from the server to feel like a Single-Page Application (SPA) without a complex JavaScript framework.

### 3.1. Core JavaScript Engine (`static/layout/js/dynamic_content_loader.js`)

This file is the heart and brain of the frontend's dynamic behavior.
-   **Primary Goal**: To intercept user navigation and form submissions, fetch only the necessary HTML content from the server, and intelligently swap it into the current page.
-   **Workflow**:
    1.  **Event Interception**: It attaches global listeners to intercept `click` events on links and `submit` events on forms.
    2.  **`loadContent(url)`**: The main function initiates a `fetch()` request, adding a custom `X-Partial-Request: "true"` header. The Django backend sees this header and responds with a lightweight HTML fragment (rendered with `_partial_layout.html`).
    3.  **DOM Manipulation**: It replaces the `innerHTML` of the main `<div id="page-content">`.
    4.  **Browser History**: It uses `history.pushState()` to update the browser URL, ensuring back/forward buttons work.
-   **`window.initializePluginsInContent(container)`**:
    -   **The Orchestrator**: Called after new content is injected to "bring it to life".
    -   **Generic Initializers**: Activates common plugins like `flatpickr` on `.datepicker` and `TomSelect` on `.searchable-select`.
    -   **Page-Specific Initializers (`pageInitializers` map)**: A key design pattern. It's a map of `CSS Selector -> Init Function`. The loader iterates this map, finds selectors in the new content, and executes the corresponding function (e.g., finds `#batchEditForm`, runs `initBatchViewLogic`).
-   **`getDataFromIsland(islandId)`**: A helper to parse JSON data from `<script type="application/json">` tags (the "JSON island" technique), which is the primary method for passing complex data from Django to JavaScript.

### 3.2. Page-Specific JavaScript Modules (`static/layout/js/*_logic.js`)

These files contain specialized logic for individual pages, called by the dynamic loader.

-   **`dashboard_logic.js`**: Manages dynamic tags and the chained API calls for the Purchase Order receiving workflow (Supplier -> POs -> PO Items -> Auto-fill form).
-   **`records_logic.js`**: Manages the "Edit Record" modal, replicating the entire PO workflow from the dashboard *inside the modal*.
-   **`purchase_order_create_logic.js`**: Dynamically adds/removes line item rows, initializes searchable product dropdowns for each row, and performs real-time calculation of line totals.
-   **`sales_order_create_logic.js`**: Fetches available finished goods stock via API and populates dynamic line item dropdowns.
-   **`shop_order_templates_logic.js`**: Manages the "Create Template" (BOM) modal, including dynamic rows and a "copy from existing" feature that pre-populates the form.
-   **`create_batch_logic.js`**: One of the most complex modules. It dynamically builds the materials table from a template, allocates available stock to each material, handles quantity splitting across multiple stock sources, and performs real-time validation.
-   **`batch_view_logic.js`**: Recalculates material quantities if the number of batches is changed and handles item deletion.
-   **`financials_logic.js`**: A multi-purpose module that handles:
    -   **Invoice Creation**: Fetches uninvoiced items via API and builds the selection table, with real-time total calculation.
    -   **Journal Entry Creation**: Manages the dynamic formset, calculates running totals, and disables the save button until the entry is balanced.
    -   **Bank Reconciliation**: Manages the state of selected items, matches transactions, and handles the creation of adjustment entries via modals and API calls.
-   **`inventory_counts_logic.js`**: Manages the entire interactive workflow for the "Variance Allocation Workspace". It fetches stock sources via API, dynamically builds the allocation modal, validates user input, stores the allocation state, and prepares the final data for submission.
-   **`visuals_logic.js`**: Manages tabs, reads data from JSON islands, and renders all charts on the analysis page using Chart.js.
-   **`close_period_logic.js`**: On the period closing page, it polls the `api_period_checklist_status` endpoint, updates the UI of the checklist with success/failure icons, and enables the finalization button only when all checks pass.
-   **`expenses_page_logic.js`**: Manages the dynamic "Source Log" dropdown on the expense dashboard.
-   **`ledger_logic.js`**: Controls the details modal on the ledger page, fetching batch analysis via API.
-   **`manage_expenses_logic.js`**: Populates "Edit" modals on the Manage Expenses page.
-   **`production_returns_logic.js`**: Dynamically fetches and populates the "Original QC Source" dropdown.
-   **`receive_finished_product_logic.js`**: Handles dynamic addition/removal of "sub-batch" rows.
-   **`tax_reconciliation_report_logic.js`**: Hijacks the filter form submission to use the dynamic content loader.
-   **`batch_production_variance_report_logic.js`**: Reads chart data from a JSON island and renders variance charts.
-   **`theme_season_logic.js`**: A non-essential, easter-egg style script for themes and seasonal effects.

### 3.3. HTML Templates (`templates/inventory/`)

The templates are structured to support the dynamic loading system.

#### 3.3.1. Core Architecture & Layouts
-   **`layout.html`**: The Master Template. Contains the shell, navigation, and links to **all** CSS and JS files. The main content `<div>` has `id="page-content"`.
-   **`_partial_layout.html`**: The Dynamic Content Template. Contains *only* `{% block content %}`. Used for all partial responses.
-   **`print_layout.html` & `print_ledger_enhanced.html`**: Print-Specific Templates with minimal structure and print-oriented CSS.

#### 3.3.2. Main Application Page Templates (The Shells)
These are simple wrappers that extend `layout.html` and `{% include %}` their corresponding `_content.html` partial. They serve as the entry points for full-page loads. Examples: `dashboard.html`, `records.html`, `products.html`, `purchase_orders.html`, `sales_orders.html`, `batches.html`, `financials.html`, `reports/*.html`, etc.

#### 3.3.3. Content Partials (`partials/`)
These files contain the actual UI for each page and are the content swapped by the dynamic loader. They contain the forms, tables, modals, and the JSON islands (`<script type="application/json">`) that provide data to the JavaScript modules.

-   **`partials/dashboard_content.html`**: Form for new receipts, table of recent logs. **JS Module**: `dashboard_logic.js`.
-   **`partials/records_content.html`**: Filterable table of inventory logs, complex modal for editing. **JS Module**: `records_logic.js`.
-   **`partials/purchase_order_create_content.html`**: Form for PO details, table for line items with dynamic rows. **JS Module**: `purchase_order_create_logic.js`.
-   **`partials/sales_order_create_content.html`**: Form for SO details, table for line items with dynamic rows. **JS Module**: `sales_order_create_logic.js`.
-   **`partials/shop_order_templates_content.html`**: Table of BOMs, modal for creation with dynamic rows. **JS Module**: `shop_order_templates_logic.js`.
-   **`partials/create_batch_content.html`**: Multi-step form for production runs. **JS Module**: `create_batch_logic.js`.
-   **`partials/batch_view_content.html`**: Detailed view of a production run. **JS Module**: `batch_view_logic.js`.
-   **`partials/supplier_invoice_create_content.html`**: Form for invoice details, table for selecting items to be invoiced. **JS Module**: `financials_logic.js`.
-   **`partials/journal_entry_create_content.html`**: Dynamic table for JE lines with sticky footer showing totals. **JS Module**: `financials_logic.js`.
-   **`partials/fiscal_year_list_content.html`**: Accordion layout for fiscal years/periods. Modals for all actions.
-   **`partials/inventory_counts_list_content.html`**, **`partials/inventory_count_create_content.html`**, **`partials/inventory_count_manage_content.html`**, **`partials/inventory_variance_allocation_content.html`**: A suite of templates that manage the entire inventory count workflow, from creation and data entry to the interactive variance allocation workspace. **JS Module**: `inventory_counts_logic.js`.
-   **`partials/reports/*`**: Data-heavy tables for reports. Filter forms use the dynamic loader.
-   **`partials/visuals_content.html`**: Tabbed layout with `<canvas>` elements for charts. **JS Module**: `visuals_logic.js`.

#### 3.3.4. Modal Partials (`modals/`)
These are reusable Bootstrap modal components included within the content partials, such as `modals/create_fiscal_year_modal.html`.

---

## 4. Developer Workflows & Conventions

### 4.1. Running the Application
-   **Server**: `python manage.py runserver`
-   **Tests**: `python manage.py test`
-   **Migrations**: `python manage.py makemigrations` followed by `python manage.py migrate`

### 4.2. Key Conventions
-   **Internationalization**: `gettext_lazy` is used for model verbose names.
-   **Logging**: A rotating file logger is configured (`gipcco.log`).
-   **Atomic Transactions**: Views use `transaction.atomic()` to ensure data integrity.
-   **Service Layer**: Complex business logic is encapsulated in services.
-   **Fat Models**: Business logic, calculations (`@property`), and validation (`clean()`) are often placed directly within the model classes.

## 5. Guidelines for Generating Code

When generating code for this project, please adhere to the following guidelines:

-   **Do not repeat unchanged code**: Use comments like `// ...existing code...` or `# ...existing code...` to represent regions of unchanged code in your edits.
-   **Follow existing patterns**: Adhere to the established architecture (Service Layer, Fat Models, SPA-like frontend).
-   **Document new code**: Add comments and docstrings where appropriate.
-   **Utilize existing context**: Do not re-read files if the information is already present in these instructions.
-   **Utilize already read files**: Do not re-read files if the file has already been read.
-   **Debug mode**: Include print and logging statements to aid in debugging during development.
-   **Editing Precision**: When replacing a specific function or class, ensure the `...existing code...` markers are placed immediately before and after the target block. This prevents accidental deletion of adjacent code. For example, to replace `function_b`:
    ```python
    # ...existing code...
    def function_a():
        pass

    def function_b_replacement(): # New function
        pass

    def function_c():
    # ...existing code...
    ```