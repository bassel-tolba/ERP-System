

## Exhaustive Frontend Architecture Representation (HTML & JS)

This document provides a definitive, file-by-file breakdown of the Gipcco frontend. It outlines the role of each HTML template and its relationship with the JavaScript architecture.

### Part 1: Core Architecture & Layouts

These files form the foundational structure of the application.

#### --- FILE: `layout.html` ---

-   **Role**: The Master Template. This is the single most important file in the frontend. Every full-page view extends it.
-   **Purpose**: To provide a consistent shell for the entire application, including navigation, branding, global styles, and all JavaScript assets.
-   **Key Components**:
    -   **`<head>`**: Loads global CSS including Bootstrap, Google Fonts, third-party libraries (TomSelect, Flatpickr), and custom stylesheets (`style.css`, `print.css`).
    -   **Sidebar (`<div class="offcanvas">`)**: A comprehensive, collapsible navigation menu that provides access to every module of the application. The active link and parent dropdown are highlighted using Django template logic (`{% if active_page == '...' %}`).
    -   **Header (`<header class="header">`)**: Contains the sidebar toggle and the dark/light mode theme switcher.
    -   **Message Display Area**: A block that iterates through Django's `messages` framework to show success, error, and warning alerts to the user after an action.
    -   **Content Block (`{% block content %}`)**: The placeholder where the unique content of each page is injected. The main content `<div>` has the crucial `id="page-content"`.
    -   **Footer**: A simple static footer.
    -   **Global Scripts**: Includes Bootstrap JS, Chart.js, and critically, **all** custom `_logic.js` files and the `dynamic_content_loader.js`. This ensures all JavaScript modules are available globally for the dynamic loader to call upon.
    -   **`window.appUrls` Object**: A global JavaScript object populated by Django's `{% url %}` tags, making backend URLs available to all client-side scripts in a maintainable way.

#### --- FILE: `_partial_layout.html` ---

-   **Role**: The Dynamic Content Template.
-   **Purpose**: A minimalist template used exclusively by views when they detect a partial request (via the `X-Partial-Request` header sent by `dynamic_content_loader.js`).
-   **Key Components**: It contains *only* a `{% block content %}` tag. This ensures the server's response is a lightweight HTML fragment, not the entire page layout, which is the key to the application's speed.

#### --- FILE: `print_layout.html` & `print_ledger_enhanced.html` ---

-   **Role**: Print-Specific Templates.
-   **Purpose**: To provide a clean, unadorned layout specifically formatted for printing reports.
-   **Key Components**:
    -   Minimal HTML structure with no navigation, sidebars, or interactive elements.
    -   Links to a dedicated print stylesheet (`print.css`) and uses `@page` CSS rules for proper A4 formatting.
    -   `print_ledger_enhanced.html` includes a report header, summary statistics, and automatically triggers the browser's print dialog via `window.print()` on load.

---

### Part 2: Main Application Page Templates (The Shells)

These templates serve as the entry points for full-page loads. They are simple wrappers that include their corresponding content partial.

#### --- FILE: `dashboard.html` ---
-   **Purpose**: Main application landing page.
-   **Includes**: `partials/dashboard_content.html`.

#### --- FILE: `records.html` ---
-   **Purpose**: To view and manage all inventory receipt records.
-   **Includes**: `partials/records_content.html`.

#### --- FILE: `quarantine.html` ---
-   **Purpose**: A focused view for managing items under quality control.
-   **Includes**: `partials/quarantine_content.html`.

#### --- FILE: `products.html`, `companies.html`, `customers.html` ---
-   **Purpose**: Standard CRUD (Create, Read, Update, Delete) pages for core data models.
-   **Includes**: `partials/products_content.html`, `partials/companies_content.html`, `partials/customers_content.html` respectively.

#### --- FILE: `purchase_orders.html`, `purchase_order_create.html`, `purchase_order_view.html`, `purchase_order_edit.html` ---
-   **Purpose**: A full suite of views for managing Purchase Orders.
-   **Includes**: `partials/purchase_orders_content.html`, `partials/purchase_order_create_content.html`, `partials/purchase_order_view_content.html`, `partials/purchase_order_edit_content.html` respectively.

#### --- FILE: `sales_orders.html`, `sales_order_create.html`, `sales_order_view.html` ---
-   **Purpose**: A full suite of views for managing Sales Orders.
-   **Includes**: `partials/sales_orders_content.html`, `partials/sales_order_create_content.html`, `partials/sales_order_view_content.html` respectively.

