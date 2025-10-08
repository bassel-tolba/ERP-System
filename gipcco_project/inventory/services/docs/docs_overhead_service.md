# File: gipcco_project/inventory/services/overhead_service.py
- **Purpose:** Manages the calculation and application of manufacturing overhead costs to finished goods.

- `calculate_cost_pool_total(cost_pool: CostPool, period: FinancialPeriod)`: Calculates the total expenses for a cost pool and all its sub-pools within a financial period.
  - Traverses the hierarchy to include all descendant cost pools.
  - Aggregates the `amount` from all `ExpenseLog` entries linked to these pools within the period.

- `calculate_driver_units_total(driver: AllocationDriver, period: FinancialPeriod)`: Calculates the total quantity of a specific allocation driver within a financial period.
  - Logic branches based on the driver type (e.g., machine hours, labor hours, units).
  - Aggregates data from `FinishedProductReceipt` and their related `Batch` models.

- `execute_overhead_allocation_run(run: OverheadAllocationRun)`: Executes the main calculations for an overhead allocation run, determining the final overhead rate.
  - Calculates the total cost pool amount and total driver units.
  - Divides the pool total by the driver units to get the overhead rate.
  - Updates and saves the `OverheadAllocationRun` object with the results.
  - **Calls:** `calculate_cost_pool_total()`, `calculate_driver_units_total()` from the current file.

- `apply_overhead_to_finished_goods(run: OverheadAllocationRun)`: Applies the calculated overhead rate to all finished goods receipts within the run's period.
  - Iterates through each `FinishedProductReceipt` in the period.
  - Calculates the specific overhead amount for each receipt based on its driver units.
  - Updates the `allocated_overhead_cost` on the receipts using a bulk update.
  - Sets the `is_overhead_posted` flag on the `PeriodCloseChecklist`.