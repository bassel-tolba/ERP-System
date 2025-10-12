# gipcco_project/inventory/services/accounting/production_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    Batch, FinishedProductReceipt, ProductionReturn
)
from ..costing_service import get_inventory_state_at_datetime
from ._helpers import _check_period_is_open, _get_product_inventory_account

logger = logging.getLogger(__name__)


def create_je_for_production_consumption(batch: Batch) -> Optional[JournalEntry]:
    """
    Creates a journal entry for the consumption of raw materials into a production batch.
    This represents the transfer of value from Raw Materials to Work-in-Progress.

    Accounting Logic:
    - DEBIT: Work-in-Progress (WIP) Inventory Account
    - CREDIT: Raw Material Inventory Account(s) (one line per distinct account)
    """
    # 1. --- Pre-checks and Guards ---
    if not batch.items.exists():
        logger.warning(f"Attempted to create JE for Batch ID {batch.id} with no items. Aborting.")
        return None

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(batch),
        object_id=batch.id
    ).exists():
        logger.warning(f"Journal entry for Batch ID {batch.id} already exists. Aborting.")
        return None

    _check_period_is_open(batch.creation_date)

    # 2. --- Get Accounts and Calculate Amounts ---
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    if not wip_account:
        raise ValueError(_("Work-in-Progress (WIP) account is not configured in General Accounting Settings."))

    total_consumption_cost = Decimal('0.0')
    credits_by_account = {}  # {account_id: (total_amount, product_object)}

    for item in batch.items.all():
        if item.actual_quantity and item.actual_quantity > 0:
            cost_of_item = item.cost_at_consumption
            if cost_of_item is None:
                logger.warning(f"cost_at_consumption is None for BatchItem {item.id}. Calculating on the fly for JE creation.")
                state = get_inventory_state_at_datetime(item.primitive_product_id, batch.creation_date)
                mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
                cost_of_item = mac_at_consumption.quantize(Decimal('0.001'))
                
            line_cost = Decimal(str(item.actual_quantity)) * cost_of_item
            total_consumption_cost += line_cost
            
            inventory_account = _get_product_inventory_account(item.primitive_product)
            
            current_amount, _product = credits_by_account.get(inventory_account, (Decimal('0.0'), None))
            credits_by_account[inventory_account] = (current_amount + line_cost, item.primitive_product)

    if total_consumption_cost <= 0:
        logger.info(f"Total consumption cost for Batch ID {batch.id} is zero. No JE will be created.")
        return None
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Raw material consumption for SO: %(so)s / Batch: %(batch)s to produce '%(product)s'"
        ) % {
            'so': batch.shop_order_number,
            'batch': batch.batch_number,
            'product': batch.template.final_product.name,
        }

        je = JournalEntry.objects.create(
            date=batch.creation_date,
            description=description,
            source_object=batch,
            status=JournalEntry.Status.POSTED
        )

        # Line 1: Debit WIP Inventory
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=wip_account,
            amount=total_consumption_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=batch.template.final_product
        )

        # Line 2..N: Credit individual Raw Material Inventory accounts
        for account, (credit_amount, product_sub_ledger) in credits_by_account.items():
            if credit_amount > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=account,
                    amount=credit_amount.quantize(Decimal('0.001')),
                    entry_type=JournalEntryLine.EntryType.CREDIT,
                    sub_ledger_object=product_sub_ledger
                )
        
        je.validate_balance()
        logger.info(f"Successfully created Journal Entry JE-{je.id} for Batch ID {batch.id}.")
    
    return je


def create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a finished product receipt.
    This moves value from WIP Inventory to Finished Goods Inventory upon receipt.

    Accounting Logic:
    - DEBIT: Finished Goods Inventory
    - CREDIT: Work-in-Progress (WIP) Inventory
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(receipt),
        object_id=receipt.id
    ).exists():
        logger.warning(f"Journal entry for FinishedProductReceipt ID {receipt.id} already exists. Aborting.")
        return None

    _check_period_is_open(receipt.receipt_date)

    total_cost = receipt.total_cost
    final_product = receipt.batch.template.final_product
    if total_cost <= 0:
        logger.info(f"Total cost for receipt {receipt.id} is zero. No JE created.")
        return None
    
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory
    
    if not all([wip_account, fg_account]):
        raise ValueError(_("WIP or Finished Goods inventory account is not configured in General Settings."))

    with transaction.atomic():
        description = _(
            "Finished goods receipt for %(qty)s %(unit)s of '%(product)s' (Batch: %(batch)s)"
        ) % {
            'qty': receipt.total_quantity_produced,
            'unit': receipt.batch.template.final_product.unit,
            'product': receipt.batch.template.final_product.name,
            'batch': receipt.individual_batch_number,
        }

        je = JournalEntry.objects.create(
            date=receipt.receipt_date,
            description=description,
            source_object=receipt,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=total_cost, entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=final_product
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=total_cost, entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=final_product
        )

        je.validate_balance()
        logger.info(f"Successfully created Journal Entry JE-{je.id} for FinishedProductReceipt ID {receipt.id}.")
    return je


def create_je_for_production_return(prod_return: ProductionReturn) -> Optional[JournalEntry]:
    """
    Creates a JE for raw materials returned from production.
    Moves value from WIP back to Raw Material Inventory.
    
    Accounting Logic:
    - DEBIT: Raw Material Inventory
    - CREDIT: Work-in-Progress (WIP) Inventory
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(prod_return), object_id=prod_return.id
    ).exists():
        return None

    _check_period_is_open(prod_return.return_date)

    state = get_inventory_state_at_datetime(prod_return.product_id, prod_return.return_date)
    mac_before_return = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
    return_value = (Decimal(str(prod_return.quantity)) * mac_before_return).quantize(Decimal('0.001'))

    if return_value <= 0:
        logger.info(f"Return value for ProductionReturn ID {prod_return.id} is zero. No JE created.")
        return None
        
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    rm_account = _get_product_inventory_account(prod_return.product)

    with transaction.atomic():
        description = _(
            "Return of %(qty)s %(unit)s of '%(product)s' from production"
        ) % {
            'qty': prod_return.quantity,
            'unit': prod_return.product.unit,
            'product': prod_return.product.name,
        }
        je = JournalEntry.objects.create(
            date=prod_return.return_date, description=description, source_object=prod_return,
            status=JournalEntry.Status.POSTED
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=rm_account, amount=return_value, entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=prod_return.product
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=return_value, entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=prod_return.product
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for ProductionReturn ID {prod_return.id}.")
    return je
