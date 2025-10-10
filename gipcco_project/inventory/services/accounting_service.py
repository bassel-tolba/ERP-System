# gipcco_project/inventory/services/accounting_service.py

import logging
import calendar
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError

from ..models import (
    InventoryLog, JournalEntry, JournalEntryLine, FinancialPeriod,
    GeneralAccountingSettings, ProductTypeAccountingSettings, Product,
    Batch, InventoryConsumption, FinishedProductDispatch, FinishedProductReceipt, ProductionReturn, Payment, BankTransfer, DepreciationLog, FixedAsset, FiscalYear,
    InventoryAdjustment, EmployeeAdvance, OverheadAllocationRun, CostPool, ExpenseLog, Account, TransactionCorrection,
    PeriodCloseChecklist, OpeningBalanceEntry, OpeningBalanceEntryLine,
    # --- NEW IMPORTS ---
    PrepaidExpense, AmortizationLog, AccrualLog, ExpenseRequest, EmployeeAdvanceSettlement
)
from ..services.costing_service import get_inventory_state_at_datetime

logger = logging.getLogger(__name__)


# --- Helper Functions ---

def _check_period_is_open(date_to_check):
    """
    Checks if the given date falls within an open financial period.
    This is the authoritative gatekeeper for all financially relevant transactions.
    It raises a PermissionError if the period is closed or locked.
    """
    # Ensure we use the date part if a datetime is passed
    check_date = date_to_check.date() if hasattr(date_to_check, 'date') else date_to_check
    try:
        period = FinancialPeriod.objects.get(
            start_date__lte=check_date,
            end_date__gte=check_date
        )
        if period.status in [FinancialPeriod.Status.CLOSED, FinancialPeriod.Status.PERMANENTLY_LOCKED]:
            raise PermissionError(
                _(f"Financial period '{period.name}' for date {check_date} is {period.get_status_display()} and cannot be posted to.")
            )
    except FinancialPeriod.DoesNotExist:
        raise PermissionError(_(f"No financial period found for date {check_date}. Please create one."))
    except FinancialPeriod.MultipleObjectsReturned:
        # This indicates a serious data integrity issue that must be resolved.
        logger.error(f"CRITICAL: Overlapping financial periods found for date {check_date}.")
        raise PermissionError(_(f"Configuration error: Overlapping financial periods exist for date {check_date}. Contact administrator."))


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

def create_je_for_inventory_adjustment(adjustment: InventoryAdjustment) -> Optional[JournalEntry]:
    """
    Creates a journal entry for an inventory adjustment.

    Accounting Logic for Shortage (negative quantity):
    - DEBIT: Inventory Adjustment Loss Account
    - CREDIT: Inventory Account

    Accounting Logic for Overage (positive quantity):
    - DEBIT: Inventory Account
    - CREDIT: Inventory Adjustment Gain Account
    """
    logger.info(f"--> Entered 'create_je_for_inventory_adjustment' for Adjustment ID {adjustment.id}.")
    
    # Check for existing JE
    existing_je_check = JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(adjustment), object_id=adjustment.id
    )
    if existing_je_check.exists():
        logger.warning(f"    [CHECK FAILED] Journal entry for InventoryAdjustment ID {adjustment.id} already exists (JE ID: {existing_je_check.first().id}). Aborting.")
        return None
    logger.info("    [CHECK PASSED] No existing journal entry found.")

    logger.info(f"    Checking financial period for adjustment date: {adjustment.adjustment_date}.")
    try:
        _check_period_is_open(adjustment.adjustment_date)
        logger.info("    [CHECK PASSED] Financial period is open.")
    except Exception as e:
        logger.error(f"    [CHECK FAILED] Financial period check failed: {e}", exc_info=True)
        raise e # Re-raise the exception to see it in the console

    settings = GeneralAccountingSettings.load()
    inventory_account = _get_product_inventory_account(adjustment.product)

    # Determine the correct loss/expense account based on the reason
    if adjustment.reason_code == InventoryAdjustment.ReasonCode.DAMAGE:
        loss_account = settings.damaged_goods_expense_account
    else: # Default to the general shrinkage/loss account for other reasons
        loss_account = settings.inventory_adjustment_loss_account
    gain_account = settings.inventory_adjustment_gain_account
    
    logger.info(f"    Accounts determined: Inventory='{inventory_account}', Loss='{loss_account}', Gain='{gain_account}'.")

    if not all([inventory_account, loss_account, gain_account]):
        logger.error(f"    [CHECK FAILED] Failed to create JE for adjustment {adjustment.id}: Critical accounts are not configured in GeneralAccountingSettings.")
        raise ValueError(_("Inventory, Loss, or Gain account for adjustments is not configured in General Settings."))
    logger.info("    [CHECK PASSED] All required accounting settings are configured.")

    adjustment_value = abs(Decimal(str(adjustment.adjustment_quantity)) * adjustment.cost_at_adjustment)
    logger.info(f"    Calculated adjustment value: {adjustment_value} (Qty: {adjustment.adjustment_quantity}, Cost: {adjustment.cost_at_adjustment})")
    
    # --- MODIFICATION BASED ON USER FEEDBACK ---
    # The check for zero-value adjustments has been removed. The system will now create
    # journal entries with a value of zero if the cost_at_adjustment results in it.
    # This is to allow for specific business cases where recording a zero-value transaction is required.
    
    with transaction.atomic():
        description = _(
            "Inventory adjustment for '%(product)s' due to %(reason)s"
        ) % {
            'product': adjustment.product.name,
            'reason': adjustment.get_reason_code_display()
        }
        logger.info(f"    Creating JournalEntry with description: \"{description}\"")
        je = JournalEntry.objects.create(
            date=adjustment.adjustment_date,
            description=description,
            source_object=adjustment,
            status=JournalEntry.Status.POSTED
        )

        if adjustment.adjustment_quantity < 0: # Shortage
            logger.info(f"    Processing shortage: DEBIT '{loss_account.name}', CREDIT '{inventory_account.name}' with {adjustment_value}.")
            JournalEntryLine.objects.create(
                journal_entry=je, account=loss_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT
            )
            JournalEntryLine.objects.create(
                journal_entry=je, account=inventory_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT,
                sub_ledger_object=adjustment.product
            )
        else: # Overage
            logger.info(f"    Processing overage: DEBIT '{inventory_account.name}', CREDIT '{gain_account.name}' with {adjustment_value}.")
            JournalEntryLine.objects.create(
                journal_entry=je, account=inventory_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT,
                sub_ledger_object=adjustment.product
            )
            JournalEntryLine.objects.create(
                journal_entry=je, account=gain_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT
            )
        
        je.validate_balance()
        logger.info(f"    Successfully created JE-{je.id} for InventoryAdjustment ID {adjustment.id}.")
        logger.info(f"<-- Exiting 'create_je_for_inventory_adjustment' for Adjustment ID {adjustment.id}.")
    return je


