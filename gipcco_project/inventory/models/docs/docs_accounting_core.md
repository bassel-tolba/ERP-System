# File: gipcco_project/inventory/models/accounting_core.py
- **Purpose:** Defines the foundational models for the accounting system, including the chart of accounts, journal entries, and fiscal periods.

- `FiscalYear`: Represents a fiscal year, containing multiple financial periods.
- `FinancialPeriod`: Represents a single accounting period (e.g., a month) within a fiscal year.
- `Account`: Defines a single account in the chart of accounts, including its type (asset, liability, etc.) and parent-child relationships.
- `JournalEntry`: Represents a single journal entry, containing multiple lines that must balance.
- `JournalEntryLine`: Represents a single line within a journal entry, either a debit or a credit to a specific account.
- `ProductTypeAccountingSettings`: Configures default GL accounts for different product types.
- `GeneralAccountingSettings`: A singleton model to hold system-wide accounting configuration, preventing hardcoded account codes.
