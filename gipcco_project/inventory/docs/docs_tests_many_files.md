# File: test_base.py
- **Purpose:** Establishes a foundational Django test case with a comprehensive set of pre-configured data, including a chart of accounts, fiscal periods, settings, and various operational objects, to be used by other test suites.

- `create_chart_of_accounts()`: Creates and returns a dictionary of a structured chart of `Account` model instances for testing.
  - Contains nested helper functions `create_account` and `set_control` to streamline object creation and configuration.

- `AccountingServiceBaseTestCase.setUpTestData(cls)`: Sets up a rich, non-modified data environment once per test class run for efficiency.
  - Creates fiscal years and financial periods.
  - Configures general and product-specific accounting settings.
  - Creates base operational objects like suppliers, customers, products, and bank accounts.
  - Creates overhead allocation objects like cost pools and drivers.
  - Creates common finished good receipts and fixed assets for use in various tests.
  - **Calls:** `create_chart_of_accounts()`, `get_or_create_batch_for_template()`, `get_or_create_receipt()` from the current file.

- `AccountingServiceBaseTestCase.get_product_type_setting(cls, product_type)`: A helper method to retrieve the accounting settings for a given product type.

- `AccountingServiceBaseTestCase.get_or_create_batch_for_template(cls, template, shop_order_number, batch_number)`: A helper method to create or retrieve a `Batch` object, preventing duplicates in test setups.

- `AccountingServiceBaseTestCase.get_or_create_receipt(cls, batch, individual_batch_number, quantity, cost, date_str)`: A helper method to create or retrieve a `FinishedProductReceipt` object, preventing duplicates in test setups.
# File: tests_adjustments.py
- **Purpose:** Contains test suites for inventory adjustment functionalities, covering both the automated journal entry creation from signals and the business logic within the adjustment service.

- `TestAdjustmentAccounting.setUp(self)`: Prepares the environment for each test by creating a common `InventoryCount` and a source `InventoryLog`.

- `TestAdjustmentAccounting.test_create_je_for_inventory_shortage_loss(self)`: Verifies that creating a negative `InventoryAdjustment` (a loss) triggers a signal that correctly generates a journal entry debiting the loss account and crediting inventory.

- `TestAdjustmentAccounting.test_create_je_for_inventory_overage_gain(self)`: Verifies that creating a positive `InventoryAdjustment` (a gain) triggers a signal that correctly generates a journal entry debiting inventory and crediting the gain account.

- `TestAdjustmentService.setUp(self)`: Prepares initial stock levels by creating several `InventoryLog` records for subsequent tests.

- `TestAdjustmentService.test_start_inventory_count_snapshots_correct_quantity(self)`: Verifies that the service correctly calculates and saves the current system quantity of a product when a new inventory count is initiated.
  - **Calls:** `adjustment_service.start_inventory_count()` from `adjustment_service.py`.

- `TestAdjustmentService.test_create_manual_adjustments_from_form_success(self)`: Verifies that the service can successfully process a list of manual allocations to create multiple `InventoryAdjustment` records.
  - **Calls:** `adjustment_service.start_inventory_count()`, `adjustment_service.create_adjustments_from_form()` from `adjustment_service.py`.

- `TestAdjustmentService.test_auto_distribute_finished_good_shortage_fifo(self)`: Verifies that the service correctly distributes a finished good shortage proportionally across available stock receipts.
  - **Calls:** `adjustment_service.start_inventory_count()`, `adjustment_service.auto_distribute_finished_good_shortage()` from `adjustment_service.py`.

- `TestAdjustmentService.test_finalize_inventory_count_triggers_recalculation(self)`: Verifies that finalizing an inventory count correctly triggers the cost recalculation logic for the affected product, resulting in an updated moving average cost.
  - **Calls:** `adjustment_service.start_inventory_count()`, `adjustment_service.create_adjustments_from_form()`, `adjustment_service.finalize_inventory_count()` from `adjustment_service.py`.

- `TestAdjustmentService.test_auto_distribute_shortage_raises_error_if_insufficient_stock(self)`: Verifies that the service raises a `ValidationError` if an attempt is made to distribute a shortage that exceeds the available stock.
  - **Calls:** `adjustment_service.start_inventory_count()`, `adjustment_service.auto_distribute_finished_good_shortage()` from `adjustment_service.py`.
# File: tests_banking.py
- **Purpose:** Contains test suites for banking-related transactions, focusing on journal entry creation for bank transfers and the functionality of the bank reconciliation module.