def create_je_for_inventory_receipt(inventory_log: InventoryLog) -> Optional[JournalEntry]:
    """
    Creates a balanced, double-entry journal entry for a released inventory receipt.
    
    Accounting Logic:
    - DEBIT: Inventory Account (at costing value)
    - DEBIT: VAT Receivable (if VAT is recoverable)
    - CREDIT: Accounts Payable (for the total invoice amount MINUS withholding tax)
    - CREDIT: Withholding Tax Payable
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
    wht_account = settings.withholding_tax_payable
    
    if not all([inventory_account, ap_account, vat_account, wht_account]):
        raise ValueError(_("One or more required general accounting settings are not configured."))

    # 3. --- Calculate Amounts ---
    quantity = Decimal(str(inventory_log.quantity))
    total_base_amount = inventory_log.base_unit_price * quantity
    vat_amount = inventory_log.vat_amount
    wht_amount = inventory_log.withholding_tax_amount
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
            source_object=inventory_log,
            status=JournalEntry.Status.POSTED
        )
        
        # Line 1: Debit Inventory
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=inventory_account,
            amount=costing_value.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=inventory_log.product
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
            amount=(total_invoice_amount - wht_amount).quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=inventory_log.company
        )

        # Line 4: Credit Withholding Tax Payable (if applicable)
        if wht_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=wht_account,
                amount=wht_amount.quantize(Decimal('0.001')),
                entry_type=JournalEntryLine.EntryType.CREDIT
            )

        je.validate_balance()
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
    credits_by_account = {}  # {account_id: (total_amount, product_object)}

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
            
            # Store amount and the product for sub-ledger linking
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


def create_je_for_internal_consumption(consumption: InventoryConsumption) -> Optional[JournalEntry]:
    """
    Creates a journal entry for the internal consumption of an MRO or Consumable item.
    
    Accounting Logic (Expense):
    - DEBIT: Expense Account (determined by product type or product override)
    - CREDIT: Inventory Account for the consumed item

    Accounting Logic (Capitalize):
    - DEBIT: Fixed Asset's GL Control Account
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
    
    # --- MODIFIED: Determine the debit account based on consumption type ---
    if consumption.consumption_type == InventoryConsumption.ConsumptionType.CAPITALIZE:
        if not consumption.fixed_asset:
            raise ValueError(_("Cannot create capitalization JE for consumption without a linked Fixed Asset."))
        debit_account = consumption.fixed_asset.gl_account
        debit_sub_ledger = consumption.fixed_asset
    # --- NEW: Handle creation of a prepaid asset from an amortizable item ---
    elif consumption.consumption_type == InventoryConsumption.ConsumptionType.AMORTIZE:
        # The debit is to the universal Prepaid Expenses account.
        settings = GeneralAccountingSettings.load()
        if not settings.prepaid_expenses_account:
            raise ValueError(_("The master Prepaid Expenses account is not configured in General Accounting Settings."))
        debit_account = settings.prepaid_expenses_account
        debit_sub_ledger = None # The sub-ledger will be the PrepaidExpense object itself, linked later.
    else: # Default to EXPENSE
        debit_account = _get_product_expense_account(consumption.product)
        debit_sub_ledger = None # Expenses don't typically have a sub-ledger here

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
            source_object=consumption,
            status=JournalEntry.Status.POSTED
        )
        
        # Debit Expense or Asset Account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=debit_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=debit_sub_ledger
        )
        
        # Credit Inventory Account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=inventory_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=consumption.product
        )
        
        je.validate_balance()
        logger.info(f"Successfully created Journal Entry JE-{je.id} for InventoryConsumption ID {consumption.id}.")
        
    return je


