Of course. Here is a highly detailed, file-by-file logical representation of the Gipcco project's frontend JavaScript architecture.

---

## Detailed Frontend JavaScript Architecture Overview

The frontend is a sophisticated "HTML-over-the-wire" system. It uses Django for the initial server-side rendering and is then enhanced by a suite of JavaScript modules to create a fast, responsive, single-page application (SPA)-like experience. The architecture is modular and event-driven, centered around a core dynamic content loader.

### Core Engine: `dynamic_content_loader.js`

This file is the heart and brain of the frontend's dynamic behavior. It eliminates the need for full-page reloads for most user actions.

-   **Primary Goal**: To intercept user navigation and form submissions, fetch only the necessary HTML content from the server, and intelligently swap it into the current page.

-   **Key Components & Workflow**:
    1.  **Event Interception**: It attaches global event listeners to the `document.body` for `click` events on links and will be extended to handle `submit` events for forms. It cleverly filters out external links, links that open new tabs, modal toggles, and links explicitly marked with `data-no-dynamic`.
    2.  **`loadContent(url)` function**:
        -   This is the main workhorse. When triggered, it initiates a `fetch()` request to the given URL.
        -   **Partial Request Header**: It adds a custom HTTP header, `X-Partial-Request: "true"`, to the request. The Django backend uses this header to decide whether to render the full `layout.html` or just the content partial within `_partial_layout.html`.
        -   **UI Feedback**: It provides immediate user feedback by slightly dimming the content area (`contentContainer.style.opacity = "0.5"`) while the new content is loading.
        -   **DOM Manipulation**: Upon receiving the lightweight HTML partial, it replaces the `innerHTML` of the main `<div id="page-content">`.
        -   **Browser History**: It uses the `history.pushState()` API to update the browser's URL and add the navigation to the session history, ensuring the back and forward buttons work as expected.
    3.  **`window.initializePluginsInContent(container)` function**:
        -   **The Orchestrator**: This is the most critical function for interactivity. After new content is injected into the DOM, this function is called to "bring it to life".
        -   **Generic Initializers**: It runs initializers for common plugins on *all* new content. This includes activating `flatpickr` on any element with the `.datepicker` class and `TomSelect` on elements with `.searchable-select`. This is the "Don't Repeat Yourself" (DRY) principle in action.
        -   **Page-Specific Initializers (`pageInitializers` object)**: This is a key design pattern. It's a map where keys are unique CSS selectors (like `#batchEditForm` or `#reconciliationWorkspace`) and values are the specific initialization functions (e.g., `initBatchViewLogic`, `initReconciliationManageLogic`). The loader iterates through this map, and if a selector is found in the newly loaded content, it executes the corresponding function. This makes the loader highly extensible and keeps page-specific logic cleanly separated.
    4.  **Utility Functions**:
        -   **`getDataFromIsland(islandId)`**: A crucial helper function that safely parses JSON data from `<script>` tags (e.g., `<script id="products-data" type="application/json">`). This "JSON island" technique is the primary method for passing complex data from Django to the client-side JavaScript without needing extra API calls on page load.

---

### Page-Specific Logic Modules (`*_logic.js`)

These files contain the specialized logic for individual pages or features. They are designed as self-contained modules that are called by `dynamic_content_loader.js` when their corresponding page content is loaded.

#### --- FILE: `dashboard_logic.js` ---

-   **Associated Partials**: `partials/dashboard_content.html`
-   **Initializer Function**: `initDashboardLogic`
-   **Core Responsibilities**:
    1.  **Dynamic Tags**: Manages the "Tags" dropdown. It listens for changes on the "Product" dropdown and makes an API call to `api_product_tags` to fetch and populate the relevant tags for the selected product.
    2.  **Purchase Order Workflow**:
        -   Controls the "Receive Against PO" checkbox.
        -   Toggles the visibility of the PO selection fields versus the manual price entry fields.
        -   Orchestrates a series of chained, dependent API calls:
            -   When a supplier is chosen (`po_supplier_id`), it calls `apiSupplierOpenPos` to fetch that supplier's open POs.
            -   When a PO is chosen (`purchase_order_id`), it calls `apiPoItems` to fetch the remaining items on that order.
        -   **Auto-Population**: When a specific PO item is selected, it automatically fills in the main form's "Product," "Company," and "Quantity" fields and displays the applicable tax rates, significantly speeding up the receiving process.

