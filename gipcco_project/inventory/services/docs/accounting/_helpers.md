<!-- gipcco_project/inventory/services/docs/accounting/_helpers.md -->
# File: gipcco_project/inventory/services/accounting/_helpers.py
- **Purpose:** Provides common, low-level helper functions used by various accounting services to ensure consistency and reduce code duplication.

### Functions:

- `_check_period_is_open(date_to_check)`:
  - **Description:** The authoritative gatekeeper for all financially relevant transactions. It checks if a given date falls within a financial period that is currently open.
  - **Raises:** `PermissionDenied` if the period is closed, permanently locked, or does not exist. This prevents any postings to incorrect or closed periods.

- `_get_product_account(product: Product, account_type: str)`:
  - **Description:** The single source of truth for resolving a product-related GL account (Inventory, COGS, or Revenue). This generic function is called by the more specific helpers below.
  - **Logic:**
    1. Checks for a specific override account on the `Product` instance.
    2. If not found, falls back to the default account defined on the `ProductTypeAccountingSettings` for the product's type.
  - **Raises:** `ValueError` if no account can be resolved, ensuring all products are correctly mapped.

- `_get_product_inventory_account(product: Product)`:
  - **Description:** A convenience wrapper that calls `_get_product_account` to retrieve the correct inventory GL account for a given product.

- `_get_product_expense_account(product: Product)`:
  - **Description:** A convenience wrapper that calls `_get_product_account` to retrieve the correct Cost of Goods Sold (COGS) or general expense GL account for a given product.

- `_get_product_revenue_account(product: Product)`:
  - **Description:** A convenience wrapper that calls `_get_product_account` to retrieve the correct sales revenue GL account for a given product.