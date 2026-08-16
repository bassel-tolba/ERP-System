# gipcco_project/inventory/services/sales_return_service.py
import logging
from decimal import Decimal
from typing import List

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from ..models import (
    SalesReturn, SalesReturnItem, JournalEntry, JournalEntryLine,
    GeneralAccountingSettings, InventoryAdjustment, CustomerCreditMemo
)
from .accounting._helpers import _get_product_expense_account, _check_period_is_open

logger = logging.getLogger(__name__)


def process_inspected_return(sales_return: SalesReturn):
    """
    Processes a sales return after it has been inspected.

    This is the primary inventory-side function for a return. It performs two key actions:
    1. Creates a single, consolidated journal entry to reverse the Cost of Goods Sold for all
       items in the return. This JE uses a temporary "clearing" account.
    2. Creates individual `InventoryAdjustment` records for each return item based on its
       final disposition (e.g., 'Return to Stock' or 'Scrap'). The signals on the
       `InventoryAdjustment` model will then create their own JEs, which will credit
       the clearing account, zeroing it out.
    """
    logger.info(f"Processing inspected sales return ID: {sales_return.id}")
    if sales_return.status != SalesReturn.Status.PENDING_PROCESSING:
        raise ValidationError(
            _("This return cannot be processed. It is not in the 'Pending Processing' status.")
        )

    return_items = sales_return.items.select_related(
        'original_dispatch__sales_order_item__finished_product__batch__template__final_product'
    ).all()

    if not return_items:
        raise ValidationError(_("This sales return has no items to process."))

    if any(item.disposition is None for item in return_items):
        raise ValidationError(_("All items must have a disposition set before processing."))

    with transaction.atomic():
        _check_period_is_open(sales_return.return_date)

        # 1. Create the consolidated COGS Reversal JE
        settings = GeneralAccountingSettings.load()
        clearing_account = settings.sales_returns_clearing_account
        if not clearing_account:
            raise ValidationError(_("The 'Sales Returns Clearing Account' is not configured in General Accounting Settings."))

        if sales_return.cogs_reversal_journal_entry:
            logger.warning(f"COGS reversal JE for SalesReturn {sales_return.id} already exists. Skipping creation.")
        else:
            total_cost_to_reverse = Decimal('0.0')
            je_description_parts = []

            for item in return_items:
                dispatch = item.original_dispatch
                cost_per_unit = (dispatch.cost_at_dispatch / Decimal(str(dispatch.quantity))) if dispatch.quantity > 0 else Decimal('0.0')
                item_cost_to_reverse = (cost_per_unit * Decimal(str(item.quantity_returned))).quantize(Decimal('0.001'))
                total_cost_to_reverse += item_cost_to_reverse
                
                final_product = dispatch.sales_order_item.finished_product.batch.template.final_product
                cogs_account = _get_product_expense_account(final_product)

                # Create JE line for this item's COGS reversal
                # We'll create the JE header after the loop
                je_description_parts.append(f"{item.quantity_returned}x {final_product.name}")

            je_description = _("COGS reversal for return of %(items)s from %(customer)s") % {
                'items': ", ".join(je_description_parts),
                'customer': sales_return.customer.name
            }

            je = JournalEntry.objects.create(
                date=sales_return.return_date,
                description=je_description,
                source_object=sales_return
            )

            # Debit the clearing account with the total value
            JournalEntryLine.objects.create(
                journal_entry=je, account=clearing_account, amount=total_cost_to_reverse,
                entry_type=JournalEntryLine.EntryType.DEBIT
            )

            # Create a credit line for each unique COGS account
            cogs_credits = {}
            for item in return_items:
                dispatch = item.original_dispatch
                cost_per_unit = (dispatch.cost_at_dispatch / Decimal(str(dispatch.quantity))) if dispatch.quantity > 0 else Decimal('0.0')
                item_cost_to_reverse = (cost_per_unit * Decimal(str(item.quantity_returned))).quantize(Decimal('0.001'))
                final_product = dispatch.sales_order_item.finished_product.batch.template.final_product
                cogs_account = _get_product_expense_account(final_product)
                cogs_credits.setdefault(cogs_account, Decimal('0.0'))
                cogs_credits[cogs_account] += item_cost_to_reverse

            for account, amount in cogs_credits.items():
                JournalEntryLine.objects.create(
                    journal_entry=je, account=account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )

            je.validate_balance()
            sales_return.cogs_reversal_journal_entry = je
            logger.info(f"Created consolidated COGS reversal JE-{je.id} for SalesReturn {sales_return.id}.")

        # 2. Create Inventory Adjustments based on disposition
        for item in return_items:
            # Check if an adjustment already exists for this item
            if hasattr(item, 'inventory_adjustment') and item.inventory_adjustment is not None:
                logger.warning(f"InventoryAdjustment for SalesReturnItem {item.id} already exists. Skipping.")
                continue

            dispatch = item.original_dispatch
            final_product = dispatch.sales_order_item.finished_product.batch.template.final_product
            cost_per_unit = (dispatch.cost_at_dispatch / Decimal(str(dispatch.quantity))) if dispatch.quantity > 0 else Decimal('0.0')
            
            notes_template = _("From sales return %(return_id)s for customer %(customer)s") % {
                'return_id': sales_return.id,
                'customer': sales_return.customer.name
            }

            if item.disposition == SalesReturnItem.Disposition.RETURN_TO_STOCK:
                InventoryAdjustment.objects.create(
                    product=final_product,
                    adjustment_quantity=item.quantity_returned, # Positive quantity
                    cost_at_adjustment=cost_per_unit,
                    reason_code=InventoryAdjustment.ReasonCode.SALES_RETURN_STOCK,
                    source_finished_product=dispatch.sales_order_item.finished_product,
                    adjustment_date=sales_return.return_date,
                    notes=notes_template,
                    source_sales_return_item=item
                )
                logger.info(f"Created 'Return to Stock' InventoryAdjustment for SalesReturnItem {item.id}.")

            elif item.disposition == SalesReturnItem.Disposition.SCRAP:
                InventoryAdjustment.objects.create(
                    product=final_product,
                    adjustment_quantity=-item.quantity_returned, # Negative quantity
                    cost_at_adjustment=cost_per_unit,
                    reason_code=InventoryAdjustment.ReasonCode.DAMAGE,
                    source_finished_product=dispatch.sales_order_item.finished_product,
                    adjustment_date=sales_return.return_date,
                    notes=notes_template,
                    source_sales_return_item=item
                )
                logger.info(f"Created 'Scrap' InventoryAdjustment for SalesReturnItem {item.id}.")

        # 3. Update the status of the sales return
        sales_return.status = SalesReturn.Status.COMPLETED
        sales_return.save(update_fields=['status', 'cogs_reversal_journal_entry'])
        logger.info(f"Successfully processed and completed SalesReturn {sales_return.id}.")



