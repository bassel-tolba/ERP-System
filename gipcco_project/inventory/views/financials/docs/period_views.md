# File: gipcco_project/inventory/views/financials/docs/period_views.md

- **Purpose:** This file contains views related to financial period management.

---

## `fiscal_year_list(request)`

- **Purpose:** Lists all Fiscal Years and their associated Financial Periods.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of fiscal years.

## `create_fiscal_year(request)`

- **Purpose:** Handles the creation of a new Fiscal Year and optionally its monthly periods.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** A redirect to the fiscal year list.

## `create_financial_period(request, year_id)`

- **Purpose:** Handles the creation of a single, custom financial period.
- **Args:**
  - `request`: The HTTP request object.
  - `year_id`: The primary key of the fiscal year.
- **Returns:** A redirect to the fiscal year list.

## `edit_fiscal_year(request, pk)`

- **Purpose:** Handles the updating of a Fiscal Year's details.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the fiscal year.
- **Returns:** A redirect to the fiscal year list.

## `delete_fiscal_year(request, pk)`

- **Purpose:** Handles the deletion of a Fiscal Year, with safety checks.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the fiscal year.
- **Returns:** A redirect to the fiscal year list.

## `generate_monthly_periods(request, year_id)`

- **Purpose:** Generates 12 monthly Financial Periods for a given Fiscal Year.
- **Args:**
  - `request`: The HTTP request object.
  - `year_id`: The primary key of the fiscal year.
- **Returns:** A redirect to the fiscal year list.

## `change_period_status(request, period_id)`

- **Purpose:** Handles changing the status of a financial period.
- **Args:**
  - `request`: The HTTP request object.
  - `period_id`: The primary key of the financial period.
- **Returns:** A redirect to the fiscal year list.

## `close_period_action(request, period_id)`

- **Purpose:** Handles the final action of closing a financial period after all checks pass.
- **Args:**
  - `request`: The HTTP request object.
  - `period_id`: The primary key of the financial period.
- **Returns:** A redirect to the fiscal year list or the closing cockpit.
- **Calls:** `update_checklist_for_period()`

## `close_period_cockpit(request, period_id)`

- **Purpose:** Displays the 'Closing Cockpit' UI for a specific financial period.
- **Args:**
  - `request`: The HTTP request object.
  - `period_id`: The primary key of the financial period.
- **Returns:** An HTTP response with the closing cockpit.
- **Calls:** `update_checklist_for_period()`

## `api_period_checklist_status(request, period_id)`

- **Purpose:** API endpoint to check the status of pre-closing conditions for a period.
- **Args:**
  - `request`: The HTTP request object.
  - `period_id`: The primary key of the financial period.
- **Returns:** A JSON response with the checklist status.

## `view_period_audit_log(request, period_id)`

- **Purpose:** Displays the audit log for a specific financial period.
- **Args:**
  - `request`: The HTTP request object.
  - `period_id`: The primary key of the financial period.
- **Returns:** An HTTP response with the audit log.
