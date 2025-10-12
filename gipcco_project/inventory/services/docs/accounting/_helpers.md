# File: gipcco_project/inventory/services/accounting/_helpers.py
- **Purpose:** Provides common, low-level helper functions used by various accounting services to ensure consistency and reduce code duplication.

### Functions:

- `_check_period_is_open(date_to_check)`:
  - **Description:** The authoritative gatekeeper for all financially relevant transactions. It checks if a given date falls within a financial period that is currently open.
  - **Raises:** `PermissionDenied` if the period is closed, permanently locked, or does not exist. This prevents any postings to incorrect or closed periods.

- `_get_product_inventory_account(product: Product)`:
  - **Description:** Retrieves the correct inventory GL account for a given product.
  - **Logic:** It first checks if the product has a specific `override_inventory_account` set. If not, it falls back to the default `inventory_account` defined in the `ProductTypeAccountingSettings` for the product's type.
  - **Raises:** `ValueError` if no account can be found, ensuring that all inventory items are correctly mapped in the chart of accounts.

- `_get_product_expense_account(product: Product)`:
  - **Description:** Retrieves the correct Cost of Goods Sold (COGS) or general expense GL account for a given product.
  - **Logic:** It first checks for a product-specific `override_cogs_expense_account`. If not present, it uses the default `cogs_or_expense_account` from the product's type settings.
  - **Raises:** `ValueError` if no account is configured, preventing un-mapped expense transactions.

- `_get_product_revenue_account(product: Product)`:
  - **Description:** Retrieves the correct sales revenue GL account for a given product.
  - **Logic:** It prioritizes the product's `override_sales_revenue_account` before falling back to the default `sales_revenue_account` defined in the product's type settings.
  - **Raises:** `ValueError` if no revenue account is configured, ensuring all sales are properly recorded.
