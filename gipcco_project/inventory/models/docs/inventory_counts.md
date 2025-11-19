# File: gipcco_project/inventory/models/inventory_counts.py
**Purpose:** This file contains the models for managing the physical inventory stock-taking process. It provides the structure for recording system vs. physical counts, identifying variances, and creating auditable adjustments to correct the inventory records.

### Class: `InventoryCount`
- **Description:** The header for a physical inventory counting event. It acts as a container for all the individual product counts performed on a specific date for a specific reason.
- **Key Fields & Relationships:**
    - `count_date`: The date the physical count was performed.
    - `status`: A state machine (`In Progress`, `Pending Allocation`, `Completed`) that tracks the lifecycle of the count event.
    - `reason`: A text field explaining the purpose of the count (e.g., "Annual Stock-take", "Cycle Count - Aisle 5").

### Class: `InventoryCountItem`
- **Description:** Represents a single product line within an `InventoryCount`. It captures a snapshot of the system's expected quantity at the time of the count and provides a field to enter the physically counted quantity.
- **Key Fields & Relationships:**
    - `inventory_count`: Links the item back to its parent count event.
    - `product`: The product being counted.
    - `system_quantity`: The quantity the ERP calculated was on hand when the count started. This value is frozen for comparison.
    - `counted_quantity`: The actual quantity found during the physical count.
- **Business Logic:**
    - `variance_quantity` property: A calculated field that shows the difference (`counted_quantity` - `system_quantity`). A positive variance is an overage, and a negative variance is a shortage. This is the key value that needs to be adjusted.
- **Data Integrity:**
    - `unique_together = ('inventory_count', 'product')`: Guarantees that a product can only appear once within a single count event.

### Class: `InventoryAdjustment`
- **Description:** A highly versatile and auditable model that records a single, granular change to inventory quantity and value. This is the definitive record for any adjustment, whether it originates from a physical count, a sales return, a supplier return, or damage.
- **Key Fields & Relationships:**
    - `adjustment_quantity`: The quantity to adjust by. **Crucially, a negative number indicates a decrease (shortage/shrinkage), and a positive number indicates an increase (overage).**
    - `cost_at_adjustment`: The unit cost of the item at the moment of adjustment. This value is snapshotted to ensure the financial transaction is accurate and auditable.
    - `reason_code`: A structured reason for the adjustment, which can drive reporting and determine which GL accounts are used (e.g., `SHRINKAGE` vs. `DAMAGE` vs. `SALES_RETURN_STOCK`).
    - `status`: A workflow field (`Draft`, `Posted`). Adjustments are created as `Draft` and only impact the GL when moved to `Posted`.
    - `journal_entry`: A link to the `JournalEntry` created when the adjustment is posted.
    - **Source Linking Fields**: A set of mutually exclusive foreign keys (`source_log`, `source_finished_product`, `source_sales_return_item`, `source_purchase_return_item`) that provide an explicit link back to the specific stock item or transaction that is being adjusted.
- **Data Integrity & Validation:**
    - The `clean()` method enforces that an adjustment can only have one source, ensuring data clarity. It also mandates a source if the adjustment is not part of a formal `InventoryCount`.
- **Financial Impact:**
    - When an adjustment's status is changed to `Posted`, a signal triggers the `create_je_for_inventory_adjustment` service. This service creates a journal entry to debit/credit the appropriate inventory account and an offsetting expense/gain/clearing account based on the `reason_code`.