- `TestBankingAccounting.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestBankingAccounting.test_create_je_for_bank_transfer_success(self)`: Verifies that creating a `BankTransfer` model instance triggers a signal that correctly generates a journal entry debiting the destination bank account and crediting the source bank account.

- `TestBankReconciliation.setUp(self)`: Creates a set of incoming payments, outgoing payments, and bank transfers to serve as transactions for reconciliation tests.

- `TestBankReconciliation.test_bank_reconciliation_creation_and_unmatch(self)`: Verifies that a `BankReconciliation` can be created, linked to transactions, and that its `unmatch_all_transactions` method correctly clears the reconciliation links.

- `TestBankReconciliation.test_bank_statement_line_matching(self)`: Verifies that a `BankStatementLine` can be successfully linked to a corresponding `Payment` object as part of the reconciliation process.
# File: tests_costing.py
- **Purpose:** Provides test suites for the inventory costing service, validating its ability to accurately calculate historical inventory states and recalculate costs after corrections.

- `TestCostingService.setUp(self)`: Ensures a clean slate for each test by deleting all `JournalEntry` objects.

- `TestCostingService.test_get_inventory_state_at_datetime_complex_scenario(self)`: Verifies the accuracy of inventory quantity and value calculations by creating a complex chronological series of receipts, consumptions, adjustments, and returns, then asserting the state at each step.
  - **Calls:** `costing_service.get_inventory_state_at_datetime()` from `costing_service.py`.

- `TestCostingService.test_recalculate_cost_history_for_product_after_correction(self)`: Verifies that after correcting a historical inventory receipt's price, the service correctly updates the cost of all subsequent transactions and the product's final moving average cost.
  - **Calls:** `costing_service.recalculate_cost_history_for_product()` from `costing_service.py`.

- `TestCostingWithOpeningBalance.setUp(self)`: Ensures a clean slate for each test by deleting all `JournalEntry` objects.

- `TestCostingWithOpeningBalance.test_operations_with_raw_material_opening_balance(self)`: Verifies that inventory consumption is costed correctly when the initial stock is established via an opening balance record, followed by a subsequent purchase.
  - **Calls:** `costing_service.recalculate_cost_history_for_product()`, `costing_service.get_inventory_state_at_datetime()` from `costing_service.py`.

- `TestCostingWithOpeningBalance.test_operations_with_finished_good_opening_balance(self)`: Verifies that selling a finished good from an opening balance correctly calculates the cost of goods sold and generates the appropriate journal entry.
  - **Calls:** `costing_service.get_inventory_state_at_datetime()` from `costing_service.py`.
# File: tests.py
- **Purpose:** Serves as a primary test runner by importing other test modules and contains tests for Django views, API endpoints, model validation, and database-level protection rules.

- `TestViews.setUp(self)`: Initializes a test client and logs in a pre-configured user before each view test.

- `TestViews.test_dashboard_index_view_get(self)`: Verifies that the main dashboard page loads successfully with a 200 status code.

- `TestViews.test_create_company_view_post(self)`: Verifies that submitting the company creation form successfully creates a new `Company` object and redirects.

- `TestViews.test_create_product_view_post(self)`: Verifies that submitting the product creation form successfully creates a new `Product` object and redirects.

- `TestViews.test_release_from_quarantine_view_post(self)`: Verifies that a POST request to the release view correctly updates an `InventoryLog`'s status from 'QUARANTINED' to 'RELEASED'.

- `TestViews.test_api_get_sellable_stock(self)`: Verifies that the sellable stock API endpoint returns a correct JSON list of available finished goods.

- `TestViews.test_create_batch_view_post(self)`: Verifies that submitting the batch creation form successfully creates a new `Batch` and its associated `BatchItem` records.

- `TestViews.test_create_purchase_order_view_post(self)`: Verifies that submitting the purchase order form successfully creates a `PurchaseOrder` and its line items.

- `TestViews.test_create_sales_order_view_post(self)`: Verifies that submitting the sales order form successfully creates a `SalesOrder` and its line items.

- `TestViews.test_api_get_po_items(self)`: Verifies that the API for retrieving purchase order items returns the correct data, including the calculated remaining quantity.

- `TestValidationAndProtection.test_consumption_of_non_mro_raises_error(self)`: Tests that the `InventoryConsumption` model's `clean()` method raises a `ValidationError` if an attempt is made to expense a product that is not of the 'MRO' type.

- `TestValidationAndProtection.test_bank_transfer_to_same_account_raises_error(self)`: Tests that the `BankTransfer` model's `clean()` method raises a `ValidationError` if the source and destination accounts are the same.

