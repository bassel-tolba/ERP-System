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
    Creates a journal entry for an inventory adjustment, handling different logic
    for standard adjustments vs. adjustments originating from a sales return.

    Standard Adjustment Logic:
    - Shortage: DEBIT Loss/Expense Account, CREDIT Inventory Account
    - Overage:  DEBIT Inventory Account, CREDIT Gain Account

    Sales Return Adjustment Logic:
    - Return to Stock (Overage): DEBIT Inventory Account, CREDIT Sales Returns Clearing Account
    - Scrap (Shortage):         DEBIT Damaged Goods Expense, CREDIT Sales Returns Clearing Account
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
    adjustment_value = abs(Decimal(str(adjustment.adjustment_quantity)) * adjustment.cost_at_adjustment)
    logger.info(f"    Calculated adjustment value: {adjustment_value} (Qty: {adjustment.adjustment_quantity}, Cost: {adjustment.cost_at_adjustment})")
    
    with transaction.atomic():
        description = _(
            "تسوية مخزون للمنتج '%(product)s' بسبب %(reason)s"
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

        if adjustment.source_sales_return_item:
            # --- Sales Return Adjustment Logic ---
            clearing_account = settings.sales_returns_clearing_account
            if not clearing_account:
                raise ValueError(_("Sales Returns Clearing Account is not configured."))

            if adjustment.adjustment_quantity < 0:  # Scrapped item
                expense_account = settings.damaged_goods_expense_account
                if not expense_account:
                    raise ValueError(_("Damaged Goods Expense Account is not configured."))
                
                logger.info(f"    Processing sales return scrap: DEBIT '{expense_account.name}', CREDIT '{clearing_account.name}' with {adjustment_value}.")
                JournalEntryLine.objects.create(
                    journal_entry=je, account=expense_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT
                )
                JournalEntryLine.objects.create(
                    journal_entry=je, account=clearing_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT
                )
            else:  # Return to stock
                logger.info(f"    Processing return to stock: DEBIT '{inventory_account.name}', CREDIT '{clearing_account.name}' with {adjustment_value}.")
                JournalEntryLine.objects.create(
                    journal_entry=je, account=inventory_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT,
                    sub_ledger_object=adjustment.product
                )
                JournalEntryLine.objects.create(
                    journal_entry=je, account=clearing_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT
                )
        else:
            # --- Standard Inventory Adjustment Logic ---
            if adjustment.adjustment_quantity < 0:  # Shortage
                # --- NEW: Handle returns to supplier ---
                if adjustment.reason_code == InventoryAdjustment.ReasonCode.RETURN_TO_SUPPLIER:
                    ap_account = settings.accounts_payable
                    if not ap_account:
                        raise ValueError(_("Accounts Payable account is not configured."))
                    
                    logger.info(f"    Processing return to supplier: DEBIT '{ap_account.name}', CREDIT '{inventory_account.name}' with {adjustment_value}.")
                    JournalEntryLine.objects.create(
                        journal_entry=je, account=ap_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT,
                        sub_ledger_object=adjustment.source_purchase_return_item.purchase_return.supplier
                    )
                    JournalEntryLine.objects.create(
                        journal_entry=je, account=inventory_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT,
                        sub_ledger_object=adjustment.product
                    )
                    # Early exit for this specific case
                    je.validate_balance()
                    logger.info(f"    Successfully created JE-{je.id} for InventoryAdjustment ID {adjustment.id}.")
                    logger.info(f"<-- Exiting 'create_je_for_inventory_adjustment' for Adjustment ID {adjustment.id}.")
                    return je
                # --- END NEW ---

                if adjustment.reason_code == InventoryAdjustment.ReasonCode.DAMAGE:
                    loss_account = settings.damaged_goods_expense_account
                else:
                    loss_account = settings.inventory_adjustment_loss_account
                if not loss_account:
                    raise ValueError(_("Loss account for inventory adjustments is not configured."))

                logger.info(f"    Processing shortage: DEBIT '{loss_account.name}', CREDIT '{inventory_account.name}' with {adjustment_value}.")
                JournalEntryLine.objects.create(
                    journal_entry=je, account=loss_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.DEBIT
                )
                JournalEntryLine.objects.create(
                    journal_entry=je, account=inventory_account, amount=adjustment_value, entry_type=JournalEntryLine.EntryType.CREDIT,
                    sub_ledger_object=adjustment.product
                )
            else:  # Overage
                gain_account = settings.inventory_adjustment_gain_account
                if not gain_account:
                    raise ValueError(_("Gain account for inventory adjustments is not configured."))

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
    # --- MODIFIED: Credit GRNI account instead of A/P ---
    grni_account = settings.goods_received_not_invoiced_account
    vat_account = settings.vat_receivable
    wht_account = settings.withholding_tax_payable
    
    if not all([inventory_account, grni_account, vat_account, wht_account]):
        raise ValueError(_("One or more required general accounting settings are not configured (Inventory, GRNI, VAT, WHT)."))

    # 3. --- Calculate Amounts ---
    quantity = Decimal(str(inventory_log.quantity))
    total_base_amount = inventory_log.base_unit_price * quantity
    vat_amount = inventory_log.vat_amount
    wht_amount = inventory_log.withholding_tax_amount
    
    # The costing_unit_price is now calculated in a pre_save signal.
    costing_value = inventory_log.costing_unit_price * quantity
    total_invoice_amount = total_base_amount + vat_amount
    
    # 4. --- Create Journal Entry and Lines within a Transaction ---
    with transaction.atomic():
        description = _(
            "استلام بضاعة بعدد %(quantity)s %(unit)s من '%(product)s' من المورد %(supplier)s (رقم فحص الجودة: %(qc)s)"
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
        
        # Line 3: Credit Goods Received, Not Invoiced (GRNI) Account
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=grni_account,
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
