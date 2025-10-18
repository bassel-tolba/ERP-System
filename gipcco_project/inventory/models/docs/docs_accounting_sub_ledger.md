# File: gipcco_project/inventory/models/accounting_sub_ledger.py
- **Purpose:** Defines models that represent sub-ledgers for accounts receivable and accounts payable.

- `SupplierInvoice`: Represents an invoice received from a supplier.
- `SupplierInvoiceItem`: Links a specific inventory receipt or expense to a supplier invoice.
- `PaymentApplication`: Applies a payment to a specific supplier invoice.
- `CustomerInvoice`: Represents an invoice sent to a customer.
- `CustomerInvoiceItem`: Links a specific product dispatch to a customer invoice.
- `CustomerPaymentApplication`: Applies a customer payment to a specific customer invoice.
- `CustomerCreditMemo`: Represents a credit memo issued to a customer. Now includes `base_amount` and `vat_amount` fields to accurately reverse the original sale components.
- `SalesReturn`: Represents a return of goods from a customer. Now includes a `status` field to track its progress through the inspection and processing workflow, and a link to the consolidated `cogs_reversal_journal_entry`.
- `SalesReturnItem`: Represents a single item within a sales return. The `reversing_journal_entry` has been removed, as this is now handled by the `InventoryAdjustment` created from the item's disposition.
- `BankTransfer`: Represents the movement of funds between two internal bank accounts.
- `DepreciationLog`: Logs a single depreciation event for a fixed asset.