- `TestValidationAndProtection.test_deleting_supplier_with_po_raises_protected_error(self)`: Verifies that the database schema prevents the deletion of a `Company` if it is linked to a `PurchaseOrder`, raising a `ProtectedError`.
# File: tests_accounting.py
- **Purpose:** Contains a comprehensive suite of tests for core accounting logic, verifying the automatic creation of journal entries from various business transactions via model signals and service functions.

- `TestAccountingService.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestAccountingService.test_create_je_for_inventory_receipt_success(self)`: Verifies that creating a 'RELEASED' `InventoryLog` triggers a signal to generate a correct, balanced journal entry for the receipt of goods, including VAT and withholding tax.

- `TestAccountingService.test_create_je_for_inventory_receipt_not_released(self)`: Verifies that no journal entry is created when an `InventoryLog` is created with a status other than 'RELEASED'.
  - **Calls:** `accounting_service.create_je_for_inventory_receipt()` from `accounting_service.py`.

- `TestAccountingService.test_create_je_for_inventory_receipt_duplicate_prevention(self)`: Ensures that the system prevents the creation of a duplicate journal entry for an `InventoryLog` that has already been processed.
  - **Calls:** `accounting_service.create_je_for_inventory_receipt()` from `accounting_service.py`.

- `TestAccountingService.test_create_je_for_inventory_receipt_period_closed(self)`: Verifies that attempting to create an `InventoryLog` with a date in a closed financial period raises a `PermissionError`.

- `TestAccountingService.test_create_je_for_production_consumption_success(self)`: Verifies that saving a `Batch` with consumed items triggers a signal to generate a journal entry that moves value from raw material inventory to WIP inventory.

- `TestAccountingService.test_create_je_for_finished_goods_receipt_success(self)`: Verifies that creating a `FinishedProductReceipt` triggers a signal to generate a journal entry that moves value from WIP inventory to finished goods inventory.

- `TestAccountingService.test_create_je_for_sales_dispatch_success(self)`: Verifies that creating a `FinishedProductDispatch` triggers a signal to generate a compound journal entry correctly recording both the revenue and the cost of goods sold.

- `TestPaymentAccounting.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestPaymentAccounting.test_create_je_for_supplier_payment_success(self)`: Verifies that creating an outgoing `Payment` to a supplier generates a journal entry that debits Accounts Payable and credits the bank account.

- `TestPaymentAccounting.test_create_je_for_customer_payment_success(self)`: Verifies that creating an incoming `Payment` from a customer generates a journal entry that debits the bank and credits the Customer Deposits liability account.

- `TestMiscAccountingTransactions.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestMiscAccountingTransactions.test_create_je_for_internal_consumption_success(self)`: Verifies that an `InventoryConsumption` of an MRO item generates a journal entry that debits an expense account and credits MRO inventory.

- `TestMiscAccountingTransactions.test_create_je_for_amortizable_consumption_success(self)`: Verifies that consuming an amortizable MRO item creates a `PrepaidExpense` asset and a journal entry debiting the Prepaid Expenses account and crediting MRO inventory.
  - **Calls:** `accounting_service._get_product_inventory_account()` from `accounting_service.py`.

- `TestMiscAccountingTransactions.test_create_je_for_production_return_success(self)`: Verifies that a `ProductionReturn` generates a journal entry that correctly moves value back from WIP inventory to raw material inventory.

- `TestOverheadAllocation.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestOverheadAllocation.test_overhead_allocation_and_application_success(self)`: Tests the end-to-end overhead process, verifying the rate calculation, the allocation JE (Expense to WIP), the application of cost to receipts, and the application JE (WIP to FG).
  - **Calls:** `overhead_service.execute_overhead_allocation_run()`, `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`, and `accounting_service.create_je_for_overhead_allocation()`, `accounting_service.create_je_for_overhead_application()` from `accounting_service.py`.

- `TestOverheadAllocation.test_overhead_allocation_with_zero_driver_units(self)`: Verifies that the allocation run completes with a calculated rate of zero if there are no production driver units in the period.
  - **Calls:** `overhead_service.execute_overhead_allocation_run()` from `overhead_service.py`.

- `TestOverheadAllocation.test_apply_overhead_with_no_receipts_in_period(self)`: Verifies that the overhead application step completes gracefully without creating a journal entry if there are no finished goods receipts in the period.
  - **Calls:** `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`, and `accounting_service.create_je_for_overhead_application()` from `accounting_service.py`.