#### --- FILE: `records_logic.js` ---

-   **Associated Partials**: `partials/records_content.html`
-   **Initializer Function**: `initRecordsLogic`
-   **Core Responsibilities**:
    -   Manages the complex "Edit Record" modal.
    -   When the modal opens, it reads all the relevant data for the record from the `data-*` attributes on the button that was clicked.
    -   It replicates the entire "Purchase Order Workflow" from the dashboard logic *inside the modal*, allowing a user to link or change the PO association for an existing receipt.
    -   It handles the asynchronous loading of associated tags and pre-selects them based on the record's data.

#### --- FILE: `purchase_order_create_logic.js` ---

-   **Associated Partials**: `partials/purchase_order_create_content.html`, `partials/purchase_order_edit_content.html`
-   **Initializer Function**: `initPurchaseOrderCreateLogic`
-   **Core Responsibilities**:
    -   Reads the list of available products from the `products-data` JSON island.
    -   Dynamically adds and removes line item rows to the purchase order table.
    -   Initializes a `TomSelect` instance on the "Product" dropdown for each new row, populating it with the product data. It correctly sets `dropdownParent: 'body'` to prevent the dropdown from being clipped inside the table.
    -   On any input change within a row (quantity, price, tax), it instantly recalculates and updates the "Line Total" and "Net Payable" amounts for that row.

#### --- FILE: `sales_order_create_logic.js` ---

-   **Associated Partials**: `partials/sales_order_create_content.html`
-   **Initializer Function**: `initSalesOrderCreateLogic`
-   **Core Responsibilities**:
    -   On initialization, it makes an API call to `api_get_sellable_stock` to get a real-time list of all finished goods available for sale.
    -   Handles the "Add Item" and "Remove Item" buttons for the sales order line items table.
    -   For each new row, it initializes a `TomSelect` dropdown populated with the fetched sellable stock data, allowing users to select specific batches.

#### --- FILE: `shop_order_templates_logic.js` ---

-   **Associated Partials**: `partials/shop_order_templates_content.html`
-   **Initializer Function**: `initShopOrderTemplatesLogic`
-   **Core Responsibilities**:
    -   Manages the "Create Template" modal.
    -   It reads product data and potential "copy-from" template data from JSON islands.
    -   Dynamically adds/removes material rows within the modal form.
    -   **Copy Functionality**: If the page was loaded with a `?copy_from=ID` query parameter, the script detects the `source-template-data` island and pre-populates the modal with the items from the source template, allowing for quick creation of similar BOMs.

#### --- FILE: `create_batch_logic.js` ---

-   **Associated Partials**: `partials/create_batch_content.html`
-   **Initializer Function**: `initCreateBatchLogic`
-   **Core Responsibilities**:
    -   **Template Loading**: When a `ShopOrderTemplate` is selected, it reads the `template-data` JSON island to find the required materials and dynamically builds the materials table.
    -   **Stock Allocation**: For each material row, it filters the global `available-stock-data` island to find and populate the "Source Stock (QC)" dropdown with only the relevant, available inventory lots.
    -   **Quantity Splitting**: Implements the logic for the "Split Quantity" button, which allows a user to consume part of a required quantity from one stock source and automatically create a new row for the remainder, pre-selecting the next available source.
    -   **Continuation Logic**: Toggles the UI between a standard batch and a "continuation" batch, showing/hiding the "Parent Batch" selector and auto-filling the template and Shop Order number when a parent is selected.
    -   **Real-time Validation**: Checks if the entered `actual_quantity` exceeds the available quantity in the selected QC source and if the source's date is not after the production date, providing immediate visual feedback.

#### --- FILE: `batch_view_logic.js` ---

-   **Associated Partials**: `partials/batch_view_content.html`
-   **Initializer Function**: `initBatchViewLogic`
-   **Core Responsibilities**:
    -   **Quantity Recalculation**: Listens for changes in the "Batch Number From/To" fields and automatically recalculates the `theoretical_quantity` and `actual_quantity` for all items in the table based on their `data-base-quantity`.
    -   **Event Delegation**: Handles the "Delete Item" button clicks within the materials table, setting the action of a hidden form and submitting it to delete the item.
    -   Manages the "is continuation" checkbox and the associated parent batch selector, including auto-filling the shop order number when a parent is selected.