def create_je_for_finished_goods_receipt(receipt: FinishedProductReceipt) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a finished product receipt.
    This moves value from WIP Inventory to Finished Goods Inventory upon receipt.

    Accounting Logic:
    - DEBIT: Finished Goods Inventory
    - CREDIT: Work-in-Progress (WIP) Inventory
    """
    # 1. --- Pre-checks and Guards ---
    # JE is now created upon receipt, regardless of quarantine status.
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(receipt),
        object_id=receipt.id
    ).exists():
        logger.warning(f"Journal entry for FinishedProductReceipt ID {receipt.id} already exists. Aborting.")
        return None

    _check_period_is_open(receipt.receipt_date)

    # 2. --- Get Accounts and Amount ---
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
            date=receipt.receipt_date,
            description=description,
            source_object=receipt,
            status=JournalEntry.Status.POSTED
        )

        # Debit Finished Goods Inventory
        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=total_cost, entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=final_product
        )
        # Credit Work-in-Progress Inventory
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
            date=payment.payment_date, description=description, source_object=payment,
            status=JournalEntry.Status.POSTED
        )

        # Debit Accounts Payable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=payment.supplier
        )
        # Credit Bank/Cash Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=payment.bank_account
        )
        je.validate_balance()
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
    # Check if this is an on-account payment (no invoice applications)
    is_on_account = not payment.customer_applications.exists()

    with transaction.atomic():
        description = _(
            "Payment received from customer '%(customer)s'. Ref: %(desc)s"
        ) % {
            'customer': payment.customer.name,
            'desc': payment.description
        }
        je = JournalEntry.objects.create(
            date=payment.payment_date, description=description, source_object=payment,
            status=JournalEntry.Status.POSTED
        )

        # Debit Bank/Cash Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=payment.bank_account
        )
        # --- MODIFIED LOGIC FOR CREDIT ---
        if is_on_account:
            # Credit Customer Deposits (Liability)
            credit_account = settings.customer_deposits_account
            if not credit_account:
                raise ValueError(_("Customer Deposits account not configured in General Settings."))
        else:
            # Credit Accounts Receivable (as before)
            credit_account = settings.accounts_receivable
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=credit_account,
            amount=payment.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=payment.customer
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for customer Payment ID {payment.id}.")
    return je


def create_je_for_employee_advance(advance: EmployeeAdvance) -> Optional[JournalEntry]:
    """
    Creates a journal entry when funds are advanced to an employee.

    Accounting Logic:
    - DEBIT: Employee Advances Receivable (an asset, representing money owed to the company)
    - CREDIT: Bank/Cash Account (the source of the funds)
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(advance), object_id=advance.id
    ).exists():
        logger.debug(f"Journal entry for EmployeeAdvance ID {advance.id} already exists. Aborting.")
        return None

    _check_period_is_open(advance.advance_date)
    
    # 2. --- Get Accounts ---
    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    bank_gl_account = advance.source_payment.bank_account.gl_account

    if not all([employee_advances_account, bank_gl_account]):
        raise ValueError(_("The Employee Advances Receivable account or the source Bank's GL account is not configured in General Settings."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Advance of %(amount)s to employee '%(employee)s'"
        ) % {
            'amount': advance.amount,
            'employee': advance.employee.full_name
        }
        je = JournalEntry.objects.create(
            date=advance.advance_date, description=description, source_object=advance,
            status=JournalEntry.Status.POSTED
        )

        # Debit Employee Advances Receivable
        JournalEntryLine.objects.create(
            journal_entry=je, account=employee_advances_account, amount=advance.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=advance.employee
        )
        # Credit Bank/Cash Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=bank_gl_account, amount=advance.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=advance.source_payment.bank_account
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for EmployeeAdvance ID {advance.id}.")
    return je

def create_je_for_employee_advance_settlement(settlement: EmployeeAdvanceSettlement) -> Optional[JournalEntry]:
    """
    Creates a journal entry when an employee advance is settled.
    The settlement source is determined via a GenericForeignKey (`source_transaction`).

    - If the source is an ExpenseLog, it moves value from 'Accrued Expenses'
      to 'Employee Advances Receivable'.
    - If the source is None, it implies a direct repayment and moves value
      from the default cash account to 'Employee Advances Receivable'.
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(settlement), object_id=settlement.id
    ).exists():
        logger.debug(f"Journal entry for EmployeeAdvanceSettlement ID {settlement.id} already exists. Aborting.")
        return None

    _check_period_is_open(settlement.settlement_date)

    # 2. --- Get Accounts ---
    settings = GeneralAccountingSettings.load()
    employee_advances_account = settings.employee_advances_receivable
    if not employee_advances_account:
        raise ValueError(_("The Employee Advances Receivable account is not configured in General Settings."))

    # 3. --- Determine Settlement Type and Prepare JE Details ---
    description = ""
    debit_account = None
    source = settlement.source_transaction # <-- CORRECTED: Use source_transaction instead of source_object

    if isinstance(source, ExpenseLog):
        # Case 1: Settlement via an Expense Log
        debit_account = settings.accrued_expenses_account
        if not debit_account:
            raise ValueError(_("The Accrued Expenses account is not configured in General Settings for expense-based settlement."))
        
        description = _(
            "Settlement of advance for '%(employee)s' with expense log #%(log_id)s"
        ) % {
            'employee': settlement.advance.employee.full_name,
            'log_id': source.id
        }
    else:
        # Case 2: Direct repayment (source is None or another type like Payment)
        debit_account = settings.default_cash_account
        if not debit_account:
            raise ValueError(_("The Default Cash Account is not configured in General Settings for direct advance repayment."))

        description = _(
            "Direct repayment of advance for '%(employee)s'"
        ) % {
            'employee': settlement.advance.employee.full_name
        }

    # 4. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=settlement.settlement_date, description=description, source_object=settlement,
            status=JournalEntry.Status.POSTED
        )

        # Debit the determined account
        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=settlement.amount_settled, # <-- CORRECTED: Use amount_settled
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Employee Advances Receivable
        JournalEntryLine.objects.create(
            journal_entry=je, account=employee_advances_account, amount=settlement.amount_settled, # <-- CORRECTED: Use amount_settled
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=settlement.advance.employee
        )

        je.validate_balance()
        # Link the JE back to the settlement for traceability
        settlement.journal_entry = je
        settlement.save(update_fields=['journal_entry'])

        logger.info(f"Successfully created JE-{je.id} for EmployeeAdvanceSettlement ID {settlement.id}.")
    return je


def create_je_for_overhead_allocation(run: OverheadAllocationRun) -> Optional[JournalEntry]:
    """
    Creates a consolidated journal entry for an overhead allocation run.

    --- CORRECTED ACCOUNTING LOGIC ---
    - DEBIT: Work-in-Progress (WIP) Inventory Account (for the total allocated amount)
    - CREDIT: Each individual Expense Account that contributed to the cost pool,
              effectively clearing them out and transferring their value to WIP.
    """
    # 1. --- Pre-checks and Guards ---
    if run.status != OverheadAllocationRun.Status.CALCULATED:
        logger.warning(f"Attempted to post JE for allocation run {run.id} which has not been calculated. Status is '{run.status}'.")
        return None
    
    if run.journal_entry:
        logger.warning(f"Journal entry for allocation run {run.id} already exists (JE ID: {run.journal_entry.id}). Aborting.")
        return None

    period = run.financial_period
    _check_period_is_open(period.end_date)

    # 2. --- Get Accounts and Amounts ---
    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    if not wip_account:
        raise ValueError(_("Work-in-Progress (WIP) account is not configured in General Accounting Settings."))

    # Find all descendant pools to gather all relevant expenses
    all_pools = [run.cost_pool]
    descendants = run.cost_pool.children.all()
    while descendants:
        all_pools.extend(descendants)
        descendants = CostPool.objects.filter(parent__in=descendants)

    # --- NEW: Aggregate expenses by their cost pool to map to GL accounts ---
    expenses_in_pool = ExpenseLog.objects.filter(
        expense_date__gte=period.start_date,
        expense_date__lte=period.end_date,
        cost_pool__in=all_pools
    ).select_related('cost_pool__gl_account')
    
    credits_by_account = {}
    for expense in expenses_in_pool:
        # The account to credit is now directly on the cost pool
        account_to_credit = expense.cost_pool.gl_account
        if account_to_credit:
            # Aggregate the amounts per account
            credits_by_account[account_to_credit] = credits_by_account.get(account_to_credit, Decimal('0.0')) + expense.amount
        else:
            # If a mapping is missing on a cost pool that has expenses, we cannot create a balanced entry.
            raise ValueError(
                _("Accounting configuration error: The cost pool '%(pool_name)s' has expenses logged against it but is not mapped to a GL account. Please configure it in the Cost Pool Management page.")
                % {'pool_name': expense.cost_pool.name}
            )

    total_allocated_amount = run.total_pool_amount
    if total_allocated_amount <= 0:
        logger.info(f"Total allocated amount for run {run.id} is zero. No JE will be created.")
        run.status = OverheadAllocationRun.Status.POSTED # Mark as posted even if zero
        run.save()
        return None

    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Allocation of %(pool_name)s overhead for period %(period_name)s"
        ) % {
            'pool_name': run.cost_pool.name,
            'period_name': period.name
        }
        je = JournalEntry.objects.create(
            date=period.end_date,
            description=description,
            source_object=run,
            status=JournalEntry.Status.POSTED
        )

        # Debit WIP Inventory for the total amount
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=wip_account,
            amount=total_allocated_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )

        # --- NEW: Create individual credit lines for each cleared expense account ---
        for account, credit_amount in credits_by_account.items():
            if credit_amount > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=account,
                    amount=credit_amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )
        
        je.validate_balance()
        # Link the JE back to the run and update status
        run.journal_entry = je
        run.status = OverheadAllocationRun.Status.POSTED
        run.posted_at = timezone.now()
        run.save()

        logger.info(f"Successfully created JE-{je.id} for Overhead Allocation Run ID {run.id}.")
    return je


def create_je_for_overhead_application(run: OverheadAllocationRun, total_applied_cost: Decimal) -> Optional[JournalEntry]:
    """
    Creates the second journal entry in the overhead process, which moves the
    applied overhead cost from WIP to Finished Goods inventory.

    Accounting Logic:
    - DEBIT: Finished Goods Inventory
    - CREDIT: Work-in-Progress (WIP) Inventory
    """
    if run.status != OverheadAllocationRun.Status.POSTED:
        raise ValueError("Cannot create application JE for a run that is not in 'Posted' status.")
    if run.application_journal_entry:
        logger.warning(f"Application JE for run {run.id} already exists. Aborting.")
        return None
    if total_applied_cost <= 0:
        logger.info(f"Total applied overhead for run {run.id} is zero. No application JE will be created.")
        # Even if the JE is zero, we mark the run as APPLIED to complete the workflow.
        run.status = OverheadAllocationRun.Status.APPLIED
        run.save()
        return None

    period = run.financial_period
    _check_period_is_open(period.end_date)

    settings = GeneralAccountingSettings.load()
    wip_account = settings.wip_inventory
    fg_account = settings.finished_goods_inventory

    if not all([wip_account, fg_account]):
        raise ValueError("WIP or Finished Goods inventory account is not configured in General Settings.")

    with transaction.atomic():
        description = _(
            "Application of %(pool_name)s overhead to Finished Goods for period %(period_name)s"
        ) % {
            'pool_name': run.cost_pool.name,
            'period_name': period.name
        }
        je = JournalEntry.objects.create(
            date=period.end_date,
            description=description,
            source_object=run,
            status=JournalEntry.Status.POSTED
        )

        # Debit Finished Goods Inventory
        JournalEntryLine.objects.create(
            journal_entry=je, account=fg_account, amount=total_applied_cost, entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Work-in-Progress Inventory
        JournalEntryLine.objects.create(
            journal_entry=je, account=wip_account, amount=total_applied_cost, entry_type=JournalEntryLine.EntryType.CREDIT
        )

        je.validate_balance()
        # Link this new JE to the run and update the final status
        run.application_journal_entry = je
        run.status = OverheadAllocationRun.Status.APPLIED
        run.save()

        logger.info(f"Successfully created Application JE-{je.id} for Overhead Allocation Run ID {run.id}.")
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
            source_object=transfer,
            status=JournalEntry.Status.POSTED
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
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for BankTransfer ID {transfer.id}.")
    return je


# --- NEW SERVICE FUNCTION FOR DEPRECIATION ---
def create_je_for_depreciation(depreciation_log: DepreciationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly depreciation log.

    Accounting Logic:
    - DEBIT: Depreciation Expense Account (from the asset)
    - CREDIT: Accumulated Depreciation Account (from the asset)
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(depreciation_log), object_id=depreciation_log.id
    ).exists():
        logger.debug(f"Journal entry for DepreciationLog ID {depreciation_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(depreciation_log.period_date)
    
    # 2. --- Get Accounts and Amount ---
    asset = depreciation_log.asset
    depreciation_amount = depreciation_log.amount
    
    expense_account = asset.depreciation_expense_account
    accumulated_dep_account = asset.accumulated_depreciation_account

    if not all([expense_account, accumulated_dep_account]):
        raise ValueError(_(f"The fixed asset '{asset.name}' is missing its depreciation or accumulated depreciation account configuration."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Monthly depreciation for asset '%(asset_name)s' (%(asset_tag)s)"
        ) % {
            'asset_name': asset.name,
            'asset_tag': asset.asset_tag
        }
        je = JournalEntry.objects.create(
            date=depreciation_log.period_date,
            description=description,
            source_object=depreciation_log,
            status=JournalEntry.Status.POSTED
        )

        # Debit Depreciation Expense
        JournalEntryLine.objects.create(
            journal_entry=je, account=expense_account, amount=depreciation_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=asset
        )
        # Credit Accumulated Depreciation
        JournalEntryLine.objects.create(
            journal_entry=je, account=accumulated_dep_account, amount=depreciation_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=asset
        )
        
        je.validate_balance()
        # Link the JE back to the log for traceability
        depreciation_log.journal_entry = je
        depreciation_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for DepreciationLog ID {depreciation_log.id}.")
    return je


# --- NEW SERVICE FUNCTIONS FOR ADJUSTING ENTRIES ---

def create_je_for_amortization(amortization_log: AmortizationLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly prepaid expense amortization.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the PrepaidExpense record.
    - CREDIT: The master Prepaid Expenses control account.
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(amortization_log), object_id=amortization_log.id
    ).exists():
        logger.debug(f"Journal entry for AmortizationLog ID {amortization_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(amortization_log.financial_period.end_date)
    
    # 2. --- Get Accounts and Amount ---
    prepaid = amortization_log.prepaid_expense
    amortization_amount = amortization_log.amount
    
    debit_account = prepaid.expense_account
    
    settings = GeneralAccountingSettings.load()
    credit_account = settings.prepaid_expenses_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The prepaid expense '{prepaid}' is missing its target expense account or the master prepaid account is not set."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Monthly amortization for: %(prepaid_desc)s"
        ) % {
            'prepaid_desc': str(prepaid)
        }
        je = JournalEntry.objects.create(
            date=amortization_log.financial_period.end_date,
            description=description,
            source_object=amortization_log,
            status=JournalEntry.Status.POSTED
        )

        # Debit Expense Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=amortization_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Prepaid Expenses Control Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=credit_account, amount=amortization_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=prepaid
        )
        
        je.validate_balance()
        # Link the JE back to the log for traceability
        amortization_log.journal_entry = je
        amortization_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for AmortizationLog ID {amortization_log.id}.")
    return je


def create_je_for_accrual(accrual_log: AccrualLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a monthly expense accrual.

    Accounting Logic:
    - DEBIT: The specific expense account defined on the AccruedExpense record.
    - CREDIT: The specific accrued liability account defined on the AccruedExpense record.
    """
    # 1. --- Pre-checks and Guards ---
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(accrual_log), object_id=accrual_log.id
    ).exists():
        logger.debug(f"Journal entry for AccrualLog ID {accrual_log.id} already exists. Aborting.")
        return None

    _check_period_is_open(accrual_log.financial_period.end_date)
    
    # 2. --- Get Accounts and Amount ---
    accrual = accrual_log.accrued_expense
    accrual_amount = accrual_log.amount
    
    debit_account = accrual.target_expense_account
    credit_account = accrual.target_liability_account

    if not all([debit_account, credit_account]):
        raise ValueError(_(f"The accrued expense '{accrual.description}' is missing its target expense or liability account configuration."))
        
    # 3. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Monthly expense accrual for: %(accrual_desc)s"
        ) % {
            'accrual_desc': accrual.description
        }
        je = JournalEntry.objects.create(
            date=accrual_log.financial_period.end_date,
            description=description,
            source_object=accrual_log,
            status=JournalEntry.Status.POSTED
        )

        # Debit Expense Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=debit_account, amount=accrual_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Accrued Liability Account
        JournalEntryLine.objects.create(
            journal_entry=je, account=credit_account, amount=accrual_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=accrual
        )
        
        je.validate_balance()
        # Link the JE back to the log for traceability
        accrual_log.journal_entry = je
        accrual_log.save(update_fields=['journal_entry'])
        
        logger.info(f"Successfully created JE-{je.id} for AccrualLog ID {accrual_log.id}.")
    return je


