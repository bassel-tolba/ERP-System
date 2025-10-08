# File: gipcco_project/inventory/signals.py
- **Purpose:** Uses Django signals to automate accounting and data integrity tasks. It creates/deletes journal entries in response to model changes and prevents transactions in closed financial periods.

- `pre_save_period_check(sender, instance, **kwargs)`: A generic pre-save signal that blocks saving a transaction if its financial period is closed.
  - Looks up the relevant date field for the model being saved.
  - Checks the period status only for new records or if the date has changed.
  - **Calls:** `_check_period_is_open()` from `services/accounting_service.py`.

- `pre_delete_period_check(sender, instance, **kwargs)`: A generic pre-delete signal that blocks deleting a transaction if its financial period is closed.
  - Looks up the relevant date field for the model being deleted.
  - **Calls:** `_check_period_is_open()` from `services/accounting_service.py`.

- `handle_inventory_log_release(sender, instance: InventoryLog, **kwargs)`: Creates a journal entry when an `InventoryLog` status is set to 'RELEASED'.
  - **Calls:** `create_je_for_inventory_receipt()` from `services/accounting_service.py`.

- `handle_inventory_log_deletion(sender, instance: InventoryLog, **kwargs)`: Deletes the associated journal entry when an `InventoryLog` is deleted.

- `handle_batch_save(sender, instance: Batch, created, **kwargs)`: Creates or updates a journal entry for production consumption when a `Batch` is saved.
  - If the batch is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_production_consumption()` from `services/accounting_service.py`.

- `set_consumption_type_for_amortizable(sender, instance: InventoryConsumption, **kwargs)`: On creation, automatically sets the consumption type to 'AMORTIZE' if the product is amortizable.

- `handle_internal_consumption_save(sender, instance: InventoryConsumption, created, **kwargs)`: Creates a journal entry and performs follow-up actions based on consumption type.
  - Creates the primary journal entry for the consumption.
  - If `CAPITALIZE`, it adds the cost to the linked fixed asset.
  - If `AMORTIZE`, it creates a new `PrepaidExpense` record.
  - If `EXPENSE` (default), it creates a direct `ExpenseLog` for overhead tracking.
  - **Calls:** `create_je_for_internal_consumption()`, `_get_product_expense_account()` from `services/accounting_service.py`.

- `handle_internal_consumption_deletion(sender, instance: InventoryConsumption, **kwargs)`: Deletes the associated journal entry when an `InventoryConsumption` record is deleted.

- `handle_fg_receipt_save(sender, instance: FinishedProductReceipt, created, **kwargs)`: Creates or updates a journal entry for a finished goods receipt.
  - If the record is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_finished_goods_receipt()` from `services/accounting_service.py`.

- `handle_fg_receipt_delete(sender, instance: FinishedProductReceipt, **kwargs)`: Deletes the associated journal entry when a `FinishedProductReceipt` is deleted.

- `handle_production_return_save(sender, instance: ProductionReturn, created, **kwargs)`: Creates or updates the journal entry for a `ProductionReturn`.
  - If the record is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_production_return()` from `services/accounting_service.py`.

- `handle_production_return_delete(sender, instance: ProductionReturn, **kwargs)`: Deletes the associated journal entry when a `ProductionReturn` is deleted.

- `handle_dispatch_save(sender, instance: FinishedProductDispatch, created, **kwargs)`: Creates or updates the journal entry for a sales dispatch.
  - If the record is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_sales_dispatch()` from `services/accounting_service.py`.

- `handle_dispatch_delete(sender, instance: FinishedProductDispatch, **kwargs)`: Deletes the associated journal entry when a sales dispatch is deleted.

- `handle_payment_delete(sender, instance: Payment, **kwargs)`: Deletes the associated journal entry when a `Payment` is deleted.

- `handle_payment_save(sender, instance: Payment, created, **kwargs)`: Creates or updates a journal entry for a payment, routing based on its type.
  - If the record is updated, it first deletes the old journal entry.
  - Routes to the correct service based on payment type (inbound vs. outbound).
  - **Calls:** `create_je_for_supplier_payment()`, `create_je_for_customer_payment()` from `services/accounting_service.py`.

- `handle_bank_transfer_save(sender, instance: BankTransfer, created, **kwargs)`: Creates or updates the journal entry for a bank transfer.
  - If the record is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_bank_transfer()` from `services/accounting_service.py`.

- `handle_bank_transfer_delete(sender, instance: BankTransfer, **kwargs)`: Deletes the associated journal entry when a `BankTransfer` is deleted.

- `handle_depreciation_log_save(sender, instance: DepreciationLog, created, **kwargs)`: Creates a journal entry when a new `DepreciationLog` is saved.
  - **Calls:** `create_je_for_depreciation()` from `services/accounting_service.py`.

- `handle_depreciation_log_deletion(sender, instance: DepreciationLog, **kwargs)`: Deletes the associated journal entry when a `DepreciationLog` is deleted.

- `handle_amortization_log_save(sender, instance: AmortizationLog, created, **kwargs)`: Creates a journal entry when a new `AmortizationLog` is saved.
  - **Calls:** `create_je_for_amortization()` from `services/accounting_service.py`.

- `handle_amortization_log_delete(sender, instance: AmortizationLog, **kwargs)`: Deletes the associated journal entry when an `AmortizationLog` is deleted.

- `handle_accrual_log_save(sender, instance: AccrualLog, created, **kwargs)`: Creates a journal entry when a new `AccrualLog` is saved.
  - **Calls:** `create_je_for_accrual()` from `services/accounting_service.py`.

- `handle_accrual_log_delete(sender, instance: AccrualLog, **kwargs)`: Deletes the associated journal entry when an `AccrualLog` is deleted.

- `handle_expense_log_save(sender, instance: ExpenseLog, created, **kwargs)`: Creates a journal entry when a new `ExpenseLog` is created.
  - **Calls:** `create_je_for_expense_log()` from `services/accounting_service.py`.

- `handle_expense_log_delete(sender, instance: ExpenseLog, **kwargs)`: Deletes the associated journal entry when an `ExpenseLog` is deleted.

- `handle_inventory_adjustment_save(sender, instance: InventoryAdjustment, created, **kwargs)`: Creates or updates the journal entry for an inventory adjustment.
  - If the record is updated, it first deletes the old journal entry.
  - **Calls:** `create_je_for_inventory_adjustment()` from `services/accounting_service.py`.

- `handle_inventory_adjustment_delete(sender, instance: InventoryAdjustment, **kwargs)`: Deletes the associated journal entry when an `InventoryAdjustment` is deleted.

- `handle_employee_advance_save(sender, instance: EmployeeAdvance, created, **kwargs)`: Creates a journal entry when a new `EmployeeAdvance` is saved.
  - **Calls:** `create_je_for_employee_advance()` from `services/accounting_service.py`.

- `handle_employee_advance_deletion(sender, instance: EmployeeAdvance, **kwargs)`: Deletes the associated journal entry when an `EmployeeAdvance` is deleted.

- `handle_advance_settlement_save(sender, instance: EmployeeAdvanceSettlement, created, **kwargs)`: Updates the status of the parent `EmployeeAdvance` when a new settlement is created.

- `create_period_close_checklist(sender, instance, created, **kwargs)`: Automatically creates a `PeriodCloseChecklist` when a new `FinancialPeriod` is created.