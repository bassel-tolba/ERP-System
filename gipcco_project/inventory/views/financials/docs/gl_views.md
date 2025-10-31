# File: gipcco_project/inventory/views/financials/docs/gl_views.md

- **Purpose:** This file contains views related to the General Ledger (GL), including journal entries and fixed assets.

---

## `journal_entries(request)`

- **Purpose:** Lists manually created journal entries and provides a link to create new ones.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the list of journal entries.

## `post_journal_entry(request, pk)`

- **Purpose:** Posts a single draft journal entry.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the journal entry.
- **Returns:** A redirect to the journal entries list.

## `create_journal_entry(request)`

- **Purpose:** Handles the creation of a new journal entry using formsets.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the form for creating a journal entry.

## `view_journal_entry(request, pk)`

- **Purpose:** Displays the details of a single journal entry.
- **Args:**
  - `request`: The HTTP request object.
  - `pk`: The primary key of the journal entry.
- **Returns:** An HTTP response with the journal entry details.

## `fixed_assets_dashboard(request)`

- **Purpose:** Displays a list of fixed assets and their depreciation status.
- **Args:**
  - `request`: The HTTP request object.
- **Returns:** An HTTP response with the fixed assets dashboard.