- `TestOverheadAllocation.test_overhead_proportional_application_and_bulk_update(self)`: Verifies that overhead costs are applied proportionally to multiple finished goods receipts based on their consumption of the allocation driver.
  - **Calls:** `overhead_service.execute_overhead_allocation_run()`, `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`.

- `TestOverheadAllocation.test_overhead_application_by_labor_hours(self)`: Verifies the full overhead allocation and application process using 'Labor Hours' as the driver.
  - **Calls:** `overhead_service.execute_overhead_allocation_run()`, `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`, and `accounting_service.create_je_for_overhead_allocation()`, `accounting_service.create_je_for_overhead_application()` from `accounting_service.py`.

- `TestOverheadAllocation.test_overhead_application_by_bottle_units(self)`: Verifies the full overhead allocation and application process using 'Bottle Units' as the driver.
  - **Calls:** `overhead_service.execute_overhead_allocation_run()`, `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`, and `accounting_service.create_je_for_overhead_allocation()`, `accounting_service.create_je_for_overhead_application()` from `accounting_service.py`.

- `TestOverheadAllocation.test_overhead_application_by_liters_volume(self)`: Verifies the full overhead allocation and application process using 'Liters Volume' as the driver.
  - **Calls:** `overhead_service.execute_overhead_allocation_run()`, `overhead_service.apply_overhead_to_finished_goods()` from `overhead_service.py`, and `accounting_service.create_je_for_overhead_allocation()`, `accounting_service.create_je_for_overhead_application()` from `accounting_service.py`.

- `TestTransactionCorrection.setUp(self)`: Ensures test isolation by deleting all `JournalEntry` objects before each test run.

- `TestTransactionCorrection.setUpTestData(cls)`: Creates an additional financial period to post corrections into.

- `TestTransactionCorrection.test_reversing_sales_dispatch_in_closed_period(self)`: Verifies that correcting a transaction from a closed period correctly creates a reversing journal entry in the next open period.
  - **Calls:** `accounting_service.create_reversing_je_for_correction()` from `accounting_service.py`.

- `TestOpeningBalanceSystem.setUp(self)`: Ensures test isolation by clearing all opening balance and journal entry models before each test.

- `TestOpeningBalanceSystem.setUpTestData(cls)`: Creates a specific financial period for the migration date to use in tests.

- `TestOpeningBalanceSystem.test_create_opening_balance_entry_structure(self)`: Verifies that the core `OpeningBalanceEntry` and `OpeningBalanceEntryLine` models can be created and linked correctly.

- `TestOpeningBalanceSystem.test_post_opening_balance_je_with_sub_ledgers_comprehensive(self)`: Tests the end-to-end opening balance workflow, ensuring the service creates a balanced master journal entry with correct sub-ledger links for various asset and liability types.
  - **Calls:** `accounting_service.create_je_for_opening_balance()` from `accounting_service.py`.

- `TestOpeningBalanceSystem.test_create_opening_balance_with_sub_ledger_details(self)`: Verifies that `OpeningBalanceSubLedgerDetail` records can be correctly created and linked to a parent `OpeningBalanceEntryLine`.
# File: tests_adjusting_entries.py
- **Purpose:** Contains tests for the adjusting entries system, focusing on the lifecycle of prepaid expenses (amortization) and accrued expenses.

- `TestAdjustingEntries.setUp(self)`: Prepares the test environment by creating specific amortizable and non-amortizable MRO products for use in the tests.

- `TestAdjustingEntries.test_prepaid_asset_flow_from_amortizable_consumption(self)`: Verifies that consuming an amortizable product correctly triggers the creation of a `PrepaidExpense` asset and generates the initial journal entry to move its cost from inventory to the prepaid asset account.
  - **Calls:** `get_product_type_setting()` from the current file's base class.

- `TestAdjustingEntries.test_direct_expense_flow_from_consumable_part(self)`: Verifies that consuming a non-amortizable MRO part correctly creates an `ExpenseLog` and generates a journal entry that directly expenses the cost from inventory.
  - **Calls:** `get_product_type_setting()` from the current file's base class.

- `TestAdjustingEntries.test_amortization_prorating_and_cost_splitting(self)`: Tests the monthly amortization service on a prepaid asset that starts mid-month and has its expense split between two cost pools, verifying correct proration and cost distribution.
  - **Calls:** `adjusting_entries_service.run_monthly_amortization()` from `adjusting_entries_service.py`.

