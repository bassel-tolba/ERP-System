# File: gipcco_project/inventory/models/purchasing.py
- **Purpose:** Defines models related to the purchasing and supplier returns workflow, including landed costs and debit memos.

### Models:

- `LandedCostType`:
  - **Description:** A master table to define different types of landed costs that can be capitalized into inventory value (e.g., 'Freight', 'Customs Duty', 'Insurance').

- `PurchaseReturn`:
  - **Description:** The header model for a return of goods to a supplier. It tracks the supplier, return date, and the status of the return process (`Pending`, `Shipped`, `Completed`).

- `PurchaseReturnItem`:
  - **Description:** A line item within a `PurchaseReturn`. It links directly to the `original_receipt` (`InventoryLog`) from which the goods came, ensuring the correct cost is used for the return transaction.

- `SupplierDebitMemo`:
  - **Description:** Represents the financial document issued to a supplier to reduce the accounts payable balance, typically created from a `PurchaseReturn`. It records the total value of the credit being claimed and links to the final journal entry.

- `LandedCostInvoice`:
  - **Description:** Represents an invoice from a third-party (e.g., a shipping company) for landed costs that need to be applied to inventory receipts. It tracks the vendor, invoice details, total amount, and status (`Draft`, `Awaiting Payment`, `Paid`).
  - **NEW**: `purchase_order` (FK) to link to the related Purchase Order for variance calculation.

- `LandedCostInvoiceItem`:
  - **Description:** A line item on a `LandedCostInvoice`, linking a specific `LandedCostType` and amount.

- `PurchaseOrderLandedCost`:
  - **Description:** Stores an estimated landed cost for an entire Purchase Order. This is the core of the NetSuite-style estimation-first approach.
