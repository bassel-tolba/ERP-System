# File: gipcco_project/inventory/models/overhead_allocation.py
**Purpose:** This file defines the models for the manufacturing overhead allocation system. This system allows for the accumulation of indirect production costs (like factory rent, utilities) into cost pools and their systematic application to the value of finished goods based on a chosen driver.

### Class: `CostPool`
- **Description:** A hierarchical model for defining and grouping overhead cost categories, similar in structure to the Chart of Accounts. It allows for detailed tracking and allocation of indirect costs.
- **Key Fields & Relationships:**
    - `parent`: A self-referential foreign key that creates the tree structure (e.g., "Factory Utilities" could be a child of "Total Factory Overhead").
    - `gl_account`: An optional, direct link to a specific expense `Account` in the General Ledger. This allows the system to automatically gather all costs posted to that GL account for inclusion in the pool's total.
- **Business Logic:**
    - The `save()` method contains logic to auto-generate a hierarchical `code` for new cost pools if one is not provided, making the structure easy to navigate.

### Class: `AllocationDriver`
- **Description:** A master list of the methodologies or bases that can be used to allocate overhead costs to production. The choice of driver determines how the total overhead cost is spread across different products.
- **Key Fields & Relationships:**
    - `name`: A `TextChoices` field with predefined, system-supported drivers like `Machine Hours`, `Labor Hours`, `Total Production Units`, etc. The business logic in the `overhead_service` is keyed off these specific choices.

### Class: `OverheadAllocationRun`
- **Description:** The primary transactional model for the overhead process. A new record is created for each `CostPool` for each `FinancialPeriod`. It captures the state and results of the entire allocation and application process for that pool and period.
- **State Transitions & Business Logic:**
    - **Status Workflow:** `Pending` -> `Calculated` -> `Posted to GL` -> `Applied to Inventory`. This status tracks the run through its multi-step lifecycle.
- **Key Fields & Relationships:**
    - `total_pool_amount`: The total indirect expenses accumulated in the `cost_pool` for the period.
    - `total_driver_units`: The total quantity of the chosen `allocation_driver` that occurred during the period (e.g., total machine hours run across all production).
    - `calculated_rate`: The final overhead rate (`total_pool_amount` / `total_driver_units`). This rate is then applied to individual `FinishedProductReceipts`.
    - `journal_entry`: Links to the first JE, which moves the `total_pool_amount` from various expense accounts into the Work-in-Progress (WIP) account.
    - `application_journal_entry`: Links to the second JE, which moves the value of the applied overhead from the WIP account to the Finished Goods Inventory account.
- **Data Integrity:**
    - `unique_together = ('financial_period', 'cost_pool')`: A critical constraint that ensures the overhead allocation for a specific cost pool can only be run once per financial period.
