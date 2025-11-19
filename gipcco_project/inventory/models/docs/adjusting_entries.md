# File: gipcco_project/inventory/models/adjusting_entries.py
**Purpose:** This file defines the models necessary for managing period-end adjusting entries, specifically for prepaid expenses and accrued expenses. These models form the sub-ledgers that allow for the proper recognition of expenses over time according to the accrual basis of accounting.

### Class: `CostPoolSplit`
- **Description:** A generic linking model that enables the cost of a single transaction (like a prepaid expense or an accrual) to be split and allocated across multiple `CostPool`s by a defined percentage. This is crucial for accurate departmental or project-based costing.
- **Design Pattern:** Uses a `GenericForeignKey` to link to various source models (`PrepaidExpense`, `AccruedExpense`), making it a reusable and flexible allocation tool.
- **Data Integrity:**
    - The `clean()` method ensures that the sum of all percentage splits for a single source object does not exceed 100%, preventing over-allocation of costs.

### Class: `PrepaidExpense`
- **Description:** Represents a prepaid asset—an expense paid in advance that will be recognized over multiple future accounting periods (e.g., annual insurance premium). This model serves as the sub-ledger for the "Prepaid Expenses" control account.
- **Key Fields & Relationships:**
    - `initial_amount`: The total value of the asset when it was created.
    - `amortization_start_date`, `amortization_end_date`: Defines the period over which the asset will be expensed.
    - `asset_account`, `expense_account`: Specifies the GL accounts for the balance sheet asset and the income statement expense, respectively.
    - `status`: Tracks the lifecycle (`Active`, `Fully Amortized`, `Written Off`).
    - `source_content_object`: A `GenericForeignKey` linking the prepaid asset back to its origin (e.g., a `SupplierInvoice` or an `InventoryConsumption`).
    - `cost_pool_splits`: A `GenericRelation` to `CostPoolSplit`, allowing the monthly amortized expense to be distributed.
- **Financial Impact:**
    - Its creation typically involves a debit to the `asset_account`.
    - Each month, the period-end service creates an `AmortizationLog` against it, which in turn generates a journal entry to debit the `expense_account` and credit the `asset_account`.

### Class: `AmortizationLog`
- **Description:** An audit and control model that records a single monthly amortization event for a `PrepaidExpense`.
- **Data Integrity:**
    - `unique_together = ('prepaid_expense', 'financial_period')`: A critical constraint that prevents the same prepaid asset from being amortized twice in the same period.
- **Financial Impact:**
    - The creation of an `AmortizationLog` triggers the `create_je_for_amortization` service, which posts the monthly expense recognition journal entry.

### Class: `AccruedExpense`
- **Description:** Represents a recurring expense that is recognized in the period it is incurred, even if the supplier invoice has not yet been received (e.g., estimated monthly utility bill). This model serves as the sub-ledger for the "Accrued Expenses" liability account.
- **Key Fields & Relationships:**
    - `total_estimated_amount`: The estimated value of the expense.
    - `accrual_start_date`, `accrual_end_date`: The period over which the expense is expected to be incurred.
    - `target_expense_account`, `target_liability_account`: Specifies the GL accounts for the expense and the corresponding liability.
- **Financial Impact:**
    - Each month, the period-end service creates an `AccrualLog` against it, which generates a journal entry to debit the `target_expense_account` and credit the `target_liability_account`.

### Class: `AccrualLog`
- **Description:** Records a single monthly accrual event for an `AccruedExpense`. It also tracks the final "true-up" when the actual invoice arrives.
- **Key Fields & Relationships:**
    - `settling_invoice`: A foreign key to the `SupplierInvoice` that finally settles this accrued amount.
    - `true_up_journal_entry`: A link to the journal entry that reverses the accrual and books the actual invoice, providing a complete audit trail.
- **Data Integrity:**
    - `unique_together = ('accrued_expense', 'financial_period')`: Prevents the same expense from being accrued twice in one period.
