# gipcco_project/inventory/services/accounting/sales_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    FinishedProductDispatch, CustomerCreditMemo
)
from ._helpers import (
    _check_period_is_open, _get_product_expense_account,
    _get_product_revenue_account
)

logger = logging.getLogger(__name__)


def create_je_for_sales_dispatch(dispatch: FinishedProductDispatch) -> Optional[JournalEntry]:
    """
    Creates a compound journal entry for a sales dispatch, recording both COGS and Revenue.
    
    COGS Logic:
    - DEBIT: Cost of Goods Sold (COGS) Expense
    - CREDIT: Finished Goods Inventory
    
    Revenue Logic:
    - DEBIT: Accounts Receivable
    - CREDIT: Sales Revenue
    - CREDIT: VAT Payable (if applicable)
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(dispatch), object_id=dispatch.id
    ).exists():
        return None

    _check_period_is_open(dispatch.dispatch_date)

    settings = GeneralAccountingSettings.load()
    so_item = dispatch.sales_order_item
    final_product = so_item.finished_product.batch.template.final_product

    # 1. --- Get Accounts ---
    fg_account = settings.finished_goods_inventory
    ar_account = settings.accounts_receivable
    vat_payable_account = settings.vat_payable
    cogs_account = _get_product_expense_account(final_product)
    revenue_account = _get_product_revenue_account(final_product)

    if not all([fg_account, ar_account, vat_payable_account, cogs_account, revenue_account]):
        raise ValueError(_("One or more accounts required for sales transactions are not configured."))

    # 2. --- Calculate Amounts ---
    cogs_amount = dispatch.cost_at_dispatch
    
    quantity_sold = Decimal(str(dispatch.quantity))
    base_revenue = quantity_sold * so_item.base_price_per_unit
    vat_amount = base_revenue * so_item.vat_rate
    total_receivable = base_revenue + vat_amount

    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Sale of %(qty)s %(unit)s of '%(product)s' to %(customer)s (SO: %(so_num)s)"
        ) % {
            'qty': dispatch.quantity, 'unit': final_product.unit, 'product': final_product.name,
            'customer': so_item.sales_order.customer.name, 'so_num': so_item.sales_order.so_number
        }
        je = JournalEntry.objects.create(
            date=dispatch.dispatch_date, description=description, source_object=dispatch,
            status=JournalEntry.Status.POSTED
        )
        # COGS Entry
        JournalEntryLine.objects.create(
            journal_entry=je, account=cogs_account, amount=cogs_amount, entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=final_product
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=cogs_amount, entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=final_product
        )
        # Revenue Entry
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar_account, amount=total_receivable, entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=so_item.sales_order.customer
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=revenue_account, amount=base_revenue, entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=final_product
        )
        if vat_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=vat_payable_account, amount=vat_amount, entry_type=JournalEntryLine.EntryType.CREDIT
            )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for FinishedProductDispatch ID {dispatch.id}.")
    return je


def create_je_for_credit_memo(memo: 'CustomerCreditMemo') -> Optional[JournalEntry]:
    """
    Creates a journal entry for a customer credit memo.

    - DEBIT: Sales Returns & Allowances (a contra-revenue account)
    - DEBIT: VAT Payable (reversing the liability from the original sale)
    - CREDIT: Accounts Receivable (reducing the customer's balance)
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(memo), object_id=memo.id
    ).exists():
        return None

    _check_period_is_open(memo.memo_date)

    settings = GeneralAccountingSettings.load()
    ar_account = settings.accounts_receivable
    vat_payable_account = settings.vat_payable
    sales_returns_account = settings.sales_returns_account

    if not all([ar_account, vat_payable_account, sales_returns_account]):
        raise ValueError(_("One or more accounts required for credit memos are not configured."))

    with transaction.atomic():
        description = _(
            "Credit Memo %(memo_num)s issued to %(customer)s"
        ) % {'memo_num': memo.memo_number, 'customer': memo.customer.name}

        je = JournalEntry.objects.create(
            date=memo.memo_date, description=description, source_object=memo,
            status=JournalEntry.Status.POSTED
        )

        # Debit Sales Returns (Contra-Revenue)
        JournalEntryLine.objects.create(
            journal_entry=je, account=sales_returns_account, amount=memo.base_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=memo.customer
        )

        # Debit VAT Payable (Reversing Liability)
        if memo.vat_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=vat_payable_account, amount=memo.vat_amount,
                entry_type=JournalEntryLine.EntryType.DEBIT
            )

        # Credit Accounts Receivable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar_account, amount=memo.total_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT, sub_ledger_object=memo.customer
        )

        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for CustomerCreditMemo ID {memo.id}.")
    return je
