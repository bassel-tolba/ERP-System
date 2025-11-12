<!-- gipcco_project/inventory/services/docs/accounting/_builder.md -->
# File: gipcco_project/inventory/services/accounting/_builder.py
- **Purpose:** Provides a fluent `JournalEntryBuilder` class to standardize and simplify the creation of `JournalEntry` objects and their associated lines across the application.

### Class: `JournalEntryBuilder`

- **Description:** Encapsulates the common, boilerplate logic required for creating valid journal entries. This includes transaction management, period validation, balance checking, and linking the entry back to its source document. Using this builder ensures consistency and reduces errors.

- **`__init__(self, source_object: Any)`**:
  - The constructor takes the source model instance (e.g., an `InventoryLog`, `Payment`, `Batch`) that is triggering the financial transaction.
  - It automatically determines the `ContentType` and attempts to infer a sensible transaction `date` from common field names on the source object (`date`, `period_date`, `creation_date`, etc.), defaulting to `timezone.now()`.

- **`set_date(self, date)`**:
  - Allows for explicitly overriding the inferred transaction date.

- **`set_description(self, description: str)`**:
  - Sets the main description for the `JournalEntry`.

- **`set_notes(self, notes: str)`**:
  - Sets the optional notes for the `JournalEntry`.

- **`debit(self, amount: Decimal, account: Account, ...)`**:
  - Adds a debit line to the journal entry. It automatically ignores lines with a zero or negative amount.
  - Can optionally link a `sub_ledger_object` to the line.

- **`credit(self, amount: Decimal, account: Account, ...)`**:
  - Adds a credit line to the journal entry. It automatically ignores lines with a zero or negative amount.
  - Can optionally link a `sub_ledger_object` to the line.

- **`post(self, link_to_source_field: str = 'journal_entry')`**:
  - The final method that executes the creation process.
  - **Workflow:**
    1. Checks if a journal entry already exists for the source object to prevent duplicates.
    2. Calls `_check_period_is_open()` to ensure the transaction date is in an open financial period.
    3. Returns `None` if the total transaction amount is zero.
    4. Wraps the entire creation process in a database transaction (`transaction.atomic`).
    5. Creates the `JournalEntry` header and all the prepared `JournalEntryLine` objects.
    6. Calls `je.validate_balance()` to ensure debits equal credits.
    7. Links the newly created `JournalEntry` back to the source object on the specified field (e.g., `source_object.journal_entry = je`).
    8. Returns the created `JournalEntry` instance or `None`.