- `TestAdjustingEntries.test_full_accrual_and_true_up_lifecycle(self)`: Tests the end-to-end accrual process, verifying the creation of the initial estimated expense JE, and the subsequent creation of a "true-up" JE when the actual invoice is received and settled.
  - **Calls:** `adjusting_entries_service.run_monthly_accruals()`, `adjusting_entries_service.settle_accrual_with_invoice()` from `adjusting_entries_service.py`.

- `TestAdjustingEntries.create_dummy_payment(self)`: A helper method to create a `Payment` object for use as a source object in prepaid expense tests.

# File: tests_hr.py
- **Purpose:** Contains a test suite for employee financial transactions, specifically focusing on the creation and settlement of employee cash advances.

- `setUp(self)`: Prepares the test environment by deleting existing journal entries and creating an `Employee`, `CostPool`, `Payment`, and `EmployeeAdvance`.

- `test_create_je_for_employee_advance_success(self)`: Verifies that creating an `EmployeeAdvance` object correctly triggers the creation of a balanced journal entry that debits the employee advances receivable account and credits the bank's GL account.

- `test_employee_advance_settlement_and_status_change(self)`: Tests the lifecycle of an advance by settling it in two parts, verifying that the `total_settled`, `unsettled_amount`, and `status` fields of the advance are correctly updated after each settlement, as is the employee's `outstanding_advance_balance`.

# File: tests_period_closing.py
- **Purpose:** Provides tests for the period closing cockpit view, its associated API for checking closing readiness, and the actions to close a financial period.

- `setUp(self)`: Configures the test environment by assigning necessary permissions to the test user, logging in a test client, and ensuring a `PeriodCloseChecklist` exists for the default financial period.

- `test_cockpit_view_loads_correctly(self)`: Verifies that the period closing cockpit view returns a 200 OK status for an open financial period.

- `test_cockpit_view_redirects_for_closed_period(self)`: Ensures that attempting to access the closing cockpit for an already closed period results in a redirect.

- `test_api_checklist_status_incomplete(self)`: Tests the checklist status API, confirming it correctly reports an incomplete status when preconditions, such as having no draft manual journal entries, are not met.

- `test_api_checklist_status_complete(self)`: Tests the checklist status API, confirming it correctly reports a complete status when all tasks (bank reconciliations, no draft entries, etc.) are finished.
  - **Calls:** `update_checklist_for_period()` from `services/period_closing_service.py`.

- `test_close_period_action_fails_if_checklist_incomplete(self)`: Verifies that posting to the close period action fails to change the period's status if the closing checklist is incomplete.

- `test_close_period_action_succeeds_if_checklist_complete(self)`: Verifies that the period closing action succeeds when all checklist conditions are met.
  - Sets up all necessary data to make the checklist complete.
  - Runs automated period-end tasks and updates the checklist.
  - Asserts that the period's status is successfully changed to 'Closed' after the action.
  - **Calls:** `run_all_period_end_tasks()` and `update_checklist_for_period()` from `services/period_closing_service.py`.

# File: tests_sales.py
- **Purpose:** Contains test suites for the sales service (order-to-cash workflow) and the sales return service (credit memo workflow).

- `setUp(self)`: Prepares a common test scenario for the sales process, including a `SalesOrder`, `SalesOrderItem`, `FinishedProductDispatch`, two `CustomerInvoice` records, and a `Payment`.

- `test_create_sales_order_success(self)`: Verifies the successful creation of a `SalesOrder` with multiple items.
  - **Calls:** `create_sales_order()` from `services/sales_service.py`.

- `test_create_sales_order_fail_invalid_customer(self)`: Ensures that `create_sales_order` raises a `ValidationError` if a non-existent customer ID is provided.
  - **Calls:** `create_sales_order()` from `services/sales_service.py`.

- `test_create_sales_order_fail_invalid_product(self)`: Ensures that `create_sales_order` raises a `ValidationError` if a non-existent product ID is provided in the items list.
  - **Calls:** `create_sales_order()` from `services/sales_service.py`.

- `test_dispatch_from_sales_order_success(self)`: Verifies the successful creation of a `FinishedProductDispatch` from a sales order.
  - **Calls:** `dispatch_from_sales_order()` from `services/sales_service.py`.

- `test_dispatch_fail_invalid_so(self)`: Ensures `dispatch_from_sales_order` raises a `ValidationError` for a non-existent sales order ID.
  - **Calls:** `dispatch_from_sales_order()` from `services/sales_service.py`.

