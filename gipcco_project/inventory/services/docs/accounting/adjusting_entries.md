# File: gipcco_project/inventory/services/accounting/adjusting_entries.py
- **Purpose:** Manages the creation of journal entries for period-end adjusting entries, such as prepaid expense amortization and expense accruals.

### Functions:

- `create_je_for_amortization(amortization_log: AmortizationLog)`:
  - **Description:** Creates a journal entry for the monthly amortization of a prepaid expense. This recognizes the portion of a prepaid asset that has been "used up" during the period.
  - **Accounting Logic:**
    - **Debit:** The specific expense account defined on the `PrepaidExpense` record (e.g., "Insurance Expense").
    - **Credit:** The master "Prepaid Expenses" control account.
  - **Key Features:**
    - Ensures the adjustment is posted to an open financial period.
    - Links the `PrepaidExpense` object as a sub-ledger for detailed tracking.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.

- `create_je_for_accrual(accrual_log: AccrualLog)`:
  - **Description:** Creates a journal entry to recognize an expense that has been incurred but not yet paid.
  - **Accounting Logic:**
    - **Debit:** The specific expense account defined on the `AccruedExpense` record (e.g., "Utilities Expense").
    - **Credit:** The specific accrued liability account defined on the `AccruedExpense` record (e.g., "Accrued Utilities Payable").
  - **Key Features:**
    - Ensures the accrual is recorded in the correct (and open) financial period.
    - Links the `AccruedExpense` object as a sub-ledger for tracking until payment.
  - **Calls:** `_check_period_is_open()` from `_helpers.py`.