def create_je_for_expense_log(expense_log: 'ExpenseLog'):
    """
    Creates a journal entry for a direct expense that is being accrued.
    Debits the expense account linked to the cost pool and credits Accrued Expenses.
    """
    _check_period_is_open(expense_log.expense_date)

    settings = GeneralAccountingSettings.load()
    if not expense_log.cost_pool or not expense_log.cost_pool.gl_account:
        raise ValidationError(f"ExpenseLog #{expense_log.id} is missing a cost pool with a linked GL account.")
    if not settings.accrued_expenses_account:
        raise ValidationError("The Accrued Expenses liability account is not configured in General Accounting Settings.")

    debit_account = expense_log.cost_pool.gl_account
    credit_account = settings.accrued_expenses_account

    je = JournalEntry.objects.create(
        date=expense_log.expense_date,
        description=f"Direct expense: {expense_log.description}",
        source_object=expense_log,
        status=JournalEntry.Status.POSTED
    )

    JournalEntryLine.objects.create(
        journal_entry=je,
        account=debit_account,
        amount=expense_log.amount,
        entry_type=JournalEntryLine.EntryType.DEBIT
    )
    JournalEntryLine.objects.create(
        journal_entry=je,
        account=credit_account,
        amount=expense_log.amount,
        entry_type=JournalEntryLine.EntryType.CREDIT
    )
    je.validate_balance()


