# File: gipcco_project/inventory/models/purchasing.py
**Purpose:** This file defines models supporting advanced purchasing workflows, specifically focusing on supplier returns and the complex process of handling and allocating landed costs (additional costs beyond the purchase price, such as freight and customs).

### Class: `LandedCostType`
- **Description:** A master data model that defines the different categories of landed costs the company incurs. Examples include 'Freight', 'Customs Duty', 'Insurance'. This provides a structured way to track and allocate these costs.

### Class: `PurchaseReturn`
- **Description:** The header model for a return of goods to a supplier. It groups the items being returned and tracks the overall status of the return process.
- **Key Fields & Relationships:**
    - `status`: A state machine (`Pending`, `Shipped`, `Completed`) that follows the physical and administrative progress of the return.

### Class: `PurchaseReturnItem`
- **Description:** Represents a single product being returned to a supplier.
- **Key Fields & Relationships:**
    - `original_receipt`: A critical foreign key to the `InventoryLog` from which the goods were initially received. This provides an indisputable link to the original cost of the item, ensuring the financial transaction for the return is valued correctly.
- **Integration Points:**
    - A `PurchaseReturnItem` is the source for a corresponding negative `InventoryAdjustment`, which removes the item from stock.

### Class: `SupplierDebitMemo`
- **Description:** The financial document that formalizes a reduction in the amount owed to a supplier, typically created as the final step of a `PurchaseReturn`. It is the transactional record for the Accounts Payable sub-ledger.
- **Key Fields & Relationships:**
    - `purchase_return`: A `OneToOneField` linking the financial debit memo directly to the physical return event that caused it.
    - `journal_entry`: A link to the journal entry that officially records the reduction in liability (Debit Accounts Payable).

### Landed Cost Models

#### Class: `LandedCostInvoice`
- **Description:** Represents an invoice received from a third-party vendor (e.g., a shipping company, customs broker) for landed cost services. This model captures the liability to the third-party vendor.
- **Key Fields & Relationships:**
    - `purchase_order`: An optional link to a PO. This helps in variance analysis between estimated and actual landed costs.
- **Financial Impact:**
    - Posting this invoice creates a journal entry to Debit a "Landed Costs Clearing" account and Credit Accounts Payable (to the third-party vendor). The value sits in the clearing account until it is allocated to inventory.

#### Class: `LandedCostInvoiceItem`
- **Description:** A line item on a `LandedCostInvoice`, specifying the `amount` for a particular `LandedCostType`.

#### Class: `PurchaseOrderLandedCost`
- **Description:** This model supports an estimation-first (NetSuite-style) landed cost workflow. It allows users to record an *estimated* amount for each `LandedCostType` directly on the `PurchaseOrder` *before* the goods or third-party invoices arrive.
- **Integration Points:**
    - When an `InventoryLog` is received against a PO with these estimates, the `create_je_for_inventory_receipt` service prorates the estimated cost and includes it in the initial inventory valuation. This results in a more accurate inventory cost from day one, with a corresponding credit to an "Accrued Landed Costs" liability account. Variances are then booked when the actual `LandedCostInvoice` is posted.
