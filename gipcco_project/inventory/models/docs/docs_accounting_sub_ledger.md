# File: gipcco_project/inventory/models/accounting_sub_ledger.py
- **Purpose:** Defines models that represent sub-ledgers for accounts receivable and accounts payable.

- `SupplierInvoice`: Represents an invoice received from a supplier.
- `SupplierInvoiceItem`: Links a specific inventory receipt or expense to a supplier invoice.
- `PaymentApplication`: Applies a payment to a specific supplier invoice.
- `CustomerInvoice`: Represents an invoice sent to a customer.
- `CustomerInvoiceItem`: Links a specific product dispatch to a customer invoice.
- `CustomerPaymentApplication`: Applies a customer payment to a specific customer invoice.
- `CustomerCreditMemo`: Represents a credit memo issued to a customer.
- `SalesReturn`: Represents a return of goods from a customer.
- `SalesReturnItem`: Represents a single item within a sales return.
- `BankTransfer`: Represents the movement of funds between two internal bank accounts.
- `DepreciationLog`: Logs a single depreciation event for a fixed asset.