#### --- FILE: `shop_order_templates.html`, `shop_order_template_view.html`, `shop_order_template_edit.html` ---
-   **Purpose**: A full suite of views for managing production Bills of Material (BOMs).
-   **Includes**: `partials/shop_order_templates_content.html`, `partials/shop_order_template_view_content.html`, `partials/shop_order_template_edit_partial.html` respectively.

#### --- FILE: `batches.html`, `create_batch.html`, `batch_view.html` ---
-   **Purpose**: A full suite of views for managing production plans (Batches/Shop Orders).
-   **Includes**: `partials/batches_content.html`, `partials/create_batch_content.html`, `partials/batch_view_content.html` respectively.

#### --- FILE: `finished_products_list.html`, `finished_goods_status.html`, `receive_finished_product.html`, `view_finished_product.html` ---
-   **Purpose**: Views for tracking and managing the finished goods lifecycle.
-   **Includes**: `partials/finished_products_list_content.html`, `partials/finished_goods_status_content.html`, `partials/receive_finished_product_content.html`, `partials/view_finished_product_content.html` respectively.

#### --- FILE: `opening_balances.html` ---
-   **Purpose**: Page for managing initial stock levels.
-   **Includes**: `partials/opening_balances_content.html`.

#### --- FILE: `production_returns.html` ---
-   **Purpose**: Page for managing materials returned from the production line.
-   **Includes**: `partials/production_returns_content.html`.

#### --- FILE: `expenses_dashboard.html`, `manage_expenses.html` ---
-   **Purpose**: Views for logging and managing all types of company expenses.
-   **Includes**: `partials/expenses_dashboard_content.html`, `partials/manage_expenses_content.html` respectively.

#### --- FILE: `supplier_invoices.html`, `supplier_invoice_create.html`, `supplier_invoice_view.html` ---
-   **Purpose**: A/P module for managing supplier invoices.
-   **Includes**: `partials/supplier_invoices_content.html`, `partials/supplier_invoice_create_content.html`, `partials/supplier_invoice_view_content.html` respectively.

#### --- FILE: `customer_invoices.html`, `customer_invoice_create.html`, `customer_invoice_view.html` ---
-   **Purpose**: A/R module for managing customer invoices.
-   **Includes**: `partials/customer_invoices_content.html`, `partials/customer_invoice_create_content.html`, `partials/customer_invoice_view_content.html` respectively.

#### --- FILE: `banking_dashboard.html` ---
-   **Purpose**: View for managing bank accounts and transfers.
-   **Includes**: `partials/banking_dashboard_content.html`.

#### --- FILE: `journal_entries.html`, `journal_entry_create.html` ---
-   **Purpose**: Views for managing manual general ledger entries.
-   **Includes**: `partials/journal_entries_content.html`, `partials/journal_entry_create_content.html` respectively.

#### --- FILE: `fixed_assets_dashboard.html` ---
-   **Purpose**: Dashboard for the fixed assets sub-ledger.
-   **Includes**: `partials/fixed_assets_dashboard_content.html`.

#### --- FILE: `fiscal_year_list.html`, `close_period_view.html` ---
-   **Purpose**: Views for managing the accounting calendar and closing periods.
-   **Includes**: `partials/fiscal_year_list_content.html`, `close_period_view.html` (this is a full template, not a partial).

#### --- FILE: `reconciliation_list.html`, `reconciliation_create.html`, `reconciliation_manage.html` ---
-   **Purpose**: A full suite of views for the bank reconciliation module.
-   **Includes**: `partials/reconciliation_list_content.html` and two full templates for the creation and management workspace.

#### --- FILE: `analysis.html`, `ledger.html`, `stock_valuation.html`, `visuals.html` ---
-   **Purpose**: Inventory analysis and reporting pages.
-   **Includes**: `partials/analysis_content.html`, `partials/ledger_content.html`, `partials/stock_valuation_content.html`, `partials/visuals_content.html` respectively.

#### --- FILE: `reports/*.html` (e.g., `trial_balance.html`, `profit_and_loss_statement.html`, etc.) ---
-   **Purpose**: The main entry points for all formal financial reports.
-   **Includes**: Each report template includes its corresponding partial from the `partials/reports/` directory (e.g., `reports/trial_balance.html` includes `partials/reports/trial_balance_content.html`).

---

### Part 3: Content Partials (`partials/`)

These files contain the actual UI for each page and are the content swapped by the dynamic loader.

#### --- FILE: `partials/dashboard_content.html` ---
-   **UI**: A form for new inventory receipts and a table of recent logs.
-   **Interactivity**: The form dynamically shows/hides PO-related fields. Dropdowns are chained and populated via API calls. Form fields are auto-filled upon PO item selection.
-   **JS Module**: `dashboard_logic.js`.