- `test_dispatch_fail_invalid_so_item(self)`: Ensures `dispatch_from_sales_order` raises a `ValidationError` if an item ID does not belong to the specified sales order.
  - **Calls:** `dispatch_from_sales_order()` from `services/sales_service.py`.

- `test_create_invoice_from_dispatches_success(self)`: Verifies the successful creation of a `CustomerInvoice` from one or more dispatch records.
  - **Calls:** `create_invoice_from_dispatches()` from `services/sales_service.py`.

- `test_create_invoice_fail_dispatch_invoiced(self)`: Ensures `create_invoice_from_dispatches` raises a `ValidationError` if any of the provided dispatches have already been invoiced.
  - **Calls:** `create_invoice_from_dispatches()` from `services/sales_service.py`.

- `test_create_invoice_fail_wrong_customer(self)`: Ensures `create_invoice_from_dispatches` raises a `ValidationError` if the dispatches belong to a different customer than the one specified.
  - **Calls:** `create_invoice_from_dispatches()` from `services/sales_service.py`.

- `test_apply_payment_full_single_invoice(self)`: Verifies that applying a payment fully covers an invoice, updating its status to 'Paid'.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_apply_payment_partial_single_invoice(self)`: Verifies that a partial payment application correctly updates the invoice's paid amount, balance, and status.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_apply_payment_multiple_invoices(self)`: Verifies that a single payment can be successfully applied across multiple invoices.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_fail_overapply_payment_total(self)`: Ensures `apply_payment_to_invoices` raises a `ValidationError` if the total applied amount exceeds the payment's available amount.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_fail_overapply_single_invoice(self)`: Ensures `apply_payment_to_invoices` raises a `ValidationError` if the amount applied to an invoice exceeds its balance due.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_fail_with_invalid_invoice_id(self)`: Ensures `apply_payment_to_invoices` raises a `ValidationError` if a non-existent invoice ID is provided.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_fail_with_wrong_payment_type(self)`: Ensures `apply_payment_to_invoices` raises a `ValidationError` if the payment is an outgoing payment instead of an incoming one.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `test_transactionality_on_failure(self)`: Verifies that if any part of the payment application fails, the entire transaction is rolled back, leaving no changes in the database.
  - **Calls:** `apply_payment_to_invoices()` from `services/sales_service.py`.

- `setUp(self)`: Prepares a test scenario for sales returns, including a dispatched item that can be returned.

- `test_process_return_item_return_to_stock(self)`: Tests the processing of a returned item that is returned to inventory, verifying the creation of a COGS-reversing journal entry.
  - **Calls:** `process_return_item()` from `services/sales_return_service.py`.

- `test_process_return_item_scrap(self)`: Tests the processing of a returned item that is scrapped, verifying the creation of both a COGS-reversing JE and an inventory adjustment JE to write off the value.
  - **Calls:** `process_return_item()` from `services/sales_return_service.py`.

- `test_create_and_apply_credit_memo(self)`: Tests the application of a customer credit memo to an outstanding invoice, verifying the creation of a journal entry that debits sales returns and credits accounts receivable.
  - **Calls:** `apply_customer_credit()` from `services/ar_service.py`.

# File: tests_sub_ledger.py
- **Purpose:** Provides tests to ensure the integrity of the sub-ledger system by enforcing rules for control accounts within the General Ledger.

- `setUp(self)`: Configures the test environment by designating the Accounts Receivable account as a control account linked to the `Customer` model.

- `test_je_line_to_control_account_without_sub_ledger_fails(self)`: Verifies that model validation prevents saving a `JournalEntryLine` to a control account if it lacks a required sub-ledger object link.

- `test_je_line_to_control_account_with_wrong_sub_ledger_type_fails(self)`: Verifies that model validation fails if a `JournalEntryLine` for a control account is linked to a sub-ledger object of an incorrect type.

- `test_je_line_to_control_account_with_correct_sub_ledger_succeeds(self)`: Confirms that a `JournalEntryLine` can be successfully saved to a control account when provided with a sub-ledger object of the correct type.

- `test_je_line_to_non_control_account_with_sub_ledger_is_allowed(self)`: Verifies that it is permissible to link a sub-ledger object to a `JournalEntryLine` for a non-control account, typically for enhanced traceability.

- `test_account_clean_method_enforces_sub_ledger_model(self)`: Tests the validation on the `Account` model itself, ensuring that an account marked as a control account must have a `sub_ledger_model` defined, and vice-versa.

# File: tests_expense_workflow.py
- **Purpose:** Contains comprehensive tests for the expense management workflow, covering requests, approvals, corrections, accruals, and various settlement processes.

