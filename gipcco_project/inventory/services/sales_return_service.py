# gipcco_project/inventory/services/sales_return_service.py
from django.db import transaction
from ..models import (
    SalesReturnItem, JournalEntry, JournalEntryLine, GeneralAccountingSettings, InventoryAdjustment
)
from .accounting_service import _get_product_expense_account

def process_return_item(return_item: SalesReturnItem):
    """
    Handles the financial transactions for a single returned item.
    """
    dispatch = return_item.original_dispatch
    cost_to_reverse = dispatch.cost_at_dispatch # Use the exact original cost

    with transaction.atomic():
        # 1. Create the COGS Reversal JE
        settings = GeneralAccountingSettings.load()
        fg_account = settings.finished_goods_inventory
        final_product = dispatch.sales_order_item.finished_product.batch.template.final_product
        cogs_account = _get_product_expense_account(final_product)
        
        je = JournalEntry.objects.create(
            date=return_item.sales_return.return_date,
            description=f"COGS reversal for return of {final_product.name}",
            source_object=return_item
        )
        # Debit FG Inventory (brings value back)
        JournalEntryLine.objects.create(journal_entry=je, account=fg_account, amount=cost_to_reverse, entry_type='debit', sub_ledger_object=final_product)
        # Credit COGS (reverses expense)
        JournalEntryLine.objects.create(journal_entry=je, account=cogs_account, amount=cost_to_reverse, entry_type='credit', sub_ledger_object=final_product)

        return_item.reversing_journal_entry = je
        return_item.save()

        # 2. Handle Disposition (after inspection)
        if return_item.disposition == SalesReturnItem.Disposition.SCRAP:
            # Create an InventoryAdjustment to write off the value
            InventoryAdjustment.objects.create(
                product=dispatch.sales_order_item.finished_product.batch.template.final_product,
                adjustment_quantity=-return_item.quantity_returned,
                cost_at_adjustment=cost_to_reverse / dispatch.quantity,
                reason_code=InventoryAdjustment.ReasonCode.DAMAGE,
                source_finished_product=dispatch.sales_order_item.finished_product,
                adjustment_date=return_item.sales_return.return_date,
                notes=f"Scrapped from sales return {return_item.sales_return.id}"
            ) # This will trigger its own JE: Debit Scrap Expense, Credit FG Inventory