#### --- FILE: `financials_logic.js` ---

-   **Associated Partials**: `partials/supplier_invoice_create_content.html`, `partials/customer_invoice_create_content.html`, `partials/journal_entry_create_content.html`, `partials/reconciliation_manage.html`
-   **Initializer Functions**: Contains multiple initializers: `initCreateSupplierInvoiceLogic`, `initCreateCustomerInvoiceLogic`, `initJournalEntryCreateLogic`, `initReconciliationManageLogic`.
-   **Core Responsibilities**:
    -   **Invoice Creation**: For both supplier and customer invoices, it listens to the supplier/SO dropdown, makes an API call to fetch uninvoiced items (`apiUninvoicedReceipts` or `apiUninvoicedDispatches`), and dynamically builds the selection table. It calculates the invoice total in real-time.
    -   **Journal Entry Creation**: Manages the dynamic formset for creating JE lines. It adds/removes rows, syncs the visible debit/credit inputs with hidden form fields, and calculates the running totals in the sticky footer. It enforces balance by disabling the save button until Debits = Credits.
    -   **Bank Reconciliation**: This is the most complex module.
        -   It manages the state of selected items from both the "Bank Statement" and "Internal Transactions" tables.
        -   When two items are selected, it checks if their amounts match. If they do, it shows a confirmation modal.
        -   Upon confirmation, it sends the match data to the `api_match_transactions` endpoint.
        -   It manages the "Create Adjustment" modal, dynamically populating the account dropdown with either income or expense accounts based on the transaction amount.
        -   It handles the form submission for creating and matching adjustments via the `api_create_adjustment_and_match` endpoint.

#### --- FILE: `visuals_logic.js` ---

-   **Associated Partials**: `partials/visuals_content.html`
-   **Initializer Function**: `initVisualsLogic`
-   **Core Responsibilities**:
    -   **Tab Management**: Controls the visibility of different filter sections based on which analysis tab ("Raw Material", "Finished Product", "Expense") is active.
    -   **Data Consumption**: Reads pre-calculated chart data from numerous JSON islands on the page.
    -   **Chart Rendering**: Uses the Chart.js library to instantiate and render all the graphs and charts on the dashboard. It contains specific configurations for each chart type (line, bar, pie, doughnut).
    -   **Graceful Degradation**: Includes a `showNoDataMessage` function to display a user-friendly message inside a chart's container if there's no data to render, preventing blank spaces on the page.

#### --- Remaining Logic Files ---

-   **`expenses_page_logic.js`**: Manages the dynamic "Source Log" dropdown on the expense dashboard, fetching available stock for a selected consumable product.
-   **`ledger_logic.js`**: Controls the details modal on the ledger page, showing different information based on the transaction type (`IN`, `OUT`, `CONSUME_OUT`). It also handles the API call to fetch and display the full batch analysis in a second modal.
-   **`manage_expenses_logic.js`**: Populates the "Edit" modals on the Manage Expenses page with the correct data from the selected table row and sets the form's `action` URL dynamically.
-   **`production_returns_logic.js`**: Dynamically fetches and populates the "Original QC Source" dropdown based on the selected product, showing only sources that have actually been consumed in production.
-   **`receive_finished_product_logic.js`**: Handles the dynamic addition and removal of "sub-batch" rows on the finished product receipt form.
-   **`tax_reconciliation_report_logic.js`**: Hijacks the filter form submission to use the dynamic content loader instead of causing a full page refresh.
-   **`close_period_logic.js`**: On the period closing page, it polls the `api_period_checklist_status` endpoint and updates the UI of the checklist with success/failure icons and details. It enables the finalization button only when all checks pass.
-   **`batch_production_variance_report_logic.js`**: Reads chart data from a JSON island and renders the quantity and cost variance charts using Chart.js.
-   **`theme_season_logic.js`**: A non-essential, easter-egg style script for managing themes and adding seasonal visual effects. It's separate from the core application logic.