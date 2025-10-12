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
