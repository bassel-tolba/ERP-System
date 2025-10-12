# File: gipcco_project/inventory/services/accounting/overhead_transactions.py
- **Purpose:** Manages the two-step accounting process for factory overhead: allocation and application.

### Functions:

- `create_je_for_overhead_allocation(run: OverheadAllocationRun)`:
  - **Description:** Creates the first journal entry in the overhead process. This entry moves the total accumulated overhead costs for the period from their various expense accounts into the production process.
  - **Accounting Logic:**
    - **Debit:** Work-in-Progress (WIP) Inventory account (for the total allocated amount).
    - **Credit:** Each individual expense account that contributed to the cost pool (e.g., Factory Rent, Indirect Labor), effectively clearing them out.
  - **Key Features:**
    - Gathers expenses from the specified parent cost pool and all its descendants.
    - Ensures a balanced entry by mapping each cost pool to a specific GL account.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_overhead_application(run: OverheadAllocationRun, total_applied_cost: Decimal)`:
  - **Description:** Creates the second journal entry in the overhead process. This entry moves the applied overhead cost from the production process to the value of the finished goods produced during the period.
  - **Accounting Logic:**
    - **Debit:** Finished Goods Inventory account.
    - **Credit:** Work-in-Progress (WIP) Inventory account.
  - **Key Features:**
    - This function is called after the overhead cost has been calculated and applied to individual `FinishedProductReceipts`.
    - Completes the flow of overhead costs from expense to finished goods inventory.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
