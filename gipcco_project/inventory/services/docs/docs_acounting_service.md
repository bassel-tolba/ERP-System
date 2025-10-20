# File: gipcco_project/inventory/services/accounting_service.py
- **Purpose:** This file acts as the central access point for all accounting-related services. It follows a modular pattern, importing functions from more granular service files located in the `accounting/` subdirectory. This approach maintains backward compatibility with the rest of the application while organizing the logic into maintainable, domain-specific files.

- **Design Principle:** No business logic should be added directly to this file. Instead, new logic should be placed in the appropriate specialized service file within the `accounting/` directory and then imported here to be exposed to the rest of the application.

---

### Refactored Service Modules:

Below is the list of the specialized modules that contain the actual business logic. Please refer to their individual documentation for detailed information.

- **[`_helpers.md`](./accounting/_helpers.md):**
  - Contains common, low-level utility functions used across multiple accounting services, such as checking financial period statuses and resolving GL accounts for products.

- **[`inventory_transactions.md`](./accounting/inventory_transactions.md):**
  - Handles journal entries for core inventory movements, including receiving goods from suppliers and internal inventory adjustments (e.g., for damages or cycle count discrepancies).

- **[`production_transactions.md`](./accounting/production_transactions.md):**
  - Manages all journal entries related to the manufacturing process, from the consumption of raw materials into WIP to the receipt of finished goods.

- **[`purchasing_service.md`](./purchasing_service.md):**
  - Manages the complete purchasing and supplier return lifecycle, including three-way match validation, landed cost allocation, and debit memo creation.

- **[`sales_transactions.md`](./accounting/sales_transactions.md):**
  - Responsible for creating the compound journal entries for customer sales, recording both revenue and the cost of goods sold (COGS).

- **[`payment_transactions.md`](./accounting/payment_transactions.md):**
  - Covers all cash-related transactions, including payments to suppliers, payments from customers, and the issuance and settlement of employee cash advances.

- **[`overhead_transactions.md`](./accounting/overhead_transactions.md):**
  - Manages the two-stage process of accounting for factory overhead: allocating costs to WIP and applying those costs to finished goods.

- **[`asset_transactions.md`](./accounting/asset_transactions.md):**
  - Handles journal entries related to fixed assets, primarily the recording of monthly depreciation.

- **[`adjusting_entries.md`](./accounting/adjusting_entries.md):**
  - Manages the creation of period-end adjustments, such as amortizing prepaid expenses and accruing for expenses incurred but not yet paid.

- **[`general_transactions.md`](./accounting/general_transactions.md):**
  - A module for various essential transactions that don't fit into other categories, such as internal consumption of MRO items, inter-bank transfers, and the posting of opening balances.

- **[`correction_transactions.md`](./accounting/correction_transactions.md):**
  - Implements the immutable ledger concept by providing a structured way to reverse incorrect transactions with fully auditable reversing journal entries.

- **[`period_end.md`](./accounting/period_end.md):**
  - Contains high-level service functions designed to be run as part of the period-end closing checklist, such as the batch process for running monthly depreciation on all assets.