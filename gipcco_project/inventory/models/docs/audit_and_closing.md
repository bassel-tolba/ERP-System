# File: gipcco_project/inventory/models/audit_and_closing.py
**Purpose:** This file provides the models necessary for ensuring financial integrity, auditability, and control over the accounting period closing process. These models do not represent transactions themselves but rather track processes and corrections.

### Class: `PeriodClosingAuditLog`
- **Description:** An immutable audit trail that records every status change of a `FinancialPeriod`. It captures who performed the action (close, re-open, lock), when they did it, and why (justification). This is a critical model for compliance and internal control.
- **Key Fields & Relationships:**
    - `financial_period`: Links to the period being changed.
    - `user`: Tracks the user responsible for the action.
    - `action_type`: The specific action performed (`Close`, `Re-open`, `Lock`).
    - `justification`: A mandatory text field for high-risk actions like re-opening a closed period.

### Class: `PeriodCloseChecklist`
- **Description:** A state-tracking model, with a one-to-one relationship to `FinancialPeriod`, that acts as a live dashboard and gatekeeper for the period-end closing process. It ensures all required sub-ledger and adjusting entry processes have been completed before a period can be closed.
- **Key Fields & Relationships:**
    - `financial_period`: A `OneToOneField` ensuring each period has exactly one checklist.
    - **Process Flags** (`is_depreciation_run`, `is_overhead_posted`, etc.): Booleans that are set to `True` by the system only after the corresponding automated period-end service has successfully completed (e.g., `run_monthly_depreciation`).
    - **Validation Flags** (`all_banks_reconciled`, `no_draft_manual_jes`, etc.): Booleans that are updated by a validation service to reflect the current state of the system (e.g., checking for any remaining draft invoices).
    - **Manual Flags** (`is_ar_aging_reviewed`, etc.): Booleans that must be manually checked by an accountant to confirm that a review task has been completed.
- **Business Logic:**
    - The `is_complete` property provides a single boolean value that can be used by the system to determine if the "Close Period" action should be enabled for a user. It aggregates the state of all critical checklist items.

### Class: `TransactionCorrection`
- **Description:** A crucial audit model that embodies the "Immutable Ledger" principle. Instead of deleting or modifying a posted transaction, this model records the act of correcting it. It creates a permanent, auditable link between an original, incorrect transaction and the new, reversing `JournalEntry` that corrects it.
- **Design Pattern:** Immutable Ledger / Compensating Transaction.
- **Key Fields & Relationships:**
    - `source_object`: A `GenericForeignKey` that points to the original document that was incorrect (e.g., a `FinishedProductDispatch`, an `ExpenseLog`).
    - `adjusting_journal_entry`: A `OneToOneField` to the new `JournalEntry` that reverses the financial impact of the original. This tight coupling ensures a clear, two-way link.
    - `justification`: A mandatory text field explaining why the correction was necessary.
    - `corrected_by`: The user who initiated the correction.
- **Integration Points:**
    - The `create_reversing_je_for_correction` service is the primary creator of these records. It first creates the reversing JE, then creates the `TransactionCorrection` record linking the original transaction to the new JE.
