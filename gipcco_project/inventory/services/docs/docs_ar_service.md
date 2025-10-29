 File: gipcco_project/inventory/services/ar_service.py
- **Purpose:** Provides services for Accounts Receivable (A/R) operations, specifically for applying credits to customer invoices.

- `apply_customer_credit(invoice, credit_source, amount_to_apply)`: Applies a credit from an unapplied payment or credit memo to an invoice and creates the corresponding journal entry.
  - Operates within a database transaction.
  - Determines the correct debit account (Customer Deposits or Sales Returns) based on the credit source type.
  - Creates a journal entry to move value from the source account to Accounts Receivable.
  