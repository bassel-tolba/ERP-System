# gipcco_project/inventory/services/accounting_service.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ..models import (
    InventoryLog, JournalEntry, JournalEntryLine, FinancialPeriod,
    GeneralAccountingSettings, ProductTypeAccountingSettings, Product,
    Batch, InventoryConsumption, FinishedProductDispatch, FinishedProductReceipt, ProductionReturn
)
from ..services.costing_service import get_inventory_state_at_datetime

logger = logging.getLogger(__name__)


# --- Helper Functions ---

def _check_period_is_open(date_to_check):
    """Checks if the given date falls within an open financial period."""
    # Ensure we use the date part if a datetime is passed
    check_date = date_to_check.date() if hasattr(date_to_check, 'date') else date_to_check
    period = FinancialPeriod.objects.filter(
        start_date__lte=check_date,
        end_date__gte=check_date
    ).first()
    if period and period.is_closed:
        raise PermissionError(_(f"Financial period for date {check_date} is closed."))

def _get_product_inventory_account(product: Product) -> Product:
    """Gets the correct inventory account for a product, checking for overrides."""
    if product.override_inventory_account:
        return product.override_inventory_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.inventory_account:
        raise ValueError(_(f"No default inventory account is set for product type '{product.get_product_type_display()}'."))
    return setting.inventory_account

def _get_product_expense_account(product: Product) -> Product:
    """Gets the correct COGS/Expense account for a product, checking for overrides."""
    if product.override_cogs_expense_account:
        return product.override_cogs_expense_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.cogs_or_expense_account:
        raise ValueError(_(f"No default COGS/Expense account is set for product type '{product.get_product_type_display()}'."))
    return setting.cogs_or_expense_account

# --- NEW HELPER FUNCTION ---
def _get_product_revenue_account(product: Product) -> Product:
    """Gets the correct Sales Revenue account for a product, checking for overrides."""
    if product.override_sales_revenue_account:
        return product.override_sales_revenue_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.sales_revenue_account:
        raise ValueError(_(f"No default sales revenue account is set for product type '{product.get_product_type_display()}'."))
    return setting.sales_revenue_account

# --- Journal Entry Creation Services ---

def create_je_for_inventory_receipt(inventory_log: InventoryLog) -> Optional[JournalEntry]:
    """
    Creates a balanced, double-entry journal entry for a released inventory receipt.
    
    Accounting Logic:
    - DEBIT: Inventory Account (at costing value)
    - DEBIT: VAT Receivable (if VAT is recoverable)
    - CREDIT: Accounts Payable (for the total invoice amount)
    """
    # 1. --- Pre-checks and Guards ---
    if inventory_log.status != InventoryLog.Status.RELEASED:
        logger.debug(f"Attempted to create JE for non-released InventoryLog ID {inventory_log.id}. Status is '{inventory_log.status}'. Aborting.")
        return None
        
    if not inventory_log.release_timestamp:
        raise ValueError(_(f"Released InventoryLog ID {inventory_log.id} is missing a release_timestamp."))

    # Prevent creating duplicate journal entries
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(inventory_log),
        object_id=inventory_log.id
    ).exists():
        logger.debug(f"Journal entry for InventoryLog ID {inventory_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(inventory_log.release_timestamp)

    # 2. --- Get Accounts from Configuration ---
    settings = GeneralAccountingSettings.load()
    inventory_account = _get_product_inventory_account(inventory_log.product)
    ap_account = settings.accounts_payable
    vat_account = settings.vat_receivable
    
    if not all([inventory_account, ap_account, vat_account]):
        raise ValueError(_("One or more required general accounting settings are not configured."))

    # 3. --- Calculate Amounts ---
    quantity = Decimal(str(inventory_log.quantity))
    total_base_amount = inventory_log.base_unit_price * quantity
    vat_amount = inventory_log.vat_amount
    total_invoice_amount = total_base_amount + vat_amount
    costing_value = inventory_log.costing_unit_price * quantity
    
    # 4. --- Create Journal Entry and Lines within a Transaction ---
    with transaction.atomic():
        description = _(
            "Purchase receipt for %(quantity)s %(unit)s of '%(product)s' from %(supplier)s (QC: %(qc)s)"
        ) % {
            'quantity': inventory_log.quantity,
            'unit': inventory_log.product.unit,
            'product': inventory_log.product.name,
            'supplier': inventory_log.company.name if inventory_log.company else 'N/A',
            'qc': inventory_log.qc_no or 'N/A',
        }

        je = JournalEntry.objects.create(
            date=inventory_log.release_timestamp,
            description=description,
            source_object=inventory_log
        )
        
        # Line 1: Debit Inventory
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=inventory_account,
            amount=costing_value.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        
        # Line 2: Debit VAT Receivable (if applicable)
        if inventory_log.vat_treatment == InventoryLog.VatTreatment.RECOVERABLE and vat_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=vat_account,
                amount=vat_amount.quantize(Decimal('0.001')),
                entry_type=JournalEntryLine.EntryType.DEBIT
            )
        
        # Line 3: Credit Accounts Payable
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=ap_account,
            amount=total_invoice_amount.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.CREDIT
        )

        logger.info(f"Successfully created Journal Entry JE-{je.id} for InventoryLog ID {inventory_log.id}.")

    return je


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
    credits_by_account = {}  # {account_id: total_amount}

    for item in batch.items.all():
        if item.actual_quantity and item.actual_quantity > 0:
            # ====== START OF CORRECTION ======
            # If cost is missing (e.g., signal fired before costing service ran), calculate it now.
            cost_of_item = item.cost_at_consumption
            if cost_of_item is None:
                logger.warning(f"cost_at_consumption is None for BatchItem {item.id}. Calculating on the fly for JE creation.")
                state = get_inventory_state_at_datetime(item.primitive_product_id, batch.creation_date)
                mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
                cost_of_item = mac_at_consumption.quantize(Decimal('0.001'))
            # ====== END OF CORRECTION ======
                
            line_cost = Decimal(str(item.actual_quantity)) * cost_of_item
            total_consumption_cost += line_cost
            
            inventory_account = _get_product_inventory_account(item.primitive_product)
            credits_by_account[inventory_account] = credits_by_account.get(inventory_account, Decimal('0.0')) + line_cost

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
            source_object=batch
        )

        # Line 1: Debit WIP Inventory
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=wip_account,
            amount=total_consumption_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT
        )

        # Line 2..N: Credit individual Raw Material Inventory accounts
        for account, credit_amount in credits_by_account.items():
            if credit_amount > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=account,
                    amount=credit_amount.quantize(Decimal('0.001')),
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )
        
        logger.info(f"Successfully created Journal Entry JE-{je.id} for Batch ID {batch.id}.")
    
    return je