def create_transaction_for_direct_payment_expense(request: 'ExpenseRequest') -> 'ExpenseLog':
    """
    Creates an ExpenseLog and a direct payment Journal Entry for an approved
    direct expense request. This bypasses the standard accrual process.

    Accounting Logic:
    - DEBIT: Expense Account (from the request's Cost Pool)
    - CREDIT: Bank/Cash Account (from the request's Bank Account)
    """
    _check_period_is_open(request.request_date)

    if not request.cost_pool or not request.cost_pool.gl_account:
        raise ValidationError(f"ExpenseRequest #{request.id} is missing a cost pool with a linked GL account.")
    if not request.bank_account or not request.bank_account.gl_account:
        raise ValidationError(f"ExpenseRequest #{request.id} is missing a bank account with a linked GL account.")

    debit_account = request.cost_pool.gl_account
    credit_account = request.bank_account.gl_account

    with transaction.atomic():
        # First, create the ExpenseLog for tracking purposes.
        # We add a flag to prevent the post_save signal from creating a duplicate JE.
        expense_log = ExpenseLog(
            description=request.description,
            expense_date=request.request_date,
            amount=request.amount,
            category=request.category,
            classification=request.classification,
            cost_pool=request.cost_pool,
            source_request=request,
            settlement_status=ExpenseLog.SettlementStatus.SETTLED
        )
        expense_log._skip_je_creation = True  # Set the flag
        expense_log.save()

        # Now, create the correct journal entry for a direct payment.
        je = JournalEntry.objects.create(
            date=request.request_date,
            description=f"Direct expense payment: {request.description}",
            source_object=expense_log, # Link JE to the ExpenseLog
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je,
            account=debit_account,
            amount=request.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=credit_account,
            amount=request.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=request.bank_account
        )

        je.validate_balance()
        # Link the JE to the expense log as the settlement object
        expense_log.settlement_object = je
        expense_log.save(update_fields=['settlement_content_type', 'settlement_object_id'])

    return expense_log


