# File: gipcco_project/inventory/models/operational.py
**Purpose:** This file defines the foundational master data models for the inventory and operational side of the ERP. These models represent core entities like products and suppliers, which are then referenced by transactional models throughout the system.

### Class: `Company`
- **Description:** A master data model representing an external business entity, primarily used as a "Supplier". It is referenced in purchasing transactions (`PurchaseOrder`, `InventoryLog`) and accounts payable (`SupplierInvoice`).

### Class: `Product`
- **Description:** The master record for any item that is bought, sold, or consumed by the company. This includes raw materials, packaging materials, maintenance supplies (MRO), and final products. It is the central point for defining an item's properties and its default accounting behavior.
- **Key Fields & Relationships:**
    - `product_type`: An essential category (`RAW_MATERIAL`, `FINAL_PRODUCT`, `MRO`, etc.) that drives behavior and default accounting rules throughout the system.
    - `moving_average_cost`: The calculated, perpetually updated unit cost of the product. This is the primary valuation method used for all inventory transactions.
    - `override_*_account`: A set of optional foreign keys to `Account`. These fields allow for specific products to have their financial transactions posted to different GL accounts than the default ones specified in `ProductTypeAccountingSettings`. This provides granular accounting control.
    - `is_amortizable`: A boolean flag that signals to the `InventoryConsumption` process that the value of this item, when consumed internally, should be treated as a prepaid asset rather than a direct expense.
- **Data Integrity:**
    - The `clean()` method acts as a critical guardrail. It prevents users from changing a product's accounting override fields after it has been used in any financial transaction. This enforces sub-ledger integrity and prevents historical financial data from becoming inconsistent.

### Class: `ProductTag`
- **Description:** A simple tagging model to allow for flexible, user-defined categorization of products, aiding in filtering and reporting.

### Class: `InventoryLog`
- **Description:** The fundamental ledger for all incoming raw material and MRO stock. Each distinct receipt of goods (e.g., from a purchase order) creates a new `InventoryLog` record, which represents a specific quantity of a product received at a specific cost. This model is the source for all subsequent consumptions.
- **State Transitions & Business Logic:**
    - **Status Workflow:** `Quarantined` (default) -> `Released` -> `Rejected` / `Scrapped` / `Voided`. Items must be `Released` from quality control before they can be consumed in production or for internal use.
    - **VAT Treatment:** The `vat_treatment` field (`Recoverable` vs. `Capitalized`) determines the financial impact of VAT. If `Capitalized`, the VAT amount is added to the inventory's cost basis instead of being booked to a separate receivable account.
- **Key Fields & Relationships:**
    - `po_item`: A link back to the `PurchaseOrderItem` that authorized this receipt, enabling PO vs. Receipt variance tracking.
    - `costing_unit_price`: The final, calculated unit cost for this specific log, which includes the base price plus any capitalized VAT and allocated landed costs. This value is snapshotted and stored permanently on the log for perfect auditability.
    - `landed_cost_component`: The portion of the `costing_unit_price` that is attributable to landed costs, providing cost analysis transparency.
- **Performance & Data Access:**
    - The model uses a custom manager, `InventoryLogQuerySet`, which provides the `with_remaining_quantity` method. This is the single, authoritative source for calculating the available stock of any given log, using robust subqueries to prevent common ORM performance bugs.