#### --- FILE: `partials/records_content.html` ---
-   **UI**: A filterable table of all inventory logs. Includes a complex modal for editing records.
-   **Interactivity**: The modal is populated from `data-*` attributes. It contains its own PO-linking logic, mirroring the dashboard.
-   **JS Module**: `records_logic.js`.

#### --- FILE: `partials/quarantine_content.html` ---
-   **UI**: Table of items awaiting QC. Includes a modal for releasing items.
-   **Interactivity**: The modal's form `action` is set dynamically.

#### --- FILE: `partials/products_content.html` ---
-   **UI**: Table of products with modals for creation/editing and tag management.
-   **Interactivity**: TomSelect is initialized on all dropdowns within the modals.

#### --- FILE: `partials/purchase_order_create_content.html`, `partials/purchase_order_edit_content.html` ---
-   **UI**: A main form for PO details and a table for line items.
-   **Interactivity**: Rows can be added/removed dynamically. Product dropdowns in each row are searchable. Line totals are calculated in real-time.
-   **JS Module**: `purchase_order_create_logic.js`.

#### --- FILE: `partials/sales_order_create_content.html` ---
-   **UI**: A main form for SO details and a table for line items.
-   **Interactivity**: Dynamically adds/removes rows. The product dropdown for each row is populated via an API call to fetch available finished goods stock.
-   **JS Module**: `sales_order_create_logic.js`.

#### --- FILE: `partials/shop_order_templates_content.html` (and related partials) ---
-   **UI**: Table of templates and a large modal for creation. `_edit_partial.html` provides the edit form.
-   **Interactivity**: The creation modal's form rows are added dynamically. It can pre-populate from another template if loaded in "copy mode."
-   **JS Module**: `shop_order_templates_logic.js`.

#### --- FILE: `partials/create_batch_content.html` ---
-   **UI**: Multi-step form for creating a production run.
-   **Interactivity**: This is one of the most complex pages. It dynamically loads materials from a template, populates QC source dropdowns from available stock, validates quantities against stock levels, and allows for quantity splitting.
-   **JS Module**: `create_batch_logic.js`.

#### --- FILE: `partials/batch_view_content.html` ---
-   **UI**: Detailed view of a production run.
-   **Interactivity**: Allows changing of source QC for consumed materials and recalculates total quantities if the number of batches is changed.
-   **JS Module**: `batch_view_logic.js`.

#### --- FILE: `partials/supplier_invoice_create_content.html`, `partials/customer_invoice_create_content.html` ---
-   **UI**: A form for invoice details and a table for selecting items to be invoiced.
-   **Interactivity**: The item table is populated via an API call when a supplier/customer is selected. The total is calculated as items are checked.
-   **JS Module**: `financials_logic.js`.

#### --- FILE: `partials/journal_entry_create_content.html` ---
-   **UI**: A dynamic table for JE lines with a sticky footer showing totals.
-   **Interactivity**: Rows can be added/removed. The footer totals update instantly. The save button is disabled until the entry is balanced (Debits = Credits).
-   **JS Module**: `financials_logic.js`.

#### --- FILE: `partials/fiscal_year_list_content.html` ---
-   **UI**: An accordion-based layout for fiscal years and periods. Uses modals for all actions.
-   **Interactivity**: The "Audit Log" modal fetches its content dynamically via a `fetch` call.

#### --- FILE: `partials/reconciliation_list_content.html` ---
-   **UI**: A filterable table of bank reconciliation periods.
-   **Interactivity**: All links and forms are handled by the dynamic content loader.

#### --- FILE: `partials/reports/*` ---
-   **UI**: Data-heavy tables designed for clarity and printing.
-   **Interactivity**: The filter forms on the parent pages are handled by the dynamic content loader to refresh the report partial without a full page reload. Hierarchical reports use recursive `include`s.
-   **JS Module**: `batch_production_variance_report_logic.js`, `tax_reconciliation_report_logic.js` for their respective reports.

#### --- FILE: `partials/visuals_content.html` ---
-   **UI**: A tabbed layout containing multiple `<canvas>` elements for charts.
-   **Interactivity**: Tabs control which filter fields are visible. All charts are rendered client-side using data from JSON islands.
-   **JS Module**: `visuals_logic.js`.

---

### Part 4: Modal Partials (`modals/`)

These files are reusable Bootstrap modal components.

#### --- FILE: `modals/create_fiscal_year_modal.html`, `edit_fiscal_year_modal.html`, `delete_fiscal_year_modal.html`, `manage_period_modal.html`, `view_audit_log_modal.html` ---
-   **Purpose**: These are all included within `fiscal_year_list_content.html` to provide the UI for creating, editing, deleting, and managing fiscal periods and their audit logs. They contain standard forms and confirmation dialogs.