- `setUp(self)`: Prepares a detailed test environment with an employee, fixed asset, MRO and amortizable products with inventory, and a bank account.

- `test_create_and_cancel_request(self)`: Verifies that a direct expense request can be created and subsequently cancelled without generating any financial records.
  - **Calls:** `request_direct_expense()`, `cancel_pending_request()` from `services/expense_service.py`.

- `test_create_and_reject_request(self)`: Confirms that an inventory expense request can be rejected by the approval service, leaving no financial impact.
  - **Calls:** `request_inventory_expense()` from `services/expense_service.py`, `reject_request()` from `services/approval_service.py`.

- `test_reject_capitalization_request(self)`: Ensures a capitalization request can be rejected without affecting the target fixed asset's cost or creating financial records.
  - **Calls:** `request_inventory_capitalization()` from `services/expense_service.py`, `reject_request()` from `services/approval_service.py`.

- `test_approve_inventory_prepaid_request_creates_all_objects(self)`: Asserts that approving a prepaid inventory request correctly creates an `InventoryConsumption`, a `PrepaidExpense` object, and the corresponding journal entry.
  - **Calls:** `request_inventory_prepaid()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`, `_get_product_inventory_account()` from `services/accounting_service.py`.

- `test_approve_capitalization_request_updates_asset_cost(self)`: Verifies that approving a capitalization request correctly increases the purchase cost of the associated fixed asset.
  - **Calls:** `request_inventory_capitalization()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`.

- `test_approve_direct_expense_request_creates_expense_log(self)`: Confirms that approving a direct expense request successfully generates the corresponding `ExpenseLog` record.
  - **Calls:** `request_direct_expense()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`.

- `test_cannot_approve_non_pending_request(self)`: Ensures that the approval service raises a `PermissionDenied` error when attempting to approve a request that is not in a 'Pending' state.
  - **Calls:** `request_direct_expense()` from `services/expense_service.py`, `approve_request()`, `reject_request()` from `services/approval_service.py`.

- `test_correct_approved_expense_creates_reversing_je(self)`: Tests that correcting a previously approved request successfully creates a new journal entry that perfectly reverses the original financial transaction.
  - **Calls:** `request_inventory_expense()`, `correct_approved_request()` from `services/expense_service.py`, and `approve_request()` from `services/approval_service.py`.

- `test_approve_direct_expense_for_accrual(self)`: Verifies that approving a direct expense set for later payment correctly creates a journal entry debiting the expense account and crediting the accrued expenses liability account.
  - **Calls:** `request_direct_expense()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`.

- `test_approve_direct_expense_for_direct_payment(self)`: Verifies that approving a direct expense paid from a bank account creates a journal entry debiting the expense account and crediting the bank's GL account.
  - **Calls:** `request_direct_expense()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`.

- `setUp(self)`: Prepares the test environment by creating an accrued expense, a log for the current period, and a supplier invoice for the subsequent period.

- `test_settle_accrual_invoice_greater_than_accrual(self)`: Tests settling an accrual where the actual invoice amount is greater than the estimate, ensuring the variance is expensed in the current period.
  - **Calls:** `settle_accrual()` from `services/expense_service.py`.

- `test_settle_accrual_invoice_less_than_accrual(self)`: Tests settling an accrual where the invoice is less than the estimate, ensuring the variance is credited to the expense account.
  - **Calls:** `settle_accrual()` from `services/expense_service.py`.

- `test_settle_accrual_invoice_equals_accrual(self)`: Tests settling an accrual where the invoice exactly matches the estimate, resulting in a zero net effect on the expense account.
  - **Calls:** `settle_accrual()` from `services/expense_service.py`.

- `test_cannot_settle_already_settled_accrual(self)`: Ensures that an `AccrualLog` that has already been settled cannot be settled a second time.
  - **Calls:** `settle_accrual()` from `services/expense_service.py`.

- `test_cannot_settle_in_closed_period(self)`: Verifies that settling an accrual is blocked if the corresponding invoice date falls within a closed financial period.
  - **Calls:** `settle_accrual()` from `services/expense_service.py`.

- `setUp(self)`: Prepares the test environment with an employee advance and several unsettled, approved expense logs.

- `_create_approved_expense_log(self, supplier, amount, expense_date, description)`: A helper method to create an approved expense log for use in settlement tests.
  - **Calls:** `request_direct_expense()` from `services/expense_service.py`, `approve_request()` from `services/approval_service.py`.