def create_je_for_opening_balance(ob_entry: 'OpeningBalanceEntry') -> JournalEntry:
    """
    Creates a single, multi-line journal entry from an Opening Balance Entry record.

    Iterates through all lines and sub-ledger details of an OpeningBalanceEntry
    and creates a single, balanced JournalEntry. This is the financial posting
    step of the migration process.
    """
    logger.info(f"--> Starting Opening Balance JE creation for '{ob_entry.name}'.")
    
    if ob_entry.status == OpeningBalanceEntry.Status.POSTED:
        raise PermissionError(_("This opening balance entry has already been posted."))
    
    _check_period_is_open(ob_entry.migration_date)

    with transaction.atomic():
        # 1. Create the JE Header
        je = JournalEntry.objects.create(
            date=ob_entry.migration_date,
            description=_(f"Opening Balance as of {ob_entry.migration_date}: {ob_entry.name}"),
            source_object=ob_entry,
            status=JournalEntry.Status.DRAFT # Start as draft
        )
        logger.info(f"    Created draft JE-{je.id} for OB Entry {ob_entry.id}.")

        total_debits = Decimal("0.0")
        total_credits = Decimal("0.0")

        # 2. Iterate through lines and create JE Lines
        for line in ob_entry.lines.prefetch_related('sub_ledger_details__sub_ledger_object').all():
            logger.info(f"    Processing OB Line for Account '{line.account.code}'...")

            # If there are sub-ledger details, create a JE line for each one
            if line.sub_ledger_details.exists():
                # --- MODIFICATION START ---
                # For product-based accounts, we might have multiple details pointing to the SAME product.
                # We need to aggregate these. For other sub-ledgers (Customer, Asset), each detail is unique.
                if line.account.sub_ledger_model == ContentType.objects.get_for_model(Product):
                    details_by_product = {}
                    for detail in line.sub_ledger_details.all():
                        product_id = detail.sub_ledger_object.pk
                        details_by_product[product_id] = details_by_product.get(product_id, Decimal('0.0')) + detail.amount
                    
                    for product_id, total_amount in details_by_product.items():
                        product_instance = Product.objects.get(pk=product_id)
                        JournalEntryLine.objects.create(
                            journal_entry=je,
                            account=line.account,
                            entry_type=line.entry_type,
                            amount=total_amount,
                            sub_ledger_object=product_instance
                        )
                        logger.info(f"        Created aggregated sub-ledger line for Product '{product_instance.name}': {line.entry_type} {line.account.code} for {total_amount}")

                else: # For non-product sub-ledgers, create one line per detail
                    for detail in line.sub_ledger_details.all():
                        JournalEntryLine.objects.create(
                            journal_entry=je,
                            account=line.account,
                            entry_type=line.entry_type,
                            amount=detail.amount,
                            sub_ledger_object=detail.sub_ledger_object
                        )
                        logger.info(f"        Created sub-ledger line: {line.entry_type} {line.account.code} for {detail.amount} -> {detail.sub_ledger_object}")
                # --- MODIFICATION END ---
            # Otherwise, create a single line for the total amount
            else:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=line.account,
                    entry_type=line.entry_type,
                    amount=line.total_amount
                )
                logger.info(f"        Created aggregate line: {line.entry_type} {line.account.code} for {line.total_amount}")

            # Keep track of totals for validation
            if line.entry_type == OpeningBalanceEntryLine.EntryType.DEBIT:
                total_debits += line.total_amount
            else:
                total_credits += line.total_amount

        # 3. Final Validation and Posting
        logger.info(f"    Validation: Total Debits = {total_debits}, Total Credits = {total_credits}")
        je.validate_balance()
        if total_debits != total_credits:
            # The transaction will be rolled back due to the exception
            raise ValueError(
                _(f"Opening Balance JE is not balanced. Debits ({total_debits}) do not equal Credits ({total_credits}).")
            )
        
        je.status = JournalEntry.Status.POSTED
        je.save(update_fields=['status'])
        
        ob_entry.journal_entry = je
        ob_entry.status = OpeningBalanceEntry.Status.POSTED
        ob_entry.posted_at = timezone.now()
        ob_entry.save(update_fields=['journal_entry', 'status', 'posted_at'])
        
        logger.info(f"<-- Successfully created and posted JE-{je.id} for Opening Balance Entry {ob_entry.id}.")
        
    return je


