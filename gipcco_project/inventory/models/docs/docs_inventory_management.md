# File: gipcco_project/inventory/models/inventory_management.py
- **Purpose:** Defines models for managing the core inventory and manufacturing processes.

- `ShopOrderTemplate`: A template for creating production plans (shop orders).
- `TemplateItem`: A single raw material item within a shop order template.
- `Batch`: Represents a production plan or "Shop Order".
- `BatchItem`: A single raw material item consumed in a production batch.
- `ProductionReturn`: Represents the return of raw materials from production back to inventory.
- `PurchaseOrder`: Represents a purchase order for buying materials from a supplier.
- `PurchaseOrderItem`: A single item within a purchase order.
- `FinishedProductReceipt`: Represents the receipt of finished goods from a production batch.
- `ReceiptSubBatch`: Represents a sub-batch within a finished product receipt.
- `Customer`: Represents a customer.
- `SalesOrder`: Represents a sales order from a customer.
- `SalesOrderItem`: A single item within a sales order.
- `FinishedProductDispatch`: Represents the dispatch of finished goods to a customer.
- `FixedAsset`: Represents an individual fixed asset.
- `InventoryConsumption`: Represents the internal consumption of inventory for non-production purposes.
Key model changes and implementation notes (current):

- `ShopOrderTemplate`:
  - New optional field `bottle_size_ml` (PositiveIntegerField) to support overhead allocation by volume.


- `Batch` and continuation semantics:
  - Fields: `template` (FK), `shop_order_number`, `batch_number`, `creation_date`, `is_customized`, `is_continuation`, `parent_batch` (FK to self), `notes`.
  - **NEW**: `status` field now includes `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`. Default is `DRAFT`.
  - **NEW**: Approval workflow fields: `submitted_by` (FK to User), `submitted_at`, `approved_by` (FK to User), `approved_at`.
  - Business rules (service layer enforces):
    - If `is_continuation` is True the `parent_batch` must reference the original batch; continuation batches share the same `shop_order_number`.
    - Finished goods receipts must be created only against the original (parent) batch.
    - Final product cost = sum(parent batch cost + all continuation batch costs).
  - New fields for allocation drivers: `machine_hours_consumed`, `labor_hours_consumed` (FloatFields).


- `BatchItem`:
  - Fields: `primitive_product`, `theoretical_quantity`, `actual_quantity`, `source_log` (FK), `cost_at_consumption` (Decimal, 3 d.p.).
  - `cost_at_consumption` is set by costing routines called from services (e.g., `recalculate_cost_history_for_product`).


- `ProductionReturn`:
  - Fields: `product`, `source_log` (FK), optional `batch` (FK), `quantity`, `return_date`, `notes`, `status` (default POSTED).
  - Cancellation guard: cannot cancel if returned stock was consumed later; service checks `BatchItem` consumption after `return_date`.


- `FinishedProductReceipt` guidance:
  - Remaining quantity formula: `remaining = total_quantity_produced - total_dispatched + total_adjusted`.
  - Use Subqueries + `Coalesce` when aggregating `total_dispatched` and `total_adjusted` to avoid join-multiplication bugs.
  - Key fields: `total_cost`, `total_quantity_produced`, `allocated_overhead_cost`, `receipt_date`, `release_date`, `status`.


- `PurchaseOrderItem` & `InventoryConsumption`:
  - `PurchaseOrderItem` includes `base_price_per_unit`, `vat_rate`, `withholding_tax_rate` to support landed-cost logic.
  - `InventoryConsumption` includes a `consumption_type` enum to indicate capitalization vs. expense and keeps `cost_at_consumption`.

Notes:

- Behavioral constraints (continuation rules, returns) are enforced in services; models document intent only.