- `test_create_invoice_from_expense_logs(self)`: Verifies that a single supplier invoice can be created from multiple unsettled expense logs, correctly summing their amounts and updating their statuses.
  - **Calls:** `create_invoice_from_expense_logs()` from `services/expense_service.py`.

- `test_create_invoice_validation_checks(self)`: Tests various failure scenarios for invoice creation, such as using already settled logs or logs belonging to a different supplier.
  - **Calls:** `create_invoice_from_expense_logs()` from `services/expense_service.py`.

- `test_settle_employee_advance_with_expense(self)`: Verifies that an employee advance can be settled using an approved expense log, correctly updating the advance's balance and creating the appropriate journal entry.
  - **Calls:** `settle_employee_advance_with_expense()` from `services/expense_service.py`.

- `test_settle_advance_validation_checks(self)`: Tests failure scenarios for advance settlement, such as using an already settled expense or an expense amount that exceeds the advance balance.
  - **Calls:** `settle_employee_advance_with_expense()` from `services/expense_service.py`.

# File: tests_financials.py
- **Purpose:** Contains test suites for Django views related to core financial operations, including Accounts Payable, Accounts Receivable, Banking, and Fiscal Period Management.

- `setUp(self)`: Prepares the test environment by granting necessary financial permissions to a test user and logging in a test client.

- `test_supplier_invoices_list_view(self)`: Verifies that the supplier invoices list view loads correctly and that its filtering functionality works as expected.

- `test_create_supplier_invoice_view_post_success(self)`: Tests the successful creation of a supplier invoice via a POST request to the corresponding view.

- `test_apply_payment_to_invoice_view_post_success(self)`: Tests that applying a payment to a supplier invoice via a POST request correctly updates the invoice's status and creates the necessary payment records.

- `test_api_get_uninvoiced_receipts(self)`: Verifies that the API endpoint for fetching uninvoiced receipts for a specific supplier returns the correct data.

- `setUp(self)`: Prepares the test environment by granting permissions to a test user and logging in a test client for customer-related tests.

- `test_customer_invoices_list_view(self)`: Verifies that the customer invoices list view loads correctly.

- `test_create_customer_invoice_view_post_success(self)`: Tests the successful creation of a customer invoice from a sales order dispatch via a POST request.

- `test_apply_payment_to_customer_invoice(self)`: Verifies the backend logic for applying a received payment to a customer invoice, ensuring the invoice status and payment application records are updated correctly.

- `test_bank_accounts_dashboard_view_get_and_post_transfer(self)`: Tests that the banking dashboard view loads (GET) and that a bank transfer can be successfully created via a POST request.

- `test_fiscal_year_list_view_and_create_year(self)`: Verifies that the fiscal year list view loads (GET) and that a new fiscal year with monthly periods can be created via a POST request.

- `test_edit_fiscal_year_view_post(self)`: Tests that a fiscal year's details can be successfully updated via a POST request to the edit view.

- `test_delete_fiscal_year_view_post(self)`: Confirms that a fiscal year can be deleted via a POST request, provided it has no associated transactions.

- `test_change_period_status_view_post(self)`: Verifies that a financial period's status can be changed (e.g., from 'Closed' to 'Open') via a POST request, and that an audit log is created for the action.

- `test_cost_pools_list_view_and_crud(self)`: Tests the full CRUD (Create, Read, Update, Delete) functionality for Cost Pools through the main list view and its POST handling logic.

# File: tests_fixed_assets.py
- **Purpose:** Contains a test suite for the Fixed Assets module, covering model properties, capitalization of inventory, and depreciation processes.

- `setUp(self)`: Prepares the test environment by deleting existing journal entries and creating a sample `FixedAsset` object.

- `test_fixed_asset_properties(self)`: Verifies that the calculated properties on the `FixedAsset` model, such as `depreciable_base` and `net_book_value`, return correct values.

- `test_inventory_consumption_capitalization(self)`: Tests that when an `InventoryConsumption` is marked for capitalization, the resulting journal entry correctly debits the fixed asset's GL account instead of an expense account.

- `test_capitalization_requires_fixed_asset(self)`: Ensures that the model's validation (`clean` method) raises a `ValidationError` if an `InventoryConsumption` is set to 'Capitalize' but is not linked to a `FixedAsset`.

- `test_depreciation_log_and_je_creation(self)`: Verifies that creating a `DepreciationLog` for an asset automatically generates a corresponding, balanced journal entry to record the depreciation expense and update accumulated depreciation.