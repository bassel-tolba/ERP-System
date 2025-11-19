# File: gipcco_project/inventory/models/inventory_management.py
**Purpose:** This is a large, central file defining the core models for the entire operational lifecycle: manufacturing, purchasing, sales, fixed assets, and internal inventory movements. These models represent the primary business objects and transactions within the ERP.

### Manufacturing & Production

#### Class: `ShopOrderTemplate`
- **Description:** The "Bill of Materials" or "recipe" for a finished product. It defines which raw materials (`TemplateItem`) and in what theoretical quantities are required to produce one unit or batch of a `final_product`.
- **Key Fields & Relationships:**
    - `bottle_size_ml`: A field used as a potential driver for volume-based overhead allocation.
    - `bottle_size_ml`: A field used as a potential driver for volume-based overhead allocation.

#### Class: `TemplateItem`
- **Description:** A line item within a `ShopOrderTemplate`, specifying a single raw material and its required quantity.

#### Class: `Batch`
- **Description:** Represents a "Production Plan" or "Shop Order". This is the primary transactional document for manufacturing, authorizing and tracking the consumption of raw materials to produce finished goods.
- **State Transitions & Business Logic:**
    - **Continuation Logic:** The `is_continuation` and `parent_batch` fields allow for tracking supplemental material issues to an existing production run without altering the original plan. Services must aggregate costs from a parent and all its continuations to find the true total production cost.
    - **Status Workflow:** A full approval workflow is defined: `Draft` -> `Pending Approval` -> `Approved` -> `In Progress` -> `Completed` / `Cancelled`. Financial transactions (material consumption JE) only occur when the status moves to `In Progress`.
- **Key Fields & Relationships:**
    - **Approval Workflow Fields**: `submitted_by`, `submitted_at`, `approved_by`, `approved_at` track the approval process.
    - `machine_hours_consumed`, `labor_hours_consumed`: Fields that capture actual resource usage, serving as drivers for overhead cost allocation.
- **Security:** Defines custom permissions (`can_submit_batch`, `can_approve_batch`, etc.) to control the production workflow.
 
#### Class: `BatchItem`
- **Description:** A line item on a `Batch`, representing the actual consumption of a raw material from a specific `source_log` (`InventoryLog`).
- **Key Fields & Relationships:**
    - `cost_at_consumption`: The unit cost of the raw material is snapshotted here when production starts. This freezes the cost for this specific transaction, ensuring cost-of-production calculations are stable and auditable, adhering to the immutable ledger principle.

#### Class: `BatchItem`
- **Description:** A line item on a `Batch`, representing the actual consumption of a raw material from a specific `source_log` (`InventoryLog`).
- **Key Fields & Relationships:**
    - `cost_at_consumption`: The unit cost of the raw material is snapshotted here when production starts. This freezes the cost for this specific transaction, ensuring cost-of-production calculations are stable and auditable, adhering to the immutable ledger principle.

#### Class: `ProductionReturn`
- **Description:** Records the return of unused raw materials from the factory floor (`Batch`) back to the warehouse.
- **Financial Impact:** Creation of this record triggers a journal entry to move value from the Work-in-Progress (WIP) account back to the Raw Material Inventory account.

#### Class: `FinishedProductReceipt`
- **Description:** Records the output of a production run, representing the creation of new, sellable finished goods inventory.
- **State Transitions & Business Logic:**
    - **Status Workflow:** `Quarantined` (default) -> `Released` -> `Rejected` / `Cancelled`. Goods must be `Released` by QC before they can be sold.
- **Key Fields & Relationships:**
    - `total_cost`: The cost of raw materials consumed to produce this batch of goods.
    - `allocated_overhead_cost`: The portion of factory overhead costs applied to this receipt, added to the total cost to determine the final inventory value.
- **Financial Impact:** Creation of a `FinishedProductReceipt` triggers a JE to move the total value (materials only before the overhead engine runs later at period end) from the WIP account to the Finished Goods Inventory account.
- **Performance Considerations:**
    - A detailed developer note explains the correct, performant way to calculate `remaining_quantity` using `Subquery` annotations to avoid SQL join multiplication bugs. This is a critical architectural pattern.
    - The model uses a custom manager, `FinishedProductReceiptQuerySet`, which provides the `with_remaining_quantity` method as the authoritative way to query available stock.

### Purchasing

#### Class: `PurchaseOrder`
- **Description:** A formal document issued to a supplier to procure goods.

#### Class: `PurchaseOrderItem`
- **Description:** A line item on a `PurchaseOrder`.
- **Key Fields & Relationships:**
    - `landed_cost_allocation_percentage`: A field for pro-rating estimated PO-level landed costs across different items.
    - `is_closed`: A flag to manually close a line item, indicating no further receipts are expected, even if under-delivered.

### Sales & Customer Management

#### Class: `Customer`, `SalesOrder`, `SalesOrderItem`
- **Description:** Standard models representing the sales workflow, from customer master data to the sales order and its specific line items.

#### Class: `FinishedProductDispatch`
- **Description:** Records the shipment of finished goods to a customer, fulfilling a `SalesOrderItem`. This is the trigger for revenue and COGS recognition.
- **State Transitions & Business Logic:**
    - **Status Workflow:** `Completed` (default) -> `Cancelled`. A dispatch can be cancelled via a service that creates a reversing journal entry.
- **Key Fields & Relationships:**
    - `cost_at_dispatch`: The unit cost of the finished good is snapshotted at the time of sale. This value is used for the COGS entry.
    - `status`: A workflow field (`Completed`, `Cancelled`) to manage the state of the dispatch non-destructively.
- **Financial Impact:** Creation of a `FinishedProductDispatch` triggers a compound journal entry that (1) Debits COGS and Credits Finished Goods Inventory, and (2) Debits Accounts Receivable and Credits Sales Revenue and VAT Payable.

### Fixed Assets & Internal Consumption

#### Class: `FixedAsset`
- **Description:** The master record for a single fixed asset. It serves as the sub-ledger for fixed asset control accounts in the GL.
- **Key Fields & Relationships:**
    - Links to three distinct GL accounts: the asset's control account, its accumulated depreciation account, and its depreciation expense account.
- **Business Logic:**
    - Properties like `depreciable_base`, `accumulated_depreciation`, and `net_book_value` provide calculated financial values for reporting.

#### Class: `InventoryConsumption`
- **Description:** Records the internal use of inventory for non-production purposes (e.g., using spare parts for maintenance, office supplies).
- **Key Fields & Relationships:**
    - `quantity_consumed`: A `FloatField` representing the amount of the item consumed.
    - `consumption_type`: A critical field (`Expense`, `Capitalize`, `Amortize`) that determines the accounting treatment of the consumption.
- **Financial Impact:**
    - **`Expense`**: Debits an expense account.
    - **`Capitalize`**: Debits a fixed asset account, increasing its book value.
    - **`Amortize`**: Debits a prepaid expense asset account, to be expensed over time.
- **Data Integrity:** The `clean()` method enforces strict rules based on `consumption_type`, ensuring a fixed asset is provided for capitalization, etc.
