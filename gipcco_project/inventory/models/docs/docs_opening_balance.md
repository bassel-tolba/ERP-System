# File: gipcco_project/inventory/models/opening_balance.py
- **Purpose:** Defines models for migrating opening balances into the system.

- `OpeningBalanceEntry`: Header for an opening balance data migration event.
- `OpeningBalanceEntryLine`: A single line in an opening balance entry, corresponding to one GL account.
- `OpeningBalanceSubLedgerDetail`: Links a specific sub-ledger record to an opening balance line.
