# gipcco_project/inventory/services/accounting/inventory_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    InventoryLog, JournalEntry, JournalEntryLine,
    GeneralAccountingSettings, InventoryAdjustment
)
from ._helpers import (
    _check_period_is_open, _get_product_inventory_account,
    _get_product_expense_account
)

logger = logging.getLogger(__name__)


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
