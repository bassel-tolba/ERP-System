# File: gipcco_project/inventory/models/inventory_counts.py
- **Purpose:** Defines models for managing physical inventory counts and adjustments.

- `InventoryCount`: Header for a physical inventory counting event.
- `InventoryCountItem`: A single product line within an inventory count.
- `InventoryAdjustment`: An auditable record of a single, granular inventory adjustment. Now includes a `RETURN_TO_SUPPLIER` reason code and a direct link to a `PurchaseReturnItem` to create a clear audit trail from a supplier return to the inventory adjustment.

More details (current implementation):

- `InventoryCount` fields & behavior:
  - `count_date` (DateField), `status` (TextChoices: IN_PROGRESS, PENDING_ALLOCATION, COMPLETED), `reason`, `created_by` (FK to user), `created_at`.
  - Model Meta: custom `db_table` = `inventory_counts`, ordering by `-count_date`.

- `InventoryCountItem` fields & behavior:
  - `inventory_count` (FK -> InventoryCount), `product` (FK -> Product), `system_quantity` (FloatField), `counted_quantity` (FloatField, nullable).
  - Has a `variance_quantity` property which returns `counted_quantity - system_quantity` (0.0 when not counted).
  - `unique_together` (`inventory_count`, `product`) to guarantee one line per product per count.

- `InventoryAdjustment` fields & behavior (important changes):
  - Core fields: `product`, `adjustment_quantity` (FloatField — negative for shortages, positive for overages), `adjustment_date`, `cost_at_adjustment` (DecimalField, 3 d.p.), `reason_code` (TextChoices including SHRINKAGE, DAMAGE, DATA_ENTRY_ERROR, OVERAGE_FOUND, SALES_RETURN_STOCK, RETURN_TO_SUPPLIER, OTHER), `notes`.
  - Status workflow: `status` (TextChoices: DRAFT, POSTED) — adjustments are created in `DRAFT` and later finalized to `POSTED`.
  - Accounting linkage: optional `journal_entry` FK (SET_NULL) to store the resulting JE once posted.
  - Source linking (mutually exclusive): `source_log` (InventoryLog), `source_finished_product` (FinishedProductReceipt), `source_sales_return_item` (OneToOne to SalesReturnItem), `source_purchase_return_item` (OneToOne to PurchaseReturnItem). The model `clean()` enforces at most one source and requires a source if the adjustment is not part of an `InventoryCount`.
  - Context: optional `inventory_count` FK to relate an adjustment to a physical count; adjustments can also be created outside of a count but must then have a source.
  - Meta: `ordering = ['-adjustment_date']`, `db_table = 'inventory_adjustments'`.

- Validation and audit notes:
  - `clean()` raises a `ValidationError` if more than one source is set, or if no source is set when the adjustment isn't part of an `InventoryCount`.
  - `__str__` renders the direction (Shortage/Overage) and absolute quantity for easy admin visibility.