def correct_approved_expense(request_id: int, user, justification: str) -> TransactionCorrection:
    """
    Finds an approved expense request and its resulting transaction, and creates
    a reversing journal entry and an audit record for the correction.
    """
    with transaction.atomic():
        # 1. Find the request and ensure it's correctable.
        try:
            request = ExpenseRequest.objects.select_for_update().get(id=request_id)
        except ExpenseRequest.DoesNotExist:
            raise ValidationError(f"ExpenseRequest with ID {request_id} not found.")

        if request.status != ExpenseRequest.Status.APPROVED:
            raise PermissionDenied(f"Cannot correct a request with status '{request.status}'. Only approved requests can be corrected.")

        # 2. Find the original transaction (ExpenseLog or InventoryConsumption).
        original_object = None
        if request.request_type == ExpenseRequest.RequestType.DIRECT_EXPENSE:
            original_object = request.final_expense_logs.first()
        elif request.request_type in [
            ExpenseRequest.RequestType.INVENTORY_EXPENSE,
            ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
            ExpenseRequest.RequestType.INVENTORY_PREPAID
        ]:
            original_object = request.final_consumption

        if not original_object:
            raise ValidationError("Could not find the original transaction linked to this expense request.")

        # 3. Create the reversing journal entry
        reversing_je = create_reversing_je_for_correction(
            original_object=original_object,
            justification=justification,
            user=user,
            correction_date=timezone.now()
        )

        # 4. Create the audit record for the correction using get_or_create for safety.
        # This prevents errors if a signal also tries to create this record.
        correction_record, created = TransactionCorrection.objects.get_or_create(
            adjusting_journal_entry=reversing_je,
            defaults={
                'source_object': original_object,
                'justification': justification,
                'corrected_by': user
            }
        )

        # 5. Update the original request with a note about the correction
        request.notes = f"{request.notes or ''}\n\nCORRECTION: This request was reversed on {timezone.now().date()} by {user.username}. Justification: {justification}. See JE-{reversing_je.id}."
        request.save(update_fields=['notes'])

        logger.info(f"User '{user.username}' corrected ExpenseRequest ID {request.id}. Reversing JE-{reversing_je.id} created.")

        return correction_record

