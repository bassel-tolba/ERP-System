# gipcco_project/inventory/services/accounting/inventory_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db.models import F, Sum
from django.utils.translation import gettext_lazy as _

from ...models import (
    InventoryLog, JournalEntry, JournalEntryLine,
    GeneralAccountingSettings, InventoryAdjustment, PurchaseOrderItem
)
from ._helpers import (
    _get_product_inventory_account
)
from ._builder import JournalEntryBuilder

logger = logging.getLogger(__name__)


def create_je_for_inventory_adjustment(adjustment: InventoryAdjustment) -> Optional[JournalEntry]:
    """
    Creates a journal entry for an inventory adjustment, handling different logic
    for standard adjustments vs. adjustments originating from a sales return.
    """
    settings = GeneralAccountingSettings.load()
    inventory_account = _get_product_inventory_account(adjustment.product)
    adjustment_value = abs(Decimal(str(adjustment.adjustment_quantity)) * adjustment.cost_at_adjustment)

    debit_account, credit_account = None, None
    debit_sub_ledger, credit_sub_ledger = None, None

    if adjustment.source_sales_return_item:
        clearing_account = settings.sales_returns_clearing_account
        if not clearing_account:
            raise ValueError(_("Sales Returns Clearing Account is not configured."))
        if adjustment.adjustment_quantity < 0:  # Scrapped item
            debit_account = settings.damaged_goods_expense_account
            credit_account = clearing_account
        else:  # Return to stock
            debit_account = inventory_account
            credit_account = clearing_account
            debit_sub_ledger = adjustment.product
    elif adjustment.reason_code == InventoryAdjustment.ReasonCode.RETURN_TO_SUPPLIER:
        debit_account = settings.purchase_returns_clearing_account
        credit_account = inventory_account
        credit_sub_ledger = adjustment.product
    else: # Standard Adjustment
        if adjustment.adjustment_quantity < 0:  # Shortage
            debit_account = settings.damaged_goods_expense_account if adjustment.reason_code == InventoryAdjustment.ReasonCode.DAMAGE else settings.inventory_adjustment_loss_account
            credit_account = inventory_account
            credit_sub_ledger = adjustment.product
        else:  # Overage
            debit_account = inventory_account
            credit_account = settings.inventory_adjustment_gain_account
            debit_sub_ledger = adjustment.product

    if not all([debit_account, credit_account]):
        raise ValueError(_("Could not determine debit/credit accounts for inventory adjustment."))

    description = _("تسوية مخزون للمنتج '%(product)s' بسبب %(reason)s") % {
        'product': adjustment.product.name,
        'reason': adjustment.get_reason_code_display()
    }

    builder = JournalEntryBuilder(source_object=adjustment)
    builder.set_description(description)
    builder.debit(adjustment_value, debit_account, sub_ledger_object=debit_sub_ledger)
    builder.credit(adjustment_value, credit_account, sub_ledger_object=credit_sub_ledger)
    return builder.post()


def create_je_for_inventory_receipt(inventory_log: InventoryLog) -> Optional[JournalEntry]:
    """
    Creates a journal entry for a released inventory receipt,
    capitalizing a prorated share of the PO's estimated landed costs.
    """
    # 1. --- Business Logic Pre-checks ---
    if inventory_log.status != InventoryLog.Status.RELEASED:
        logger.debug(f"JE creation skipped for InventoryLog {inventory_log.id}: Status is '{inventory_log.status}'.")
        return None
    if not inventory_log.release_timestamp:
        raise ValueError(f"Released InventoryLog ID {inventory_log.id} is missing a release_timestamp.")

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

    # Prorated Landed Cost Calculation
    prorated_landed_cost = Decimal('0.0')
    if inventory_log.po_item and inventory_log.po_item.quantity_ordered > 0:
        po_item = inventory_log.po_item
        purchase_order = po_item.purchase_order
        total_po_landed_cost = purchase_order.landed_costs.aggregate(
            total=Sum('estimated_amount')
        )['total'] or Decimal('0.0')
        item_allocation_percentage = po_item.landed_cost_allocation_percentage / Decimal('100.0')
        total_landed_cost_for_item = total_po_landed_cost * item_allocation_percentage
        receipt_quantity_ratio = quantity / Decimal(str(po_item.quantity_ordered))
        prorated_landed_cost = total_landed_cost_for_item * receipt_quantity_ratio

    costing_value = total_base_amount + prorated_landed_cost
    if inventory_log.vat_treatment == InventoryLog.VatTreatment.CAPITALIZED:
        costing_value += vat_amount

    # Persist the final calculated costs on the log itself for auditability
    if quantity > 0:
        final_costing_unit_price = costing_value / quantity
        landed_cost_per_unit = prorated_landed_cost / quantity
        InventoryLog.objects.filter(pk=inventory_log.pk).update(
            landed_cost_component=landed_cost_per_unit,
            costing_unit_price=final_costing_unit_price
        )

    grni_credit_amount = total_base_amount + vat_amount - wht_amount

    # 4. --- Build and Post the Journal Entry ---
    description = _("Receipt of %(qty)s %(unit)s of '%(prod)s' from %(supp)s (QC: %(qc)s)") % {
        'qty': inventory_log.quantity, 'unit': inventory_log.product.unit,
        'prod': inventory_log.product.name, 'supp': inventory_log.company.name if inventory_log.company else 'N/A',
        'qc': inventory_log.qc_no or 'N/A',
    }

    builder = JournalEntryBuilder(source_object=inventory_log)
    builder.set_date(inventory_log.release_timestamp)
    builder.set_description(description)

    # Debits
    builder.debit(costing_value, inventory_account, sub_ledger_object=inventory_log.product)
    if inventory_log.vat_treatment == InventoryLog.VatTreatment.RECOVERABLE:
        builder.debit(vat_amount, vat_account)

    # Credits
    builder.credit(grni_credit_amount, grni_account, sub_ledger_object=inventory_log.company)
    builder.credit(prorated_landed_cost, accrued_landed_costs_account)
    builder.credit(wht_amount, wht_account)

    return builder.post()
