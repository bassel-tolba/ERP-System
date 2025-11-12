# gipcco_project/inventory/services/accounting/production_transactions.py

import logging
from decimal import Decimal
from typing import Optional
from datetime import datetime
from django.utils import timezone

from django.utils.translation import gettext_lazy as _

from ...models import (
    JournalEntry, GeneralAccountingSettings,
    Batch, FinishedProductReceipt, ProductionReturn, BatchItem
)
from ..costing_service import get_inventory_state_at_datetime
from ._helpers import _get_product_inventory_account
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def create_je_for_production_consumption(batch: Batch) -> Optional[JournalEntry]:
    """
    Creates a journal entry for the consumption of raw materials into a production batch.
    This represents the transfer of value from Raw Materials to Work-in-Progress.
    """
    if not batch.items.exists():
        logger.warning(f"Attempted to create JE for Batch ID {batch.id} with no items. Aborting.")
        return None

    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    if not wip_account:
        raise ValueError(_("Work-in-Progress (WIP) account is not configured in General Accounting Settings."))

    total_consumption_cost = Decimal('0.0')
    credits_by_account = {}

    for item in batch.items.all():
        if item.actual_quantity and item.actual_quantity > 0:
            cost_of_item = item.cost_at_consumption
            if cost_of_item is None:
                logger.warning(f"cost_at_consumption is None for BatchItem {item.id}. Calculating on the fly for JE creation.")
                state = get_inventory_state_at_datetime(item.primitive_product_id, batch.creation_date)
                mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
                cost_of_item = mac_at_consumption.quantize(Decimal('0.001'))
                
            line_cost = item.actual_quantity * cost_of_item
            total_consumption_cost += line_cost
            
            inventory_account = _get_product_inventory_account(item.primitive_product)
            
            current_amount, _product = credits_by_account.get(inventory_account, (Decimal('0.0'), None))
            credits_by_account[inventory_account] = (current_amount + line_cost, item.primitive_product)

    description = _("Raw material consumption for SO: %(so)s / Batch: %(batch)s to produce '%(product)s'") % {
        'so': batch.shop_order_number,
        'batch': batch.batch_number,
        'product': batch.template.final_product.name,
    }

    builder = JournalEntryBuilder(source_object=batch)
    builder.set_description(description)
    builder.debit(total_consumption_cost.quantize(Decimal('0.001')), wip_account, sub_ledger_object=batch.template.final_product)

    for account, (credit_amount, product_sub_ledger) in credits_by_account.items():
        builder.credit(credit_amount.quantize(Decimal('0.001')), account, sub_ledger_object=product_sub_ledger)
    
    return builder.post()


def create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a finished product receipt.
    This moves value from WIP Inventory to Finished Goods Inventory upon receipt.
    """
    total_cost = receipt.total_cost
    final_product = receipt.batch.template.final_product
    
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory
    
    if not all([wip_account, fg_account]):
        raise ValueError(_("WIP or Finished Goods inventory account is not configured in General Settings."))

    description = _("Finished goods receipt for %(qty)s %(unit)s of '%(product)s' (Batch: %(batch)s)") % {
        'qty': receipt.total_quantity_produced,
        'unit': receipt.batch.template.final_product.unit,
        'product': receipt.batch.template.final_product.name,
        'batch': receipt.individual_batch_number,
    }

    builder = JournalEntryBuilder(source_object=receipt)
    builder.set_description(description)
    builder.debit(total_cost, fg_account, sub_ledger_object=final_product)
    builder.credit(total_cost, wip_account, sub_ledger_object=final_product)
    return builder.post()


def create_je_for_production_return(prod_return: ProductionReturn) -> Optional[JournalEntry]:
    """
    Creates a JE for raw materials returned from production.
    Moves value from WIP back to Raw Material Inventory.
    """
    state = get_inventory_state_at_datetime(prod_return.product_id, prod_return.return_date)
    mac_before_return = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
    # FIX: Convert quantity (float) to Decimal safely before multiplication
    return_value = (Decimal(str(prod_return.quantity)) * mac_before_return).quantize(Decimal('0.001'))
        
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    rm_account = _get_product_inventory_account(prod_return.product)

    description = _("Return of %(qty)s %(unit)s of '%(product)s' from production") % {
        'qty': prod_return.quantity,
        'unit': prod_return.product.unit,
        'product': prod_return.product.name,
    }

    builder = JournalEntryBuilder(source_object=prod_return)
    builder.set_description(description)
    builder.debit(return_value, rm_account, sub_ledger_object=prod_return.product)
    builder.credit(return_value, wip_account, sub_ledger_object=prod_return.product)
    return builder.post()


def create_je_for_production_supplemental_issue(item: 'BatchItem') -> Optional[JournalEntry]:
    """
    Creates a journal entry for a single supplemental item added to a production batch.
    This is a more granular version of production consumption for auditable corrections.
    """
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    if not wip_account:
        raise ValueError(_("Work-in-Progress (WIP) account is not configured in General Accounting Settings."))

    if not item.cost_at_consumption or item.cost_at_consumption <= 0:
        logger.error(f"Cannot create supplemental JE for BatchItem {item.id} because its cost is not set.")
        raise ValueError(f"Cost for supplemental item {item.primitive_product.name} has not been calculated and set.")

    line_cost = (item.actual_quantity * item.cost_at_consumption).quantize(Decimal('0.001'))
    inventory_account = _get_product_inventory_account(item.primitive_product)

    description = _("Supplemental issue of '%(product)s' to SO: %(so)s / Batch: %(batch)s") % {
        'product': item.primitive_product.name,
        'so': item.batch.shop_order_number,
        'batch': item.batch.batch_number,
    }

    builder = JournalEntryBuilder(source_object=item)
    builder.set_description(description)
    builder.debit(line_cost, wip_account, sub_ledger_object=item.batch.template.final_product)
    builder.credit(line_cost, inventory_account, sub_ledger_object=item.primitive_product)
    return builder.post()