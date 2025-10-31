# gipcco_project/inventory/services/accounting/inventory_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F, Sum
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType

from ...models import (
    InventoryLog, JournalEntry, JournalEntryLine,
    GeneralAccountingSettings, InventoryAdjustment, PurchaseOrderItem
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
        elif adjustment.reason_code == InventoryAdjustment.ReasonCode.RETURN_TO_SUPPLIER:
            # --- Purchase Return Adjustment Logic ---
            clearing_account = settings.purchase_returns_clearing_account
            if not clearing_account:
                raise ValueError(_("Purchase Returns Clearing Account is not configured."))
            
            logger.info(f"    Processing return to supplier: DEBIT '{clearing_account.name}', CREDIT '{inventory_account.name}' with {adjustment_value}.")
            # Debit the clearing account, which will be offset by the debit memo
            JournalEntryLine.objects.create(
                journal_entry=je, account=clearing_account, amount=adjustment_value,
                entry_type=JournalEntryLine.EntryType.DEBIT
            )
            # Credit Inventory as the goods are leaving
            JournalEntryLine.objects.create(
                journal_entry=je, account=inventory_account, amount=adjustment_value,
                entry_type=JournalEntryLine.EntryType.CREDIT, sub_ledger_object=adjustment.product
            )

        else:
            # --- Standard Inventory Adjustment Logic ---
            if adjustment.adjustment_quantity < 0:  # Shortage
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
    REFACTORED: Creates a journal entry for a released inventory receipt,
    capitalizing a prorated share of the PO's estimated landed costs.
    """
    try:
        inventory_log = InventoryLog.objects.select_related(
            'po_item__purchase_order', 'product', 'company'
        ).get(pk=inventory_log.pk)
    except InventoryLog.DoesNotExist:
        logger.error(f"Could not re-fetch InventoryLog with pk={inventory_log.pk} in create_je_for_inventory_receipt.")
        return None

    # 1. --- Pre-checks and Guards ---
    if inventory_log.status != InventoryLog.Status.RELEASED:
        logger.debug(f"JE creation skipped for InventoryLog {inventory_log.id}: Status is '{inventory_log.status}'.")
        return None
    if not inventory_log.release_timestamp:
        raise ValueError(f"Released InventoryLog ID {inventory_log.id} is missing a release_timestamp.")
    if JournalEntry.objects.filter(content_type=ContentType.objects.get_for_model(inventory_log), object_id=inventory_log.id).exists():
        logger.debug(f"JE creation skipped for InventoryLog {inventory_log.id}: Journal entry already exists.")
        return None
    _check_period_is_open(inventory_log.release_timestamp)

    # 2. --- Get Accounts from Configuration ---
    settings = GeneralAccountingSettings.load()
    inventory_account = _get_product_inventory_account(inventory_log.product)
    grni_account = settings.goods_received_not_invoiced_account
    vat_account = settings.vat_receivable
    wht_account = settings.withholding_tax_payable
    accrued_landed_costs_account = settings.accrued_landed_costs_account

    if not all([inventory_account, grni_account, vat_account, wht_account, accrued_landed_costs_account]):
        raise ValueError(_("One or more required accounts are not configured (Inventory, GRNI, VAT, WHT, Accrued Landed Costs)."))

    # 3. --- Calculate Amounts ---
    quantity = Decimal(str(inventory_log.quantity))
    total_base_amount = inventory_log.base_unit_price * quantity
    vat_amount = inventory_log.vat_amount
    wht_amount = inventory_log.withholding_tax_amount

    # --- NEW: Prorated Landed Cost Calculation ---
    prorated_landed_cost = Decimal('0.0')
    if inventory_log.po_item and inventory_log.po_item.quantity_ordered > 0:
        po_item = inventory_log.po_item
        purchase_order = po_item.purchase_order
        
        # 1. Get total estimated landed costs for the entire PO
        total_po_landed_cost = purchase_order.landed_costs.aggregate(
            total=Sum('estimated_amount')
        )['total'] or Decimal('0.0')
        
        # 2. Calculate the portion allocated to this specific line item
        item_allocation_percentage = po_item.landed_cost_allocation_percentage / Decimal('100.0')
        total_landed_cost_for_item = total_po_landed_cost * item_allocation_percentage
        
        # 3. Prorate the item's allocated cost based on the quantity being received now
        receipt_quantity_ratio = quantity / Decimal(str(po_item.quantity_ordered))
        prorated_landed_cost = total_landed_cost_for_item * receipt_quantity_ratio

    # Calculate the final, total value to be capitalized into inventory
    costing_value = total_base_amount + prorated_landed_cost
    if inventory_log.vat_treatment == InventoryLog.VatTreatment.CAPITALIZED:
        costing_value += vat_amount

    # Update the log with the final calculated costs to persist them.
    if quantity > 0:
        final_costing_unit_price = costing_value / quantity
        landed_cost_per_unit = prorated_landed_cost / quantity
        InventoryLog.objects.filter(pk=inventory_log.pk).update(
            landed_cost_component=landed_cost_per_unit,
            costing_unit_price=final_costing_unit_price
        )
        inventory_log.refresh_from_db()

    grni_credit_amount = total_base_amount + vat_amount - wht_amount

    # 4. --- Create Journal Entry and Lines ---
    with transaction.atomic():
        description = _(
            "Receipt of %(qty)s %(unit)s of '%(prod)s' from %(supp)s (QC: %(qc)s)"
        ) % {
            'qty': inventory_log.quantity, 'unit': inventory_log.product.unit,
            'prod': inventory_log.product.name, 'supp': inventory_log.company.name if inventory_log.company else 'N/A',
            'qc': inventory_log.qc_no or 'N/A',
        }
        je = JournalEntry.objects.create(
            date=inventory_log.release_timestamp, description=description,
            source_object=inventory_log, status=JournalEntry.Status.POSTED
        )
        
        # DEBIT: Inventory for the full capitalized value
        JournalEntryLine.objects.create(
            journal_entry=je, account=inventory_account, amount=costing_value,
            entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=inventory_log.product
        )
        
        # DEBIT: VAT Receivable (if applicable)
        if inventory_log.vat_treatment == InventoryLog.VatTreatment.RECOVERABLE and vat_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=vat_account, amount=vat_amount,
                entry_type=JournalEntryLine.EntryType.DEBIT
            )
        
        # CREDIT: Goods Received, Not Invoiced (GRNI) for the supplier's portion
        JournalEntryLine.objects.create(
            journal_entry=je, account=grni_account, amount=grni_credit_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT, sub_ledger_object=inventory_log.company
        )

        # CREDIT: Accrued Landed Costs for the estimated third-party costs
        if prorated_landed_cost > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=accrued_landed_costs_account, amount=prorated_landed_cost,
                entry_type=JournalEntryLine.EntryType.CREDIT
            )

        # CREDIT: Withholding Tax Payable (if applicable)
        if wht_amount > 0:
            JournalEntryLine.objects.create(
                journal_entry=je, account=wht_account, amount=wht_amount,
                entry_type=JournalEntryLine.EntryType.CREDIT
            )

        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for InventoryLog ID {inventory_log.id} with prorated landed costs.")

    return je