def create_credit_memo_from_return(sales_return: SalesReturn, memo_number: str, memo_date: str) -> CustomerCreditMemo:
    """
    Creates a CustomerCreditMemo from a SalesReturn, calculating the total
    credit amount from its items. This triggers the financial (AR) side of the return.

    Args:
        sales_return: The SalesReturn instance to create a credit memo for.
        memo_number: The unique number for the credit memo.
        memo_date: The date of the credit memo.

    Returns:
        The newly created CustomerCreditMemo instance.

    Raises:
        ValidationError: If the return has no items or a credit memo already exists.
    """
    logger.info(f"Attempting to create credit memo for SalesReturn ID {sales_return.id}.")

    return_content_type = ContentType.objects.get_for_model(sales_return)
    if CustomerCreditMemo.objects.filter(
        content_type=return_content_type, object_id=sales_return.id
    ).exists():
        raise ValidationError(_("A credit memo has already been created for this sales return."))

    return_items = sales_return.items.select_related(
        'original_dispatch__sales_order_item'
    ).all()

    if not return_items:
        raise ValidationError(_("This sales return has no items to credit."))

    total_base_amount = Decimal('0.0')
    total_vat_amount = Decimal('0.0')

    for item in return_items:
        so_item = item.original_dispatch.sales_order_item
        quantity_returned = Decimal(str(item.quantity_returned))
        
        base_price = so_item.base_price_per_unit
        vat_rate = so_item.vat_rate
        
        item_base_amount = quantity_returned * base_price
        item_vat_amount = item_base_amount * vat_rate
        
        total_base_amount += item_base_amount
        total_vat_amount += item_vat_amount

    with transaction.atomic():
        credit_memo = CustomerCreditMemo.objects.create(
            customer=sales_return.customer,
            memo_number=memo_number,
            memo_date=memo_date,
            base_amount=total_base_amount.quantize(Decimal('0.001')),
            vat_amount=total_vat_amount.quantize(Decimal('0.001')),
            source_object=sales_return,
            status=CustomerCreditMemo.Status.OPEN
        )
        # The post_save signal on CustomerCreditMemo will now create the JE.
        logger.info(f"Successfully created CustomerCreditMemo {credit_memo.id} for SalesReturn {sales_return.id}.")

    return credit_memo
