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
    Batch, InventoryConsumption, FinishedProductDispatch, FinishedProductReceipt, ProductionReturn, Payment, BankTransfer, DepreciationLog, FixedAsset
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



def create_je_for_supplier_payment(payment: Payment) -> Optional[JournalEntry]:
    """
    Creates a journal entry when a payment is made to a supplier.

    Accounting Logic:
    - DEBIT: Accounts Payable (reducing the liability)
    - CREDIT: Bank/Cash Account (reducing the asset)
    """
    # 1. --- Pre-checks and Guards ---
    if payment.payment_type != Payment.PaymentType.PAYMENT_OUT or not payment.supplier:
        logger.debug(f"JE creation skipped for Payment ID {payment.id}: Not an outgoing supplier payment.")
        return None

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(payment), object_id=payment.id
    ).exists():
        logger.debug(f"Journal entry for Payment ID {payment.id} already exists. Aborting.")
        return None

    _check_period_is_open(payment.payment_date)
    
    # 2. --- Get Accounts ---
    settings = GeneralAccountingSettings.load()
    ap_account = settings.accounts_payable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ap_account, bank_gl_account]):
        raise ValueError(_("A/P account or the Bank's GL account is not configured."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Payment to supplier '%(supplier)s'. Ref: %(desc)s"
        ) % {
            'supplier': payment.supplier.name,
            'desc': payment.description
        }
        je = JournalEntry.objects.create(
            date=payment.payment_date, description=description, source_object=payment
        )

        # Debit Accounts Payable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Bank/Cash Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        logger.info(f"Successfully created JE-{je.id} for supplier Payment ID {payment.id}.")
    return je

def create_je_for_customer_payment(payment: Payment) -> Optional[JournalEntry]:
    """
    Creates a journal entry when a payment is received from a customer.

    Accounting Logic:
    - DEBIT: Bank/Cash Account (increasing the asset)
    - CREDIT: Accounts Receivable (reducing the asset)
    """
    # 1. --- Pre-checks and Guards ---
    if payment.payment_type != Payment.PaymentType.PAYMENT_IN or not payment.customer:
        logger.debug(f"JE creation skipped for Payment ID {payment.id}: Not an incoming customer payment.")
        return None

    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(payment), object_id=payment.id
    ).exists():
        logger.debug(f"Journal entry for Payment ID {payment.id} already exists. Aborting.")
        return None

    _check_period_is_open(payment.payment_date)
    
    # 2. --- Get Accounts ---
    settings = GeneralAccountingSettings.load()
    ar_account = settings.accounts_receivable
    bank_gl_account = payment.bank_account.gl_account

    if not all([ar_account, bank_gl_account]):
        raise ValueError(_("A/R account or the Bank's GL account is not configured."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Payment received from customer '%(customer)s'. Ref: %(desc)s"
        ) % {
            'customer': payment.customer.name,
            'desc': payment.description
        }
        je = JournalEntry.objects.create(
            date=payment.payment_date, description=description, source_object=payment
        )

        # Debit Bank/Cash Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Accounts Receivable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ar_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        logger.info(f"Successfully created JE-{je.id} for customer Payment ID {payment.id}.")
    return je


def create_je_for_bank_transfer(transfer: BankTransfer) -> Optional[JournalEntry]:
    """
    Creates a journal entry for an internal bank transfer.

    Accounting Logic:
    - DEBIT: Destination Bank/Cash GL Account (asset increases)
    - CREDIT: Source Bank/Cash GL Account (asset decreases)
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(transfer), object_id=transfer.id
    ).exists():
        logger.debug(f"Journal entry for BankTransfer ID {transfer.id} already exists. Aborting.")
        return None

    _check_period_is_open(transfer.transfer_date)
    
    source_gl = transfer.source_account.gl_account
    dest_gl = transfer.destination_account.gl_account

    if not all([source_gl, dest_gl]):
        raise ValueError(_("One of the bank accounts in the transfer is missing its GL account link."))

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=transfer.transfer_date,
            description=transfer.description,
            source_object=transfer
        )

        # Debit Destination
        JournalEntryLine.objects.create(
            journal_entry=je, account=dest_gl, amount=transfer.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Source
        JournalEntryLine.objects.create(
            journal_entry=je, account=source_gl, amount=transfer.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        logger.info(f"Successfully created JE-{je.id} for BankTransfer ID {transfer.id}.")
    return je

def create_je_for_monthly_depreciation(year: int, month: int) -> Optional[JournalEntry]:
    """
    Calculates and posts a single, consolidated journal entry for all eligible
    fixed assets for a given month.
    """
    from django.utils.timezone import datetime
    import calendar

    # 1. --- Pre-checks and Guards ---
    period_end_date = datetime(year, month, calendar.monthrange(year, month)[1]).date()
    _check_period_is_open(period_end_date)
    
    # Find assets that have already been depreciated for this period
    already_processed_assets = DepreciationLog.objects.filter(
        period_date=period_end_date
    ).values_list('asset_id', flat=True)
    
    # Find assets eligible for depreciation this month
    eligible_assets = FixedAsset.objects.filter(
        status=FixedAsset.AssetStatus.IN_SERVICE,
        depreciation_start_date__lte=period_end_date,
        useful_life_years__gt=0
    ).exclude(id__in=already_processed_assets)

    if not eligible_assets.exists():
        logger.info(f"No new assets to depreciate for {year}-{month:02d}.")
        return None
    
    # 2. --- Calculate Depreciation and Group by Account ---
    depreciation_details = []
    expense_totals = {}  # {account: total_amount}
    accumulated_totals = {} # {account: total_amount}

    for asset in eligible_assets:
        if asset.depreciable_base <= 0:
            continue
            
        monthly_depreciation = (asset.depreciable_base / (asset.useful_life_years * 12)).quantize(Decimal('0.001'))
        
        # Check if this month's depreciation exceeds the remaining value
        remaining_value = asset.depreciable_base - asset.accumulated_depreciation
        if remaining_value <= 0:
            continue # Already fully depreciated
        
        # Adjust the last depreciation amount to not overshoot
        final_amount = min(monthly_depreciation, remaining_value)
        if final_amount <= 0:
            continue

        depreciation_details.append({
            'asset': asset,
            'amount': final_amount
        })
        
        # Aggregate amounts for the journal entry
        expense_acc = asset.depreciation_expense_account
        accum_acc = asset.accumulated_depreciation_account
        expense_totals[expense_acc] = expense_totals.get(expense_acc, Decimal('0.000')) + final_amount
        accumulated_totals[accum_acc] = accumulated_totals.get(accum_acc, Decimal('0.000')) + final_amount

    if not depreciation_details:
        logger.info(f"No depreciation value to post for {year}-{month:02d}.")
        return None

    # 3. --- Create Journal Entry and Logs ---
    with transaction.atomic():
        description = _("Monthly depreciation for %(period)s") % {'period': period_end_date.strftime('%Y-%m')}
        je = JournalEntry.objects.create(
            date=period_end_date, description=description, source_object=None
        )

        # Debit Expense Accounts
        for account, total in expense_totals.items():
            JournalEntryLine.objects.create(
                journal_entry=je, account=account, amount=total, entry_type=JournalEntryLine.EntryType.DEBIT
            )
        
        # Credit Accumulated Depreciation Accounts
        for account, total in accumulated_totals.items():
            JournalEntryLine.objects.create(
                journal_entry=je, account=account, amount=total, entry_type=JournalEntryLine.EntryType.CREDIT
            )

        # Create the log records to prevent re-running
        logs_to_create = [
            DepreciationLog(
                asset=detail['asset'],
                period_date=period_end_date,
                amount=detail['amount'],
                journal_entry=je
            ) for detail in depreciation_details
        ]
        DepreciationLog.objects.bulk_create(logs_to_create)

        logger.info(f"Successfully created JE-{je.id} for monthly depreciation.")
    return je