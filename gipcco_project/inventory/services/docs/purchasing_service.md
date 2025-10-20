# File: gipcco_project/inventory/services/purchasing_service.py
- **Purpose:** Manages the complete purchasing and supplier return lifecycle, including three-way match validation, landed cost allocation, and debit memo creation.

### Functions:

- `post_supplier_invoice(invoice: SupplierInvoice)`:
  - **Description:** The core of the three-way match process. It posts a `Draft` supplier invoice to the General Ledger.
  - **Workflow:**
    1.  Validates that the invoice is in `Draft` status and has all required data (actual subtotal and VAT).
    2.  Calculates the total value of all linked inventory receipts (the amount accrued in the GRNI account).
    3.  Compares the receipt value to the actual invoice value to determine the Purchase Price Variance (PPV).
    4.  Creates a single, balanced journal entry that:
        - **Debits:** Goods Received, Not Invoiced (GRNI) to clear the temporary liability.
        - **Debits:** VAT Receivable for the actual VAT amount.
        - **Debits/Credits:** The Purchase Price Variance (PPV) account for any difference.
        - **Credits:** Accounts Payable for the final, correct liability to the supplier.
    5.  Updates the invoice status to `Awaiting Payment` and links it to the new journal entry.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from `_helpers.py`.

- `allocate_landed_costs(invoice: SupplierInvoice)`:
  - **Description:** Allocates landed costs (e.g., freight, customs) from a `Draft` supplier invoice to the `costing_unit_price` of the associated inventory receipts.
  - **Logic:** It distributes the total landed cost amount proportionally across all receipt lines based on their value.
  - **Key Feature:** After updating the costs on the `InventoryLog` records, it triggers `recalculate_cost_history_for_product` to ensure the moving average cost is corrected for all subsequent transactions.
  - **Calls:** `recalculate_cost_history_for_product()` from `costing_service.py`.

- `create_purchase_return(user, return_data: dict, items_data: list)`:
  - **Description:** Creates a `PurchaseReturn` header and its associated `PurchaseReturnItem` records.

- `process_inventory_return(user, purchase_return: PurchaseReturn)`:
  - **Description:** Processes the physical inventory side of a supplier return.
  - **Logic:** For each item in the `PurchaseReturn`, it creates a negative `InventoryAdjustment` with the reason code `RETURN_TO_SUPPLIER`. This action, via a signal, creates the journal entry to Debit Accounts Payable and Credit Inventory.
  - **Key Feature:** Updates the `PurchaseReturn` status to `Completed`.

- `create_debit_memo_from_return(user, purchase_return: PurchaseReturn, memo_data: dict)`:
  - **Description:** Creates the final financial document, a `SupplierDebitMemo`, from a processed `PurchaseReturn`. This confirms the financial credit owed by the supplier.
