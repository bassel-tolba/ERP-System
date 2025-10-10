# File: gipcco_project/inventory/services/accounting_service.py
- **Purpose:** Centralizes all logic for creating journal entries in response to various business events like inventory movements, payments, and period-end adjustments.

- `_check_period_is_open(date_to_check)`: Checks if a given date falls within an open financial period, raising a `PermissionError` if not.

- `_get_product_inventory_account(product: Product)`: Retrieves the correct inventory account for a product, prioritizing a product-specific override over the product type default.

- `_get_product_expense_account(product: Product)`: Retrieves the correct COGS/Expense account for a product, prioritizing a product-specific override.

- `_get_product_revenue_account(product: Product)`: Retrieves the correct Sales Revenue account for a product, prioritizing a product-specific override.

- `create_je_for_inventory_adjustment(adjustment: InventoryAdjustment)`: Creates a journal entry for an inventory adjustment, handling both shortages (losses) and overages (gains).
  - Verifies that the financial period is open.
  - Debits a loss account and credits inventory for shortages.
  - Debits inventory and credits a gain account for overages.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from the current file.

- `create_je_for_inventory_receipt(inventory_log: InventoryLog)`: Creates a journal entry for receiving purchased goods.
  - Verifies the log is 'Released' and the financial period is open.
  - Debits Inventory and VAT Receivable; Credits Accounts Payable and Withholding Tax Payable.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from the current file.

- `create_je_for_production_consumption(batch: Batch)`: Creates a journal entry for raw materials consumed in a production batch.
  - Verifies financial period is open and batch has items.
  - Aggregates the total cost of consumed materials.
  - Debits Work-in-Progress (WIP) and credits the respective Raw Material inventory accounts.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from the current file, and `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_je_for_internal_consumption(consumption: InventoryConsumption)`: Creates a journal entry for items consumed internally.
  - Verifies financial period is open.
  - Handles different consumption types with specific debit accounts:
    - `EXPENSE`: Debits an expense account.
    - `CAPITALIZE`: Debits a Fixed Asset's GL account.
    - `AMORTIZE`: Debits the Prepaid Expenses account.
  - Credits the item's inventory account.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()`, `_get_product_expense_account()` from the current file.

- `create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt)`: Creates a journal entry to move value from WIP to Finished Goods upon production completion.
  - Verifies financial period is open.
  - Debits Finished Goods Inventory and credits Work-in-Progress (WIP) Inventory.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_production_return(prod_return: ProductionReturn)`: Creates a journal entry for raw materials returned from production back to inventory.
  - Calculates the value of the returned goods.
  - Debits Raw Material Inventory and credits Work-in-Progress (WIP) Inventory.
  - **Calls:** `_check_period_is_open()`, `_get_product_inventory_account()` from the current file, and `get_inventory_state_at_datetime()` from `costing_service.py`.

- `create_je_for_sales_dispatch(dispatch: FinishedProductDispatch)`: Creates a compound journal entry for a customer sale, recording both COGS and revenue.
  - Creates lines for Cost of Goods Sold (Debit COGS, Credit Finished Goods).
  - Creates lines for Revenue (Debit Accounts Receivable, Credit Revenue/VAT Payable).
  - **Calls:** `_check_period_is_open()`, `_get_product_expense_account()`, `_get_product_revenue_account()` from the current file.

- `create_je_for_supplier_payment(payment: Payment)`: Creates a journal entry for a payment made to a supplier.
  - Debits Accounts Payable and credits the source Bank account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_customer_payment(payment: Payment)`: Creates a journal entry for a payment received from a customer.
  - Debits the receiving Bank account.
  - Credits Accounts Receivable if applying to invoices, or Customer Deposits if it's an on-account payment.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_employee_advance(advance: EmployeeAdvance)`: Creates a journal entry for a cash advance given to an employee.
  - Debits Employee Advances Receivable and credits the source Bank account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_employee_advance_settlement(settlement: EmployeeAdvanceSettlement)`: Creates a journal entry for an employee advance settlement, with logic depending on the settlement's source.
  - It inspects the `source_transaction` generic foreign key.
  - If the source is an `ExpenseLog`, it creates a JE to Debit Accrued Expenses and Credit Employee Advances Receivable.
  - If the source is not an expense (i.e., a direct cash repayment), it creates a JE to Debit Cash and Credit Employee Advances Receivable.

- `create_je_for_overhead_allocation(run: OverheadAllocationRun)`: Creates a journal entry to move collected overhead costs into WIP.
  - Aggregates expenses from all cost pools in the run.
  - Debits Work-in-Progress (WIP) and credits the various source expense accounts.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_overhead_application(run: OverheadAllocationRun, total_applied_cost: Decimal)`: Creates a journal entry to apply overhead costs from WIP to Finished Goods.
  - Debits Finished Goods Inventory and credits Work-in-Progress (WIP) Inventory.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_bank_transfer(transfer: BankTransfer)`: Creates a journal entry for a transfer of funds between two internal bank accounts.
  - Debits the destination bank account and credits the source bank account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_depreciation(depreciation_log: DepreciationLog)`: Creates a journal entry for a single asset's monthly depreciation.
  - Debits the asset's Depreciation Expense account and credits its Accumulated Depreciation account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_amortization(amortization_log: AmortizationLog)`: Creates a journal entry for the monthly amortization of a prepaid expense.
  - Debits the target expense account and credits the master Prepaid Expenses control account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_accrual(accrual_log: AccrualLog)`: Creates a journal entry for a monthly expense accrual.
  - Debits the target expense account and credits the associated accrued liability account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_expense_log(expense_log: ExpenseLog)`: Creates a journal entry for a direct expense.
  - Debits the expense account linked to the cost pool.
  - Credits the master Accrued Expenses liability account.
  - **Calls:** `_check_period_is_open()` from the current file.

- `create_je_for_opening_balance(ob_entry: 'OpeningBalanceEntry')`: Creates a single, multi-line journal entry from an Opening Balance Entry record.
  - Iterates through all lines and sub-ledger details to build the JE.
  - Aggregates sub-ledger details for products to create consolidated lines.
  - Validates that total debits equal total credits before posting.
  - **Calls:** `_check_period_is_open()` from the current file.

- `correct_approved_expense(request_id: int, user, justification: str)`: Reverses the financial transaction associated with an approved expense request.
  - Finds the original transaction (ExpenseLog or InventoryConsumption).
  - Creates a reversing journal entry and a `TransactionCorrection` audit record.
  - **Calls:** `create_reversing_je_for_correction()` from the current file.

- `create_reversing_je_for_correction(original_object, justification: str, user, correction_date: Optional[timezone.datetime])`: Creates a journal entry that is an exact reversal of a previous transaction's entry.
  - Finds the original JE linked to the source object.
  - Creates a new JE where debits become credits and credits become debits.
  - Creates a `TransactionCorrection` audit record to link the original and reversing JEs.
  - **Calls:** `_check_period_is_open()` from the current file.

- `run_monthly_depreciation(period: FinancialPeriod)`: A service function that calculates and posts depreciation for all eligible assets for a given financial period.
  - Identifies all assets needing depreciation that have not yet been processed for the period.
  - Calculates the correct monthly or final depreciation amount.
  - Creates a `DepreciationLog` for each asset, which in turn triggers its own journal entry creation.
  - **Calls:** `_check_period_is_open()` from the current file.