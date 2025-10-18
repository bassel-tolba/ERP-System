# File: gipcco_project/inventory/models/inventory_counts.py
- **Purpose:** Defines models for managing physical inventory counts and adjustments.

- `InventoryCount`: Header for a physical inventory counting event.
- `InventoryCountItem`: A single product line within an inventory count.
- `InventoryAdjustment`: An auditable record of a single, granular inventory adjustment. Now includes a `SALES_RETURN_STOCK` reason code and a direct link to a `SalesReturnItem` to create a clear audit trail from a customer return to the inventory adjustment.
