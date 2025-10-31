# File: gipcco_project/inventory/views/financials/docs/overhead_views.md

- **Purpose:** This file contains views related to overhead allocation.

---

## `overhead_allocation_workspace(request)`

- **Purpose:** Manages the period-end overhead allocation process.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the overhead allocation workspace.
- **Calls:**
  - `execute_overhead_allocation_run()`
  - `create_je_for_overhead_allocation()`
  - `apply_overhead_to_finished_goods()`
  - `create_je_for_overhead_application()`
