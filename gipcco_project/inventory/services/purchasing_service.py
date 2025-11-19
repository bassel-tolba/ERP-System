# gipcco_project/inventory/services/purchasing_service.py

import logging
from decimal import Decimal
from typing import Optional, Dict, List, Any

from django.db import transaction
from django.db.models import Sum, F, FloatField, Q, DecimalField
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone

from ..models import (
    SupplierInvoice, JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    InventoryAdjustment, PurchaseReturn, PurchaseOrder, PurchaseOrderItem,
    SupplierDebitMemo, LandedCostInvoice, InventoryLog, PurchaseOrderLandedCost,
    LandedCostType, PurchaseReturnItem, LandedCostAllocation, Payment,
    LandedCostPaymentApplication
)
from .accounting._helpers import _check_period_is_open, _get_product_inventory_account
from .costing_service import recalculate_cost_history_for_product

logger = logging.getLogger(__name__)


# ==============================================================================
#  PURCHASE ORDER MANAGEMENT
# ==============================================================================

def create_purchase_order(user, po_data: dict, items_data: list, landed_costs_data: list) -> PurchaseOrder:
    """
    Creates a new Purchase Order, its items, and any associated
    estimated landed costs from validated data.
    
    Args:
        user: The user creating the PO
        po_data: Dict with 'po_number', 'supplier_id', 'order_date'
        items_data: List of dicts, each with:
            - 'product_id'
            - 'quantity'
            - 'base_price_per_unit'
            - 'vat_rate'
            - 'withholding_tax_rate'
            - 'landed_cost_allocation_percentage'
        landed_costs_data: List of dicts, each with {'cost_type_id', 'estimated_amount'}
    """
    logger.info(f"--> User {user.username} attempting to create a Purchase Order.")
    logger.debug(f"    PO Data: {po_data}")
    logger.debug(f"    Items Data: {items_data}")
    logger.debug(f"    Landed Costs Data: {landed_costs_data}")

    # --- Validation ---
    if not all([po_data.get('po_number'), po_data.get('supplier_id'), po_data.get('order_date')]):
        logger.error("Validation failed: PO Number, Supplier, or Order Date is missing.")
        raise ValidationError(_("PO Number, Supplier, and Order Date are required."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exists():
        logger.error(f"Validation failed: PO Number '{po_data['po_number']}' already exists.")
        raise ValidationError(_("A Purchase Order with this number already exists."))

    # Validate allocation percentages
    total_percentage = sum(Decimal(item.get('landed_cost_allocation_percentage', 0)) for item in items_data)
    if landed_costs_data and total_percentage != Decimal('100.0'):
        logger.error(f"Validation failed: Landed cost allocation percentages sum to {total_percentage}, not 100.")
        raise ValidationError(_("Landed cost allocation percentages for all items must sum to exactly 100%."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        
        # Create PO header
        po = PurchaseOrder.objects.create(
            po_number=po_data['po_number'],
            supplier_id=po_data['supplier_id'],
            order_date=po_data['order_date']
        )
        logger.debug(f"    Created PurchaseOrder header PO-{po.id} with number {po.po_number}.")

        # Create PO items
        items_to_create = []
        for item_data in items_data:
            logger.debug(f"      Processing item: {item_data}")
            if not all([item_data.get('product_id'), item_data.get('quantity'), item_data.get('base_price_per_unit')]):
                logger.error(f"Validation failed for item: {item_data}. Missing required fields.")
                raise ValidationError(_("Product, Quantity, and Price are required for all items."))
            
            items_to_create.append(
                PurchaseOrderItem(
                    purchase_order=po,
                    product_id=item_data['product_id'],
                    quantity_ordered=float(item_data['quantity']),
                    base_price_per_unit=Decimal(str(item_data['base_price_per_unit'])),
                    vat_rate=Decimal(str(item_data.get('vat_rate', '0.14'))),
                    withholding_tax_rate=Decimal(str(item_data.get('withholding_tax_rate', '0.01'))),
                    landed_cost_allocation_percentage=Decimal(item_data.get('landed_cost_allocation_percentage', '0.0'))
                )
            )
        
        if not items_to_create:
            logger.error("Validation failed: No items were provided for the PO.")
            raise ValidationError(_("A Purchase Order must have at least one item."))
        
        PurchaseOrderItem.objects.bulk_create(items_to_create)
        logger.debug(f"    Bulk created {len(items_to_create)} PurchaseOrderItem objects.")
        
        # Create PO-level landed cost estimates
        if landed_costs_data:
            estimates_to_create = []
            for lc_data in landed_costs_data:
                if lc_data.get('cost_type_id') and lc_data.get('estimated_amount'):
                    estimates_to_create.append(
                        PurchaseOrderLandedCost(
                            purchase_order=po,
                            cost_type_id=lc_data['cost_type_id'],
                            estimated_amount=Decimal(str(lc_data['estimated_amount']))
                        )
                    )
            if estimates_to_create:
                PurchaseOrderLandedCost.objects.bulk_create(estimates_to_create)
                logger.debug(f"      Created {len(estimates_to_create)} landed cost estimates for PO {po.id}.")
        
        logger.debug("    Transaction finished.")

    logger.info(f"<-- User {user.username} successfully created Purchase Order {po.po_number}.")
    return po


def update_purchase_order(user, po: PurchaseOrder, po_data: dict, items_data: list, landed_costs_data: list) -> PurchaseOrder:
    """
    Updates an existing Purchase Order, its items, and their associated
    estimated landed costs.
    """
    logger.info(f"--> User {user.username} attempting to update Purchase Order {po.po_number} (ID: {po.id}).")
    logger.debug(f"    New PO Data: {po_data}")
    logger.debug(f"    New Items Data: {items_data}")
    logger.debug(f"    New Landed Costs Data: {landed_costs_data}")

    if po.items.filter(receipts__isnull=False).exists():
        logger.error(f"Permission denied: Cannot edit PO {po.po_number} because it has received items.")
        raise PermissionDenied(_("Cannot edit a Purchase Order that has received items."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exclude(pk=po.pk).exists():
        logger.error(f"Validation failed: Another PO with number '{po_data['po_number']}' already exists.")
        raise ValidationError(_("Another Purchase Order with this number already exists."))

    # Validate allocation percentages
    total_percentage = sum(Decimal(item.get('landed_cost_allocation_percentage', 0)) for item in items_data)
    if landed_costs_data and total_percentage != Decimal('100.0'):
        logger.error(f"Validation failed: Landed cost allocation percentages sum to {total_percentage}, not 100.")
        raise ValidationError(_("Landed cost allocation percentages for all items must sum to exactly 100%."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        po.po_number = po_data['po_number']
        po.supplier_id = po_data['supplier_id']
        po.order_date = po_data['order_date']
        po.save()
        logger.debug(f"    Updated PO header for {po.po_number}.")

        # Delete existing items and landed costs
        po.items.all().delete()
        po.landed_costs.all().delete()
        logger.debug("    Deleted existing items and PO-level landed cost estimates.")

        # Re-create items
        for item_data in items_data:
            logger.debug(f"      Processing new item: {item_data}")
            PurchaseOrderItem.objects.create(
                purchase_order=po,
                product_id=item_data['product_id'],
                quantity_ordered=float(item_data['quantity']),
                base_price_per_unit=Decimal(str(item_data['base_price_per_unit'])),
                vat_rate=Decimal(str(item_data.get('vat_rate', '0.14'))),
                withholding_tax_rate=Decimal(str(item_data.get('withholding_tax_rate', '0.01'))),
                landed_cost_allocation_percentage=Decimal(item_data.get('landed_cost_allocation_percentage', '0.0'))
            )

        # Re-create landed cost estimates
        if landed_costs_data:
            estimates_to_create = []
            for lc_data in landed_costs_data:
                if lc_data.get('cost_type_id') and lc_data.get('estimated_amount'):
                    estimates_to_create.append(
                        PurchaseOrderLandedCost(
                            purchase_order=po,
                            cost_type_id=lc_data['cost_type_id'],
                            estimated_amount=Decimal(str(lc_data['estimated_amount']))
                        )
                    )
            if estimates_to_create:
                PurchaseOrderLandedCost.objects.bulk_create(estimates_to_create)
                logger.debug(f"      Re-created {len(estimates_to_create)} landed cost estimates for PO {po.id}.")

    logger.info(f"<-- User {user.username} successfully updated Purchase Order {po.po_number}.")
    return po


def update_po_status_after_receipt(
    inventory_log_id: Optional[int], 
    is_final_receipt: bool, 
    old_po_item_id: Optional[int] = None
):
    """
    Updates the status of a Purchase Order based on its received items.
    This should be triggered after an InventoryLog is saved or deleted.

    Args:
        inventory_log_id: The ID of the newly created/updated InventoryLog. Can be None if a log was deleted.
        is_final_receipt: A boolean flag from the UI indicating if an under-delivery should close the PO line.
        old_po_item_id: The ID of a PurchaseOrderItem that was previously linked to a log, used for deletions or edits.
    """
    logger.debug(f"--> Triggered PO status update. Log ID: {inventory_log_id}, Is Final: {is_final_receipt}, Old PO Item ID: {old_po_item_id}")

    po_to_update = None
    po_item_to_check = None

    # Try to find the PO from the new inventory log
    if inventory_log_id:
        try:
            log = InventoryLog.objects.select_related('po_item__purchase_order').get(pk=inventory_log_id)
            if log.po_item:
                po_to_update = log.po_item.purchase_order
                po_item_to_check = log.po_item
                logger.debug(f"    Found PO {po_to_update.po_number} via InventoryLog {inventory_log_id}.")
        except InventoryLog.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent InventoryLog ID {inventory_log_id}.")
    
    # Fallback to old PO item (for deletion cases)
    if not po_to_update and old_po_item_id:
        try:
            old_item = PurchaseOrderItem.objects.select_related('purchase_order').get(pk=old_po_item_id)
            po_to_update = old_item.purchase_order
            logger.debug(f"    Found PO {po_to_update.po_number} via old_po_item_id {old_po_item_id}.")
        except PurchaseOrderItem.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent old_po_item_id {old_po_item_id}.")
            return

    if not po_to_update:
        logger.info("update_po_status_after_receipt called with no associated PO to update. Exiting.")
        return

    # Handle manual closing of an under-delivered item
    if po_item_to_check and is_final_receipt:
        logger.debug(f"    'is_final_receipt' is True for PO Item {po_item_to_check.id}. Checking for under-delivery.")
        total_received_for_item = po_item_to_check.receipts.exclude(status=InventoryLog.Status.VOIDED).aggregate(
            total=Coalesce(Sum('quantity'), 0.0, output_field=FloatField())
        )['total']
        logger.debug(f"    PO Item {po_item_to_check.id}: Ordered={po_item_to_check.quantity_ordered}, Total Received={total_received_for_item}")
        
        if total_received_for_item < po_item_to_check.quantity_ordered:
            po_item_to_check.is_closed = True
            po_item_to_check.save(update_fields=['is_closed'])
            logger.info(f"PO Item ID {po_item_to_check.id} for PO {po_to_update.po_number} was manually closed short.")

    # Update overall PO status based on all its items
    logger.debug(f"    Recalculating overall status for PO {po_to_update.po_number}.")
    all_items = po_to_update.items.all()
    
    # An item is considered "complete" if it's fully received OR manually closed
    completed_items_count = all_items.annotate(
        total_received=Coalesce(Sum('receipts__quantity', filter=~Q(receipts__status=InventoryLog.Status.VOIDED)), 0.0, output_field=FloatField())
    ).filter(
        Q(total_received__gte=F('quantity_ordered')) | Q(is_closed=True)
    ).count()

    total_received_on_po = all_items.aggregate(
        total=Coalesce(Sum('receipts__quantity', filter=~Q(receipts__status=InventoryLog.Status.VOIDED)), 0.0, output_field=FloatField())
    )['total']
    
    logger.debug(f"    PO {po_to_update.po_number}: Total Items={all_items.count()}, Completed Items={completed_items_count}, Total Qty Received={total_received_on_po}")

    # Determine new status
    new_status = po_to_update.status
    if completed_items_count == all_items.count():
        new_status = PurchaseOrder.Status.COMPLETED
    elif total_received_on_po > 0:
        new_status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        new_status = PurchaseOrder.Status.PENDING
    
    if new_status != po_to_update.status:
        po_to_update.status = new_status
        po_to_update.save(update_fields=['status'])
        logger.info(f"<-- Updated status for PO {po_to_update.po_number} to {po_to_update.status}.")
    else:
        logger.debug(f"<-- Status for PO {po_to_update.po_number} remains {po_to_update.status}.")


# ==============================================================================
#  SUPPLIER INVOICE POSTING
# ==============================================================================

def post_supplier_invoice(invoice: SupplierInvoice) -> JournalEntry:
    """
    Posts a 'Draft' supplier invoice to the General Ledger.

    This service performs the 3-way match by:
    1. Calculating the total value of all linked receipts (the amount in GRNI).
    2. Comparing this to the actual invoice total provided by the user.
    3. Creating a single, balanced journal entry that:
        - Clears the GRNI account for the receipt value.
        - Books the final, correct liability to Accounts Payable.
        - Records any difference as a Purchase Price Variance (PPV).
    4. Updates the invoice status to 'Awaiting Payment'.
    """
    logger.info(f"--> Attempting to post SupplierInvoice ID {invoice.id}.")
    logger.debug(f"    Invoice details: Number={invoice.invoice_number}, Date={invoice.invoice_date}, Supplier={invoice.supplier.name}, Status={invoice.status}")

    # --- 1. Pre-checks and Guards ---
    if invoice.status != SupplierInvoice.InvoiceStatus.DRAFT:
        logger.error(f"Validation failed for Invoice ID {invoice.id}: Status is '{invoice.status}', not 'Draft'.")
        raise ValidationError(_("Only invoices in 'Draft' status can be posted."))
    
    if not invoice.items.exists():
        logger.error(f"Validation failed for Invoice ID {invoice.id}: No items found.")
        raise ValidationError(_("Cannot post an invoice with no items."))

    if invoice.journal_entry:
        logger.error(f"Validation failed for Invoice ID {invoice.id}: Already has a journal entry (JE-{invoice.journal_entry.id}).")
        raise ValidationError(_("This invoice has already been posted and has a journal entry linked."))

    if not invoice.actual_subtotal or not invoice.actual_vat:
        logger.error(f"Validation failed for Invoice ID {invoice.id}: Actual subtotal or VAT is missing.")
        raise ValidationError(_("Actual subtotal and VAT from the physical invoice must be entered before posting."))

    logger.debug(f"    Pre-checks passed for Invoice ID {invoice.id}.")
    _check_period_is_open(invoice.invoice_date)

    # --- 2. Get Accounts from Configuration ---
    settings = GeneralAccountingSettings.load()
    grni_account = settings.goods_received_not_invoiced_account
    ap_account = settings.accounts_payable
    ppv_account = settings.purchase_price_variance_account
    vat_account = settings.vat_receivable
    
    logger.debug(f"    Accounts loaded: GRNI={grni_account.code}, A/P={ap_account.code}, PPV={ppv_account.code}, VAT={vat_account.code}")

    if not all([grni_account, ap_account, ppv_account, vat_account]):
        logger.error("CRITICAL: One or more required purchasing accounts are not configured in General Accounting Settings.")
        raise ValueError(_("GRNI, A/P, PPV, or VAT accounts are not configured in General Accounting Settings."))

    # --- 3. Calculate Amounts ---
    logger.debug(f"    Starting amount calculations for Invoice ID {invoice.id}.")
    receipt_base_value = Decimal('0.0')
    receipt_vat_value = Decimal('0.0')
    receipt_total_wht = Decimal('0.0')

    for item in invoice.items.select_related('receipt').all():
        receipt = item.receipt
        if receipt:
            item_base = receipt.base_unit_price * Decimal(str(receipt.quantity))
            receipt_base_value += item_base
            receipt_vat_value += receipt.vat_amount
            receipt_total_wht += receipt.withholding_tax_amount
            logger.debug(f"      Processing Receipt ID {receipt.id}: Base={item_base}, VAT={receipt.vat_amount}, WHT={receipt.withholding_tax_amount}")

    # The value in GRNI that needs to be cleared
    grni_clearing_value = (receipt_base_value + receipt_vat_value - receipt_total_wht).quantize(Decimal('0.001'))

    # The final A/P liability
    final_ap_liability = (invoice.actual_subtotal + invoice.actual_vat - receipt_total_wht).quantize(Decimal('0.001'))

    # PPV is the difference between invoice and receipt subtotals
    purchase_price_variance = (invoice.actual_subtotal - receipt_base_value).quantize(Decimal('0.001'))

    # VAT variance
    vat_variance = (invoice.actual_vat - receipt_vat_value).quantize(Decimal('0.001'))

    actual_invoice_total = (invoice.actual_subtotal + invoice.actual_vat).quantize(Decimal('0.001'))

    logger.info(f"    Calculations complete: GRNI Clearing={grni_clearing_value}, Final A/P={final_ap_liability}, PPV={purchase_price_variance}, VAT Variance={vat_variance}")
    logger.debug(f"    Receipt Totals: Base={receipt_base_value}, VAT={receipt_vat_value}, WHT={receipt_total_wht}")
    logger.debug(f"    Invoice Actuals: Subtotal={invoice.actual_subtotal}, VAT={invoice.actual_vat}, Total={actual_invoice_total}")

    # --- 4. Create Journal Entry and Lines ---
    with transaction.atomic():
        logger.debug(f"    Transaction started. Creating Journal Entry for Invoice ID {invoice.id}.")
        description = _("Posting Supplier Invoice %(invoice_num)s for %(supplier)s") % {
            'invoice_num': invoice.invoice_number,
            'supplier': invoice.supplier.name
        }
        
        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=description,
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )
        logger.debug(f"    Created JE-{je.id}.")

        # DEBIT: Clear the GRNI account
        logger.debug(f"      Creating DEBIT line to GRNI Account {grni_account.code} for {grni_clearing_value}.")
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=grni_account,
            amount=grni_clearing_value,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=invoice.supplier
        )

        # DEBIT/CREDIT: Purchase Price Variance
        if purchase_price_variance != 0:
            ppv_type = JournalEntryLine.EntryType.DEBIT if purchase_price_variance > 0 else JournalEntryLine.EntryType.CREDIT
            logger.debug(f"      Creating {ppv_type.upper()} line to PPV Account {ppv_account.code} for {abs(purchase_price_variance)}.")
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=ppv_account,
                amount=abs(purchase_price_variance),
                entry_type=ppv_type
            )

        # DEBIT/CREDIT: VAT Variance
        if vat_variance != 0:
            vat_type = JournalEntryLine.EntryType.DEBIT if vat_variance > 0 else JournalEntryLine.EntryType.CREDIT
            logger.debug(f"      Creating {vat_type.upper()} line to VAT Account {vat_account.code} for {abs(vat_variance)}.")
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=vat_account,
                amount=abs(vat_variance),
                entry_type=vat_type
            )

        # CREDIT: Accounts Payable
        logger.debug(f"      Creating CREDIT line to A/P Account {ap_account.code} for {final_ap_liability}.")
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=ap_account,
            amount=final_ap_liability,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=invoice.supplier
        )

        logger.debug(f"    Validating balance for JE-{je.id}.")
        je.validate_balance()
        logger.info(f"    Successfully created JE-{je.id} for Invoice ID {invoice.id}.")

        # --- 5. Update Invoice Status ---
        logger.debug(f"    Updating Invoice ID {invoice.id} status to AWAITING_PAYMENT.")
        invoice.status = SupplierInvoice.InvoiceStatus.AWAITING_PAYMENT
        invoice.journal_entry = je
        invoice.total_amount = actual_invoice_total
        invoice.save(update_fields=['status', 'journal_entry', 'total_amount'])
        logger.info(f"<-- Successfully posted SupplierInvoice ID {invoice.id}.")

    return je


# ==============================================================================
#  PURCHASE RETURNS
# ==============================================================================

def create_purchase_return(user, return_data: dict, items_data: list) -> PurchaseReturn:
    """
    Creates a Purchase Return and its items, validating that the return quantity
    does not exceed the available quantity from the original receipt.
    """
    logger.info(f"--> User {user.username} attempting to create a Purchase Return.")
    logger.debug(f"    Return Data: {return_data}")
    logger.debug(f"    Items Data: {items_data}")

    if not all([return_data.get('supplier_id'), return_data.get('return_date')]):
        logger.error("Validation failed: Supplier or Return Date is missing.")
        raise ValidationError(_("Supplier and Return Date are required."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        pr = PurchaseReturn.objects.create(
            supplier_id=return_data['supplier_id'],
            return_date=return_data['return_date'],
            notes=return_data.get('notes', '')
        )
        logger.debug(f"    Created PurchaseReturn header PR-{pr.id}.")

        items_to_create = []
        for item_data in items_data:
            receipt_id = item_data['original_receipt_id']
            logger.debug(f"      Processing item for original receipt ID {receipt_id}.")
            
            try:
                receipt = InventoryLog.objects.get(pk=receipt_id)
            except InventoryLog.DoesNotExist:
                logger.error(f"Validation failed: Receipt ID {receipt_id} not found.")
                raise ValidationError(_(f"Receipt ID {receipt_id} not found."))
            
            quantity_to_return = float(item_data['quantity_returned'])
            
            if quantity_to_return <= 0:
                logger.error(f"Validation failed for receipt {receipt_id}: Return quantity ({quantity_to_return}) must be positive.")
                raise ValidationError(_("Return quantity must be a positive number."))

            # Get quantity already returned against this receipt
            already_returned = receipt.purchase_return_items.aggregate(
                total=Sum('quantity_returned')
            )['total'] or 0.0
            
            available_to_return = receipt.quantity - already_returned
            logger.debug(f"      Receipt {receipt_id}: Original Qty={receipt.quantity}, Already Returned={already_returned}, Available={available_to_return}")

            if quantity_to_return > available_to_return:
                logger.error(f"Validation failed for receipt {receipt_id}: Attempting to return {quantity_to_return}, but only {available_to_return} is available.")
                raise ValidationError(
                    _("Cannot return %(qty)s. Only %(avail)s is available to be returned from receipt %(receipt)s.") % {
                        'qty': quantity_to_return, 'avail': available_to_return, 'receipt': receipt.pk
                    }
                )
            
            items_to_create.append(
                PurchaseReturnItem(
                    purchase_return=pr,
                    original_receipt=receipt,
                    quantity_returned=quantity_to_return
                )
            )
            logger.debug(f"      Item for receipt {receipt_id} is valid and queued for creation.")
        
        if not items_to_create:
            logger.error("Validation failed: No valid items were provided for the purchase return.")
            raise ValidationError(_("A purchase return must have at least one item."))
            
        logger.debug(f"    Bulk creating {len(items_to_create)} PurchaseReturnItem objects.")
        PurchaseReturnItem.objects.bulk_create(items_to_create)
        logger.debug("    Transaction finished.")

    logger.info(f"<-- User {user.username} successfully created Purchase Return {pr.id}.")
    return pr


def process_inventory_return(user, purchase_return: PurchaseReturn) -> PurchaseReturn:
    """
    Processes the inventory movement for a purchase return by creating
    a negative inventory adjustment for each item.
    """
    logger.info(f"--> User {user.username} attempting to process inventory movements for Purchase Return {purchase_return.id}.")
    
    if purchase_return.status != PurchaseReturn.Status.PENDING:
        logger.error(f"Permission denied: PR-{purchase_return.id} has status '{purchase_return.status}', not 'Pending'.")
        raise PermissionDenied(_("This return has already been processed."))

    with transaction.atomic():
        logger.debug(f"    Transaction started for PR-{purchase_return.id}.")
        
        for item in purchase_return.items.all():
            logger.debug(f"      Processing PR Item {item.id}: Returning {-item.quantity_returned} of Product ID {item.original_receipt.product.id} at cost {item.original_receipt.costing_unit_price}.")
            
            adj = InventoryAdjustment.objects.create(
                product=item.original_receipt.product,
                adjustment_date=purchase_return.return_date,
                adjustment_quantity=-item.quantity_returned,
                reason_code=InventoryAdjustment.ReasonCode.RETURN_TO_SUPPLIER,
                cost_at_adjustment=item.original_receipt.costing_unit_price,
                notes=f"Return for PR #{purchase_return.id}",
                source_purchase_return_item=item
            )
            logger.debug(f"      Created InventoryAdjustment ADJ-{adj.id} for PR Item {item.id}.")
        
        logger.debug(f"    Updating status of PR-{purchase_return.id} to COMPLETED.")
        purchase_return.status = PurchaseReturn.Status.COMPLETED
        purchase_return.save(update_fields=['status'])
        logger.debug("    Transaction finished.")
    
    logger.info(f"<-- User {user.username} successfully processed inventory movements for Purchase Return {purchase_return.id}.")
    return purchase_return


def create_debit_memo_from_return(user, purchase_return: PurchaseReturn, memo_data: dict) -> SupplierDebitMemo:
    """
    Creates a SupplierDebitMemo from a processed Purchase Return, generating
    the final financial document for the transaction.
    """
    logger.info(f"--> User {user.username} attempting to create Debit Memo from PR-{purchase_return.id}.")
    logger.debug(f"    Memo Data: {memo_data}")

    if purchase_return.status != PurchaseReturn.Status.COMPLETED:
        logger.error(f"Permission denied: PR-{purchase_return.id} has status '{purchase_return.status}', not 'Completed'.")
        raise PermissionDenied(_("Inventory must be processed before a debit memo can be created."))
    
    if hasattr(purchase_return, 'debit_memo') and purchase_return.debit_memo:
        logger.error(f"Permission denied: A debit memo (DM-{purchase_return.debit_memo.id}) already exists for PR-{purchase_return.id}.")
        raise PermissionDenied(_("A debit memo has already been created for this return."))

    if not all([memo_data.get('memo_number'), memo_data.get('memo_date')]):
        logger.error("Validation failed: Memo Number or Memo Date is missing.")
        raise ValidationError(_("Memo Number and Memo Date are required."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        
        # Calculate total
        total_amount = sum(
            (item.original_receipt.costing_unit_price * Decimal(str(item.quantity_returned)))
            for item in purchase_return.items.all()
        )
        logger.debug(f"    Calculated total debit memo amount: {total_amount}")

        # Create memo
        debit_memo = SupplierDebitMemo.objects.create(
            supplier=purchase_return.supplier,
            memo_number=memo_data['memo_number'],
            memo_date=memo_data['memo_date'],
            total_amount=total_amount.quantize(Decimal('0.001')),
            purchase_return=purchase_return,
            status=SupplierDebitMemo.Status.OPEN
        )
        logger.debug(f"    Created SupplierDebitMemo DM-{debit_memo.id}.")
        
        # Create Journal Entry
        logger.debug("    Creating journal entry for debit memo.")
        settings = GeneralAccountingSettings.load()
        ap_account = settings.accounts_payable
        clearing_account = settings.purchase_returns_clearing_account

        if not ap_account or not clearing_account:
            logger.error("CRITICAL: A/P or Purchase Returns Clearing accounts are not configured.")
            raise ValueError(_("A/P or Purchase Returns Clearing accounts are not configured."))
        
        logger.debug(f"    Accounts loaded: A/P={ap_account.code}, Clearing={clearing_account.code}")

        je_desc = _("Debit Memo %(memo_num)s for return to %(supplier)s") % {
            'memo_num': debit_memo.memo_number, 'supplier': debit_memo.supplier.name
        }
        
        je = JournalEntry.objects.create(
            date=debit_memo.memo_date,
            description=je_desc,
            source_object=debit_memo,
            status=JournalEntry.Status.POSTED
        )
        logger.debug(f"    Created JE-{je.id}.")
        
        # DEBIT: A/P (reduces liability)
        logger.debug(f"      Creating DEBIT line to A/P Account {ap_account.code} for {debit_memo.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, 
            account=ap_account, 
            amount=debit_memo.total_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT, 
            sub_ledger_object=debit_memo.supplier
        )
        
        # CREDIT: Clearing account
        logger.debug(f"      Creating CREDIT line to Clearing Account {clearing_account.code} for {debit_memo.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, 
            account=clearing_account, 
            amount=debit_memo.total_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        
        logger.debug(f"    Validating balance for JE-{je.id}.")
        je.validate_balance()
        
        debit_memo.journal_entry = je
        debit_memo.save(update_fields=['journal_entry'])
        logger.debug(f"    Linked JE-{je.id} to DM-{debit_memo.id} and saved.")
        logger.debug("    Transaction finished.")

    logger.info(f"<-- User {user.username} successfully created Debit Memo {debit_memo.memo_number} for Purchase Return {purchase_return.id}.")
    return debit_memo


# ==============================================================================
#  LANDED COSTS
# ==============================================================================

def post_landed_cost_invoice(invoice: LandedCostInvoice, user) -> JournalEntry:
    """
    Posts a 'Draft' LandedCostInvoice to the General Ledger. It calculates the
    variance between the actual cost and the total accrued estimates from all
    related receipts, posting the difference to a variance account.

    - Debits 'Accrued Landed Costs' to clear the total accrued amount.
    - Debits/Credits 'Landed Cost Variance' for the difference.
    - Credits Accounts Payable to the third-party vendor.
    - Updates the invoice status to 'Awaiting Payment'.
    """
    logger.info(f"--> User {user.username} attempting to post LandedCostInvoice ID {invoice.id}.")
    logger.debug(f"    Invoice details: Number={invoice.invoice_number}, Date={invoice.invoice_date}, Vendor={invoice.vendor.name}, Amount={invoice.total_amount}")

    # --- Validation ---
    if invoice.status != LandedCostInvoice.Status.DRAFT:
        logger.error(f"Validation failed for LC Invoice {invoice.id}: Status is '{invoice.status}', not 'Draft'.")
        raise ValidationError(_("Only draft landed cost invoices can be posted."))
    
    if invoice.journal_entry:
        logger.error(f"Validation failed for LC Invoice {invoice.id}: Already has a journal entry (JE-{invoice.journal_entry.id}).")
        raise ValidationError(_("This invoice has already been posted."))

    if not invoice.purchase_order:
        logger.error(f"Validation failed for LC Invoice {invoice.id}: It is not linked to a Purchase Order.")
        raise ValidationError(_("Landed Cost Invoices must be linked to a Purchase Order to be posted."))

    _check_period_is_open(invoice.invoice_date)
    logger.debug("    Pre-checks passed.")

    # --- Get Accounts ---
    settings = GeneralAccountingSettings.load()
    accrued_account = settings.accrued_landed_costs_account
    ap_account = settings.accounts_payable
    
    # CHANGED: We post the difference to a Clearing account, not directly to Variance.
    # The Allocation Service will later move this from Clearing -> Inventory/Variance.
    clearing_account = settings.landed_costs_clearing_account

    if not all([accrued_account, ap_account, clearing_account]):
        logger.error("CRITICAL: Accrued LC, A/P, or LC Clearing accounts are not configured.")
        raise ValueError(_("Accrued Landed Costs, A/P, or Landed Cost Clearing accounts are not configured."))
    
    logger.debug(f"    Accounts loaded: Accrued={accrued_account.code}, A/P={ap_account.code}, Clearing={clearing_account.code}")

    # --- Calculate Amounts ---
    actual_cost = invoice.total_amount

    # Find all receipts for the linked PO and sum the accrued landed cost component
    related_receipts = InventoryLog.objects.filter(po_item__purchase_order=invoice.purchase_order)
    total_accrued = related_receipts.aggregate(
        total=Sum(F('landed_cost_component') * F('quantity'), output_field=DecimalField())
    )['total'] or Decimal('0.0')
    
    diff_amount = actual_cost - total_accrued
    logger.info(f"    Calculations complete for LC Invoice {invoice.id}: Actual={actual_cost}, Accrued={total_accrued}, Difference={diff_amount}")

    with transaction.atomic():
        logger.debug("    Transaction started.")
        
        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=_("Landed Cost Invoice %(num)s from %(vendor)s for PO %(po)s") % {
                'num': invoice.invoice_number, 'vendor': invoice.vendor.name, 'po': invoice.purchase_order.po_number
            },
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )
        logger.debug(f"    Created JE-{je.id}.")
        
        # DEBIT: Accrued Landed Costs (to clear the accrual)
        logger.debug(f"      Creating DEBIT line to Accrued LC Account {accrued_account.code} for {total_accrued}.")
        JournalEntryLine.objects.create(
            journal_entry=je, 
            account=accrued_account, 
            amount=total_accrued,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        
        # DEBIT/CREDIT: Landed Cost Clearing (The difference to be allocated)
        if diff_amount != 0:
            clearing_type = JournalEntryLine.EntryType.DEBIT if diff_amount > 0 else JournalEntryLine.EntryType.CREDIT
            logger.debug(f"      Creating {clearing_type.upper()} line to Clearing Account {clearing_account.code} for {abs(diff_amount)}.")
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=clearing_account,
                amount=abs(diff_amount),
                entry_type=clearing_type
            )

        # CREDIT: Accounts Payable
        logger.debug(f"      Creating CREDIT line to A/P Account {ap_account.code} for {actual_cost}.")
        JournalEntryLine.objects.create(
            journal_entry=je, 
            account=ap_account, 
            amount=actual_cost,
            entry_type=JournalEntryLine.EntryType.CREDIT, 
            sub_ledger_object=invoice.vendor
        )
        
        logger.debug(f"    Validating balance for JE-{je.id}.")
        je.validate_balance()

        # CHANGED: Status must be AWAITING_ALLOCATION so the user can run the allocation wizard.
        invoice.status = LandedCostInvoice.Status.AWAITING_ALLOCATION
        invoice.journal_entry = je
        invoice.save(update_fields=['status', 'journal_entry'])
        logger.debug(f"    Updated LC Invoice {invoice.id} status to AWAITING_ALLOCATION and linked JE-{je.id}.")
        logger.info(f"<-- Successfully posted LandedCostInvoice ID {invoice.id}.")

    return je


def allocate_landed_costs_from_invoice(landed_cost_invoice_id: int, allocation_data: List[dict], user):
    """
    Allocates costs from a Landed Cost Invoice to specific Inventory Logs.
    
    CRITICAL PRODUCTION LOGIC (PRORATED APPROACH):
    Instead of forcing the FULL cost into the remaining items (which inflates unit cost)
    or updating historical COGS (which requires a massive engine), we split the cost.
    
    1. Calculate % of stock remaining.
    2. Apply that % of the Landed Cost to Inventory (Capitalize).
    3. Apply the rest to Variance (Expense).
    
    This keeps unit costs accurate for future sales while expensing the cost of goods already sold.
    """
    invoice = LandedCostInvoice.objects.get(pk=landed_cost_invoice_id)
    
    if invoice.status != LandedCostInvoice.Status.AWAITING_ALLOCATION:
        raise ValidationError(_("Invoice is not awaiting allocation."))
        
    _check_period_is_open(invoice.invoice_date)

    settings = GeneralAccountingSettings.load()
    accrued_account = settings.accrued_landed_costs_account
    variance_account = settings.landed_cost_variance_account
    clearing_account = settings.landed_costs_clearing_account

    total_allocated = Decimal('0.0')
    products_to_recalc = set()
    
    # Prepare Journal Entry Data
    je_builder_lines = [] 

    with transaction.atomic():
        for item in allocation_data:
            log_id = item['receipt_log_id']
            amount = Decimal(str(item['amount']))
            
            # Lock the log for update
            log = InventoryLog.objects.select_for_update().get(pk=log_id)
            
            # 1. Get Authoritative Remaining Quantity
            # We must use the manager method that calculates this dynamically
            log_with_qty = InventoryLog.objects.with_remaining_quantity().get(pk=log_id)
            remaining_qty = log_with_qty.remaining_quantity
            
            total_allocated += amount

            # 2. Create Allocation Record (Audit Trail)
            LandedCostAllocation.objects.create(
                invoice=invoice,
                receipt_log=log,
                amount=amount
            )

            # 3. PRORATED CALCULATION
            # Avoid division by zero if log was created with 0 qty (unlikely but possible)
            if log.quantity <= 0:
                inventory_share = Decimal('0.0')
                variance_share = amount
            else:
                # Calculate ratio of stock remaining
                # Clamp between 0 and 1 to handle over-consumption/returns edge cases
                ratio = max(Decimal('0.0'), min(Decimal('1.0'), remaining_qty / log.quantity))
                
                inventory_share = (amount * ratio).quantize(Decimal('0.001'))
                variance_share = amount - inventory_share

            logger.info(f"Log {log.id}: Total={log.quantity}, Rem={remaining_qty}. Split: Inv={inventory_share}, Var={variance_share}")

            # 4. Apply Variance Share (Expense)
            if variance_share != 0:
                je_builder_lines.append({
                    'account': variance_account,
                    'amount': variance_share,
                    'type': 'debit',
                    'note': f"LC Variance (Sold Portion) for Log #{log.id}"
                })

            # 5. Apply Inventory Share (Capitalize)
            if inventory_share != 0:
                # We only add the INVENTORY SHARE to the unit cost.
                # This ensures the unit cost increases by the exact amount allocated per unit.
                cost_per_original_unit = inventory_share / log.quantity
                log.costing_unit_price += cost_per_original_unit
                log.landed_cost_component += cost_per_original_unit
                log.save(update_fields=['costing_unit_price', 'landed_cost_component'])
                
                inv_account = _get_product_inventory_account(log.product)
                je_builder_lines.append({
                    'account': inv_account,
                    'amount': inventory_share,
                    'type': 'debit',
                    'note': f"LC Capitalization (On-Hand) to Log #{log.id}"
                })
                
                products_to_recalc.add((log.product_id, log.timestamp))

        # 4. Create the Journal Entry
        je = JournalEntry.objects.create(
            date=timezone.now(), # Allocation happens Now, not invoice date
            description=f"Allocation of Landed Cost Invoice {invoice.invoice_number}",
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )
        
        # Credit the Source (Clearing)
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=total_allocated,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        
        # Debit Destinations
        for line in je_builder_lines:
            JournalEntryLine.objects.create(
                journal_entry=je, account=line['account'], amount=line['amount'],
                entry_type=JournalEntryLine.EntryType.DEBIT
            )
            
        je.validate_balance()
        
        invoice.status = LandedCostInvoice.Status.ALLOCATED
        invoice.save(update_fields=['status'])

    # 5. Trigger Recalculation for touched products
    for prod_id, start_time in products_to_recalc:
        recalculate_cost_history_for_product(prod_id, start_time)


# ==============================================================================
#  RECEIPT VOIDING
# ==============================================================================

def void_inventory_receipt(log_entry: InventoryLog, user, justification: str) -> InventoryLog:
    """
    Voids an inventory receipt non-destructively, with strict safety checks.

    - Reverses the original receipt journal entry.
    - Marks the InventoryLog status as VOIDED.
    - Triggers a cost recalculation.
    """
    from ..models import BatchItem, SupplierInvoiceItem, LandedCostAllocation
    from .accounting.correction_transactions import create_reversing_je_for_correction
    from .costing_service import recalculate_cost_history_for_product

    logger.info(f"--> User '{user.username}' attempting to void InventoryLog ID {log_entry.id}.")

    # --- Strict Pre-checks ---
    if log_entry.status not in ['quarantined', 'released']:
        raise ValidationError(_(f"Cannot void a receipt with status '{log_entry.get_status_display()}'. Only Quarantined or Released receipts can be voided."))
    
    # Check for consumption in production
    if BatchItem.objects.filter(source_log=log_entry).exists():
        raise ValidationError(_("Cannot void this receipt as it has been consumed in a production batch."))

    # Check if it has been invoiced
    if SupplierInvoiceItem.objects.filter(receipt=log_entry).exists():
        raise ValidationError(_("Cannot void this receipt as it has been included in a supplier invoice."))

    # Check for allocated landed costs
    if LandedCostAllocation.objects.filter(receipt_log=log_entry).exists():
        raise ValidationError(_("Cannot void this receipt as landed costs have been allocated to it."))

    with transaction.atomic():
        # Reverse the original JE if the log was released and a JE was created
        if log_entry.status == 'released':
            create_reversing_je_for_correction(
                original_object=log_entry,
                justification=justification,
                user=user,
                correction_date=timezone.now()
            )
            logger.info(f"    Created reversing JE for released InventoryLog ID {log_entry.id}.")

        # Update the status to VOIDED
        log_entry.status = 'voided'
        log_entry.save(update_fields=['status'])
        logger.info(f"    Set status to VOIDED for InventoryLog ID {log_entry.id}.")

    # Trigger cost recalculation outside the transaction
    recalculate_cost_history_for_product(log_entry.product_id, log_entry.timestamp)
    logger.info(f"    Triggered cost recalculation for Product ID {log_entry.product_id}.")

    logger.info(f"<-- Successfully voided InventoryLog ID {log_entry.id}.")
    return log_entry


def apply_payment_to_landed_cost_invoice(user, invoice_id: int, bank_account_id: int, amount: Decimal, payment_date, description: str = ""):
    """
    Creates a Payment and applies it to a Landed Cost Invoice.
    """
    invoice = LandedCostInvoice.objects.select_for_update().get(pk=invoice_id)
    
    # Validation
    if invoice.status not in [LandedCostInvoice.Status.AWAITING_PAYMENT, LandedCostInvoice.Status.PARTIALLY_PAID, LandedCostInvoice.Status.ALLOCATED, LandedCostInvoice.Status.AWAITING_ALLOCATION]:
        # Note: We allow payment even if allocation isn't done yet, provided it's posted (has JE)
        if not invoice.journal_entry:
             raise ValidationError(_("Cannot pay an invoice that hasn't been posted."))
        if invoice.status == LandedCostInvoice.Status.PAID:
             raise ValidationError(_("Invoice is already fully paid."))

    if amount <= 0:
        raise ValidationError(_("Payment amount must be positive."))
    
    if amount > invoice.balance_due:
        raise ValidationError(_(f"Payment amount ({amount}) exceeds balance due ({invoice.balance_due})."))

    _check_period_is_open(payment_date)

    with transaction.atomic():
        # 1. Create Payment Record
        payment = Payment.objects.create(
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            supplier=invoice.vendor,
            bank_account_id=bank_account_id,
            amount=amount,
            payment_date=payment_date,
            description=description or f"Payment for LC Invoice {invoice.invoice_number}",
            source_object=invoice # Link for traceability
        )

        # 2. Create Application Link
        LandedCostPaymentApplication.objects.create(
            payment=payment,
            invoice=invoice,
            amount_applied=amount
        )

        # 3. Update Invoice Status
        invoice.amount_paid += amount
        
        if invoice.balance_due <= Decimal('0.001'):
            invoice.status = LandedCostInvoice.Status.PAID
        else:
            invoice.status = LandedCostInvoice.Status.PARTIALLY_PAID
        
        invoice.save(update_fields=['amount_paid', 'status'])
        
        # Note: The Payment model's post_save signal (or payment service) handles the GL Entry (Cr Bank, Dr AP)