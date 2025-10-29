# `finished_product_service.py` Manifest

This service manages the lifecycle and associated costs of finished goods. It handles the process of receiving products from production, managing their status, calculating their costs, and processing cancellations.

## Key Functionalities:

### 1. **Finished Goods Status Reporting**
   - **`get_finished_goods_status_data`**: Gathers and organizes data for a dashboard view of the entire finished goods pipeline. It provides lists of:
     - Production plans that are currently `IN_PROGRESS` and have outstanding receipts.
     - Finished product receipts that are in `QUARANTINED` status, awaiting quality control release.
     - Finished product receipts that have been `RELEASED` and are available for sale.

### 2. **Status Management**
   - **`release_receipt_from_quarantine`**: Changes a `FinishedProductReceipt`'s status from `QUARANTINED` to `RELEASED`, making it available for dispatch.

### 3. **Cost Calculation**
   - **`get_proportional_cost_for_receipt`**: This is a crucial costing function that calculates the cost of a single finished product batch.
     - **Aggregates Total Cost**: It sums up the costs of all materials consumed in the main production plan (`Batch`) **plus** all materials consumed in any associated `continuation_batches`. This provides the total cost for the entire production run.
     - **Calculates Proportional Cost**: It then divides this total cost by the `number_of_batches_in_plan` to determine the cost that should be allocated to a single `FinishedProductReceipt`. This ensures that each unit produced from the plan is assigned an equal and accurate share of the total production cost.
   - **`get_finished_product_cost_breakdown`**: Provides a detailed breakdown of the costs for a specific receipt, showing the cost contribution from the main plan and each continuation batch separately. This is useful for analysis and reporting.

### 4. **Receipt Creation**
   - **`create_finished_product_receipt`**: This function handles the creation of a new `FinishedProductReceipt`.
     - It performs validation to ensure receipts are only created for `IN_PROGRESS` plans.
     - It uses `get_proportional_cost_for_receipt` to determine the `total_cost` for the new receipt.
     - It creates the main `FinishedProductReceipt` record and its associated `ReceiptSubBatch` records (e.g., pallets).
     - **Financial Impact**: The `post_save` signal on the `FinishedProductReceipt` model is responsible for calling the `accounting_service` to create the journal entry that moves the value from the Work-in-Progress (WIP) account to the Finished Goods Inventory account.
     - It updates the parent `Batch` status to `COMPLETED` if all expected receipts have been processed.

### 5. **Receipt Cancellation**
   - **`cancel_finished_product_receipt`**: Provides a controlled, non-destructive way to cancel a receipt.
     - It validates that the receipt has not already been sold or adjusted.
     - It sets the receipt's status to `CANCELLED`.
     - It reverts the parent `Batch` status from `COMPLETED` back to `IN_PROGRESS` so that the receipt can be re-processed if necessary.
     - It calls the `accounting_service` to create a **reversing journal entry** to nullify the original WIP-to-Finished-Goods transaction.
     - It triggers a cost recalculation for the finished product via the `costing_service` to ensure the Moving Average Cost is corrected.

This service is the critical link between the production module and the inventory and accounting modules, ensuring that the value of finished goods is accurately calculated and recorded.
