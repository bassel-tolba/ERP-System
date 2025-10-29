# `production_returns_service.py` Manifest

This service manages the business logic for returning unused raw materials from the production line back into inventory. This is a critical function for maintaining accurate inventory records and ensuring that the value of Work-in-Progress (WIP) is correctly stated.

## Key Functionalities:

### 1. **Production Return Creation**
   - **`create_production_return`**: This function is responsible for creating a new `ProductionReturn` record.
     - **Validation**: Before creating the return, it performs a critical validation to ensure that the quantity being returned does not exceed the amount that was originally consumed from that specific `InventoryLog` (source). It calculates the `max_returnable` quantity by taking the total amount consumed from the source minus any previous returns from that same source. This prevents fraudulent or erroneous returns.
     - **Record Creation**: It creates the `ProductionReturn` object, linking it to the specific product, the original source log, and optionally the batch it's being returned from.
     - **Financial Impact**: The actual financial transaction is handled by a `post_save` signal on the `ProductionReturn` model. This signal calls the `accounting_service` to create the journal entry that moves value back from the WIP account to the Raw Material Inventory account (a debit to inventory and a credit to WIP). The signal also triggers a cost recalculation via the `costing_service`.

### 2. **Production Return Cancellation**
   - **`cancel_production_return`**: This function provides a controlled and auditable way to reverse a production return that was made in error.
     - **Validation**: It includes a crucial safety check to prevent cancellation if the stock that was returned has already been consumed in a subsequent production batch. This maintains the integrity of the inventory data.
     - **Reversing Journal Entry**: It calls the `accounting_service` (specifically `create_reversing_je_for_correction`) to create a reversing journal entry that nullifies the financial impact of the original return.
     - **Status Update**: It sets the status of the `ProductionReturn` to `CANCELLED`.
     - **Cost Recalculation**: It triggers a cost recalculation for the affected product via the `costing_service` to ensure that the Moving Average Cost is corrected after the cancellation.

This service ensures that the process of returning materials from production is properly validated, recorded, and reflected in the company's financial and inventory records.