def create_je_for_internal_consumption(consumption: InventoryConsumption) -> Optional[JournalEntry]:
    """
    Creates a journal entry for the internal consumption of an MRO or Consumable item.
    
    Accounting Logic:
    - DEBIT: Expense Account (determined by product type or product override)
    - CREDIT: Inventory Account for the consumed item
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(consumption),
        object_id=consumption.id
    ).exists():
        logger.debug(f"Journal entry for InventoryConsumption ID {consumption.id} already exists. Aborting.")
        return None
        
    _check_period_is_open(consumption.consumption_date)

    # 2. --- Get Accounts and Amount ---
    total_cost = consumption.cost_at_consumption
    if total_cost <= 0:
        logger.info(f"Total consumption cost for InventoryConsumption ID {consumption.id} is zero. No JE created.")
        return None
        
    inventory_account = _get_product_inventory_account(consumption.product)
    expense_account = _get_product_expense_account(consumption.product)
    
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Internal consumption of %(quantity)s %(unit)s of '%(product)s' by %(dept)s"
        ) % {
            'quantity': consumption.quantity_consumed,
            'unit': consumption.product.unit,
            'product': consumption.product.name,
            'dept': consumption.get_department_display()
        }
        
        je = JournalEntry.objects.create(
            date=consumption.consumption_date,
            description=description,
            source_object=consumption
        )
        
        # Debit Expense Account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=expense_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        
        # Credit Inventory Account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=inventory_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        
        logger.info(f"Successfully created Journal Entry JE-{je.id} for InventoryConsumption ID {consumption.id}.")
        
    return je


def create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a released finished product receipt.
    This moves value from WIP Inventory to Finished Goods Inventory.

    Accounting Logic:
    - DEBIT: Finished Goods Inventory
    - CREDIT: Work-in-Progress (WIP) Inventory
    """
    # 1. --- Pre-checks and Guards ---
    if receipt.status != FinishedProductReceipt.Status.RELEASED:
        return None # Only create JEs for released goods

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(receipt),
        object_id=receipt.id
    ).exists():
        logger.warning(f"Journal entry for FinishedProductReceipt ID {receipt.id} already exists. Aborting.")
        return None

    _check_period_is_open(receipt.release_date or receipt.receipt_date)

    # 2. --- Get Accounts and Amount ---
    total_cost = receipt.total_cost
    if total_cost <= 0:
        logger.info(f"Total cost for receipt {receipt.id} is zero. No JE created.")
        return None
    
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory
    
    if not all([wip_account, fg_account]):
        raise ValueError(_("WIP or Finished Goods inventory account is not configured in General Settings."))

    # 3. --- Create Journal Entry and Lines ---
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
            date=receipt.release_date or receipt.receipt_date,
            description=description,
            source_object=receipt
        )

        # Debit Finished Goods Inventory
        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=total_cost, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Work-in-Progress Inventory
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=total_cost, entry_type=JournalEntryLine.EntryType.CREDIT
        )

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

    # Calculate the value of the return based on the Moving Average Cost just before the return
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
            date=prod_return.return_date, description=description, source_object=prod_return
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=rm_account, amount=return_value, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=return_value, entry_type=JournalEntryLine.EntryType.CREDIT
        )
        logger.info(f"Successfully created JE-{je.id} for ProductionReturn ID {prod_return.id}.")
    return je


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
            date=dispatch.dispatch_date, description=description, source_object=dispatch
        )
        # COGS Entry
        JournalEntryLine.objects.create(
            journal_entry=je, account=cogs_account, amount=cogs_amount, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=cogs_amount, entry_type=JournalEntryLine.EntryType.CREDIT
        )
        # Revenue Entry
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar_account, amount=total_receivable, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=revenue_account, amount=base_revenue, entry_type=JournalEntryLine.EntryType.CREDIT
        )
        if vat_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=vat_payable_account, amount=vat_amount, entry_type=JournalEntryLine.EntryType.CREDIT
            )
        logger.info(f"Successfully created JE-{je.id} for FinishedProductDispatch ID {dispatch.id}.")
    return je