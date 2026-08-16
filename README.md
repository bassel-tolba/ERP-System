# GIPCCO ERP

Django-based ERP system covering accounting, inventory, manufacturing (batches), purchasing, sales, and financial reporting for GIPCCO. Started as an inventory tracker, turned into a full-blown accounting system somewhere around migration 0030. It happens.

RTL/Arabic support is baked in (see `bootstrap.rtl.css`, the Arabic Flatpickr locale, and yes, there's a stray `الحسابات.html` sitting in the app root — more on that below), so this is built with an Arabic-first user base in mind.

## Stack

- **Backend:** Django (single app: `inventory`, doing a LOT of heavy lifting)
- **DB:** SQLite for local dev (`inventory.db`). No idea what's configured for prod — check `settings.py` before you assume anything.
- **Frontend:** Server-rendered templates + HTMX for page swaps (no SPA framework, no build step). `dynamic_content_loader.js` is the backbone of the "content" partial pattern you'll see all over `templates/inventory/partials/`.
- **UI:** Bootstrap 5 (incl. RTL build), Chart.js for dashboards, Tom Select for fancy dropdowns, Flatpickr for date pickers (Arabic locale included).
- **Other:** htmx, custom middleware, Django signals for side effects.

If you're new to the codebase, `static/layout/summary_of_all_the_js_files.md` already exists and documents the per-page JS files — read that before you go hunting through `static/layout/js/` yourself.

## What's actually in here

This isn't a toy CRUD app. The `inventory` app covers:

**Accounting core**
- Chart of accounts, journal entries, general ledger (`models/accounting_core.py`)
- AR/AP sub-ledgers (`accounting_sub_ledger.py`)
- Adjusting entries — accruals, prepaids, corrections (`adjusting_entries.py`)
- Period close workflow, closing checklist, audit log (`audit_and_closing.py`)
- Bank reconciliation & transfers (`bank_reconciliation.py`, `sub_ledger_banking.py`)
- Opening balances (`opening_balance.py`)

**Manufacturing / Inventory**
- Batches (production runs), batch items, approvals
- Overhead allocation — cost pools, allocation drivers, allocation runs
- Landed cost invoices and allocation
- Inventory counts, variance, quarantine, scrap
- Finished product receipts

**Purchasing**
- Purchase orders, purchase returns, supplier invoices, landed cost tie-in

**Sales**
- Sales orders, customer invoices, credit memos, sales returns, customer payments/applications

**Expenses / HR**
- Expense requests, employee advances & settlements, category settings
- Fixed assets + depreciation posting

**Reporting**
- Trial balance, GL, P&L, stock valuation, tax reconciliation
- AR aging, customer statements
- Sales by customer/product, sales order backlog
- Batch production variance report
- Most of these also render as PDFs (see `templates/inventory/reports/`)

## Getting started

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

There's also a `start.sh` in the root — check what that actually sets up before relying on it, I don't have it in front of me right now so I won't promise what env vars or flags it wires in.

Useful management commands once you're up:

```bash
python manage.py accounts_chart_first_make   # seeds the chart of accounts, run this first on a fresh DB
python manage.py setup_test_data             # demo/test data
python manage.py setup_batch_permissions     # sets up permission groups for batch workflows
python manage.py post_depreciation           # posts fixed asset depreciation for the period
```

## Tests

Split by domain, not by app structure — `tests_accounting.py`, `tests_batches.py`, `tests_sales.py`, `tests_purchasing.py`, `tests_period_closing.py`, `tests_fixed_assets.py`, `tests_hr.py`, `tests_banking.py`, etc., all sharing `test_base.py`. Run the usual way:

```bash
python manage.py test inventory
```

## Known rough edges

Being upfront about the stuff that'll confuse you if you go digging:

- **67 migrations**, several of them add-then-remove-then-re-add the same field (batch approval fields especially). Schema went through some back-and-forth. Fine functionally, just don't be surprised. Might be worth squashing at some point.
