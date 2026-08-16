# gipcco_project/inventory/services/accounting/sales_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    FinishedProductDispatch, CustomerCreditMemo
)
from ._helpers import (
    _get_product_expense_account,
    _get_product_revenue_account
)
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def create_je_for_sales_dispatch(dispatch: FinishedProductDispatch) -> Optional[JournalEntry]:
    """
    Creates a compound journal entry for a sales dispatch, recording both COGS and Revenue.
    """
    settings = GeneralAccountingSettings.load()
    so_item = dispatch.sales_order_item
    final_product = so_item.finished_product.batch.template.final_product

    fg_account = settings.finished_goods_inventory
    ar_account = settings.accounts_receivable
    vat_payable_account = settings.vat_payable
    cogs_account = _get_product_expense_account(final_product)
    revenue_account = _get_product_revenue_account(final_product)
    if not all([fg_account, ar_account, vat_payable_account, cogs_account, revenue_account]):
        raise ValueError(_("One or more accounts required for sales transactions are not configured."))

    cogs_amount = dispatch.cost_at_dispatch
    quantity_sold = Decimal(str(dispatch.quantity))
    base_revenue = quantity_sold * so_item.base_price_per_unit
    vat_amount = base_revenue * so_item.vat_rate
    total_receivable = base_revenue + vat_amount

    description = _("Sale of %(qty)s %(unit)s of '%(product)s' to %(customer)s (SO: %(so_num)s)") % {
        'qty': dispatch.quantity, 'unit': final_product.unit, 'product': final_product.name,
        'customer': so_item.sales_order.customer.name, 'so_num': so_item.sales_order.so_number
    }

    builder = JournalEntryBuilder(source_object=dispatch)
    builder.set_description(description)
    # COGS
    builder.debit(cogs_amount, cogs_account, sub_ledger_object=final_product)
    builder.credit(cogs_amount, fg_account, sub_ledger_object=final_product)
    # Revenue
    builder.debit(total_receivable, ar_account, sub_ledger_object=so_item.sales_order.customer)
    builder.credit(base_revenue, revenue_account, sub_ledger_object=final_product)
    builder.credit(vat_amount, vat_payable_account)
    return builder.post()


def create_je_for_credit_memo(memo: 'CustomerCreditMemo') -> Optional[JournalEntry]:
    """
    Creates a journal entry for a customer credit memo.
    """
    settings = GeneralAccountingSettings.load()
    ar_account = settings.accounts_receivable
    vat_payable_account = settings.vat_payable
    sales_returns_account = settings.sales_returns_account
    if not all([ar_account, vat_payable_account, sales_returns_account]):
        raise ValueError(_("One or more accounts required for credit memos are not configured."))

    description = _("Credit Memo %(memo_num)s issued to %(customer)s") % {
        'memo_num': memo.memo_number, 'customer': memo.customer.name
    }

    builder = JournalEntryBuilder(source_object=memo)
    builder.set_description(description)
    builder.debit(memo.base_amount, sales_returns_account, sub_ledger_object=memo.customer)
    builder.debit(memo.vat_amount, vat_payable_account)
    builder.credit(memo.total_amount, ar_account, sub_ledger_object=memo.customer)
    return builder.post()

