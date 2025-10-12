# File: gipcco_project/inventory/models/adjusting_entries.py
- **Purpose:** Defines models for managing adjusting entries, such as prepaid expenses and accrued expenses.

- `CostPoolSplit`: A generic linking table to split the cost of a source object across multiple cost pools by percentage.
- `PrepaidExpense`: Represents a prepaid asset, which will be amortized over time.
- `AmortizationLog`: Logs a single amortization event for a prepaid asset.
- `AccruedExpense`: Represents a recurring expense that is estimated and booked monthly.
- `AccrualLog`: Logs a single accrual event for a recurring expense.