def create_reversing_je_for_correction(
    original_object,
    justification: str,
    user,
    correction_date: Optional[timezone.datetime] = None
) -> JournalEntry:
    """
    Creates a new journal entry in the current open period that exactly reverses
    the financial impact of an original transaction's journal entry.

    This is the core of the "Immutable Ledger" pattern.

    Args:
        original_object: The instance of the model to be corrected (e.g., a FinishedProductDispatch).
        justification: The reason for the correction, for audit purposes.
        user: The user performing the correction.
        correction_date: The date for the new JE. Defaults to now().

    Returns:
        The newly created adjusting JournalEntry.
    """
    content_type = ContentType.objects.get_for_model(original_object)

    # 1. --- Pre-checks and Guards ---
    # Find the original journal entry
    original_je = JournalEntry.objects.filter(
        content_type=content_type, object_id=original_object.pk
    ).first()

    if not original_je:
        raise ValueError(f"Cannot create correction: No original journal entry found for {original_object}.")

    # Check if it has already been corrected
    if TransactionCorrection.objects.filter(content_type=content_type, object_id=original_object.pk).exists():
        raise PermissionError(f"This transaction ({original_object}) has already been corrected and cannot be adjusted again.")

    # The new JE must be in an open period
    if not correction_date:
        correction_date = timezone.now()
    _check_period_is_open(correction_date)

    # 2. --- Create the Reversing Journal Entry ---
    with transaction.atomic():
        description = _(
            "Reversal of JE-%(original_je_id)s for: %(original_desc)s"
        ) % {
            'original_je_id': original_je.id,
            'original_desc': original_je.description
        }

        # Create the new adjusting JE header
        adjusting_je = JournalEntry.objects.create(
            date=correction_date,
            description=description,
            notes=justification,
            status=JournalEntry.Status.POSTED
        )

        # Create the reversing lines
        for line in original_je.lines.all():
            JournalEntryLine.objects.create(
                journal_entry=adjusting_je,
                account=line.account,
                amount=line.amount,
                # The core of the reversal: flip debit to credit and vice-versa
                entry_type=JournalEntryLine.EntryType.CREDIT if line.entry_type == JournalEntryLine.EntryType.DEBIT else JournalEntryLine.EntryType.DEBIT,
                sub_ledger_object=line.sub_ledger_object
            )

        je.validate_balance()
        # 3. --- Create the Audit Record ---
        correction_record = TransactionCorrection.objects.create(
            source_object=original_object,
            adjusting_journal_entry=adjusting_je,
            justification=justification,
            corrected_by=user
        )

        # Link the new JE back to the correction record for a circular audit trail
        adjusting_je.source_object = correction_record
        adjusting_je.save(update_fields=['content_type', 'object_id'])

        logger.info(f"Successfully created reversing JE-{adjusting_je.id} to correct {original_object}.")

    return adjusting_je


def run_monthly_depreciation(period: FinancialPeriod) -> dict:
    """
    Calculates and posts depreciation for all eligible fixed assets for a given period.

    - Identifies all 'In Service' assets whose depreciation should have started.
    - Checks if depreciation has already been posted for the period to prevent duplicates.
    - Calculates straight-line monthly depreciation.
    - Handles the final depreciation amount to ensure the net book value matches the salvage value.
    - Creates a DepreciationLog for each asset, which triggers JE creation via a signal.

    Returns:
        A dictionary summarizing the run (e.g., assets processed, total depreciated).
    """
    logger.info(f"Starting monthly depreciation run for period '{period.name}'.")
    _check_period_is_open(period.end_date)

    assets_to_depreciate = FixedAsset.objects.filter(
        status=FixedAsset.AssetStatus.IN_SERVICE,
        depreciation_start_date__lte=period.end_date
    )

    # Exclude assets for which depreciation has already been logged for this period's end date
    existing_logs = DepreciationLog.objects.filter(
        asset__in=assets_to_depreciate,
        period_date=period.end_date
    ).values_list('asset_id', flat=True)

    assets_to_process = assets_to_depreciate.exclude(id__in=existing_logs)

    # --- FIX: The checklist should be updated REGARDLESS of whether assets were found. ---
    # The act of running this service means the depreciation task for the period is "done".
    try:
        checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=period)
        checklist.is_depreciation_run = True
        checklist.save()
        logger.info(f"Updated period close checklist for {period.name}: is_depreciation_run=True.")
    except Exception as e:
        # Log the error but don't let it crash the entire process
        logger.error(f"Could not update period close checklist for '{period.name}': {e}", exc_info=True)

    if not assets_to_process.exists():
        logger.info("No new assets found to depreciate for this period.")
        summary = {
            "status": "success",
            "message": "No new assets found to depreciate for this period.",
            "assets_processed": 0,
            "total_depreciation": Decimal("0.0")
        }
        return summary

    processed_count = 0
    total_depreciation_posted = Decimal("0.0")

    for asset in assets_to_process:
        with transaction.atomic():
            # Ensure we don't depreciate past the salvage value
            accumulated_dep = asset.accumulated_depreciation
            depreciable_base = asset.depreciable_base

            if accumulated_dep >= depreciable_base:
                logger.info(f"Skipping asset '{asset.asset_tag}' as it is fully depreciated.")
                continue

            monthly_depreciation_amount = (depreciable_base / (asset.useful_life_years * 12)).quantize(Decimal('0.001'))

            # Check if this is the last depreciation entry or if it would overshoot
            if (accumulated_dep + monthly_depreciation_amount) > depreciable_base:
                final_amount = depreciable_base - accumulated_dep
                depreciation_amount = final_amount
            else:
                depreciation_amount = monthly_depreciation_amount

            if depreciation_amount > 0:
                # This creation will trigger the post_save signal to create the JE
                DepreciationLog.objects.create(
                    asset=asset,
                    period_date=period.end_date,
                    amount=depreciation_amount
                )
                processed_count += 1
                total_depreciation_posted += depreciation_amount
                logger.info(f"Posted depreciation of {depreciation_amount} for asset '{asset.asset_tag}'.")

    summary = {
        "status": "success",
        "message": f"Depreciation run completed for period '{period.name}'.",
        "assets_processed": processed_count,
        "total_depreciation": total_depreciation_posted
    }
    logger.info(f"Finished depreciation run. Processed {processed_count} assets with a total value of {total_depreciation_posted}.")
    return summary