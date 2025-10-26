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
  - **Description:** (Legacy) Allocates landed costs from a `SupplierInvoice` to associated receipts. This is being replaced by the more robust `allocate_landed_costs_from_invoice`.
  - **Logic:** Distributes landed cost proportionally based on receipt value.
  - **Calls:** `recalculate_cost_history_for_product()` from `costing_service.py`.

- `create_purchase_return(user, return_data: dict, items_data: list)`:
  - **Description:** Creates a `PurchaseReturn` header and its associated `PurchaseReturnItem` records, validating return quantities against original receipts.

- `process_inventory_return(user, purchase_return: PurchaseReturn)`:
  - **Description:** Processes the physical inventory side of a supplier return.
  - **Logic:** For each item in the `PurchaseReturn`, it creates a negative `InventoryAdjustment` with the reason code `RETURN_TO_SUPPLIER`. This action, via a signal, creates the journal entry to Debit a clearing account and Credit Inventory.
  - **Key Feature:** Updates the `PurchaseReturn` status to `Completed`.

- `create_debit_memo_from_return(user, purchase_return: PurchaseReturn, memo_data: dict)`:
  - **Description:** Creates the final financial document, a `SupplierDebitMemo`, from a processed `PurchaseReturn`. This creates the JE to Debit Accounts Payable and Credit the clearing account.

- `create_purchase_order(user, po_data: dict, items_data: list)`:
  - **Description:** Creates a new `PurchaseOrder` and its associated `PurchaseOrderItem` records from validated data.

- `update_purchase_order(user, po: PurchaseOrder, po_data: dict, items_data: list)`:
  - **Description:** Updates an existing `PurchaseOrder` and its items.
  - **Logic:** Prevents updates if any of the PO items have already been received against.

- `update_po_status_after_receipt(inventory_log_id: int, is_final_receipt: bool, old_po_item_id: int)`:
  - **Description:** A utility function to update the status of a `PurchaseOrder` and its items based on receipt activity. It is triggered after an `InventoryLog` is saved or deleted.
  - **Logic:** Calculates total received quantity against ordered quantity to set statuses like `Partially Received` or `Completed`.

- `post_landed_cost_invoice(invoice: LandedCostInvoice)`:
  - **Description:** Posts a third-party `LandedCostInvoice` to the General Ledger. This is the first step in the landed cost workflow.
  - **Accounting Logic:**
    - **Debit:** A "Landed Costs Clearing" account.
    - **Credit:** Accounts Payable (for the landed cost vendor).
  - **Key Feature:** Sets the invoice status to `Awaiting Allocation`.

- `allocate_landed_costs_from_invoice(landed_cost_invoice_ids: list, receipt_log_ids: list, user)`:
  - **Description:** **REDEFINED:** The second and final step in the landed cost workflow. It allocates late costs from `LandedCostInvoice` records to inventory receipts using a non-destructive revaluation model.
  - **Workflow:**
    1. Updates the `costing_unit_price` on the target `InventoryLog` records.
    2. Creates a single, consolidated journal entry that moves value from the "Landed Costs Clearing" account.
    3. **It intelligently splits the debit:** A portion goes to an "Inventory Revaluation" account (for on-hand quantity) and the rest goes to a "Manufacturing Variance" account (for the portion already sold).
    4. Triggers the new, non-destructive `recalculate_cost_history_for_product` to update the product's `moving_average_cost` for future transactions only.
  - **Calls:** `get_inventory_state_at_datetime()`, `recalculate_cost_history_for_product()` from `costing_service.py`, `_check_period_is_open()` from `_helpers.py`.
