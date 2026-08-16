<img width="500" height="300" alt="image" src="https://github.com/user-attachments/assets/a91afddb-595a-4832-a095-e1a0d1b28b33" />


# GIPCCO ERP

Django-based ERP system covering accounting, inventory, manufacturing (batches), purchasing, sales, and financial reporting for GIPCCO. Started as an inventory tracker, turned into a full-blown accounting system. It happens.

## Stack

- **Backend:** Django
- **DB:** SQLite for local dev (`inventory.db`).
- **Frontend:** Server-rendered templates + HTMX for page swaps.
- **UI:** Bootstrap 5, Chart.js, Tom Select, Flatpickr.
- **Other:** htmx, custom middleware, Django signals.

## What's actually in here

This isn't a toy CRUD app. The `inventory` app covers:

**Accounting core**
- Chart of accounts, journal entries, general ledger
- AR/AP sub-ledgers
- Adjusting entries — accruals, prepaids, corrections
- Period close workflow, closing checklist, audit log
- Bank reconciliation & transfers
- Opening balances

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
- Most of these also render as PDFs

## Getting started

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

There's also a `start.sh` in the root — check what that actually sets up before relying on it, I don't have it in front of me right now so I won't promise what env vars or flags it wires in.

management commands once you're up:

```bash
python manage.py accounts_chart_first_make 
python manage.py setup_test_data 
python manage.py setup_batch_permissions
python manage.py post_depreciation 
```

## Tests

Split by domain — `tests_accounting.py`, `tests_batches.py`, `tests_sales.py`, `tests_purchasing.py`, `tests_period_closing.py`, `tests_fixed_assets.py`, `tests_hr.py`, `tests_banking.py`, etc, all sharing `test_base.py`. Run:

```bash
python manage.py test inventory
```

## Known rough edges

Being upfront:

- **67 migrations**, Schema went through some back-and-forth. Fine functionally, just don't be surprised. Might be worth squashing at some point.
