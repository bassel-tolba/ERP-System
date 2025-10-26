# gipcco_project/inventory/services/purchasing_service.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils import timezone

from ..models import (
    SupplierInvoice, JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    InventoryAdjustment, PurchaseReturn, PurchaseOrder, PurchaseOrderItem,
    SupplierDebitMemo, LandedCostInvoice, InventoryLog
)
from .accounting._helpers import _check_period_is_open, _get_product_inventory_account

logger = logging.getLogger(__name__)

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

    # The value in GRNI that needs to be cleared. This is the amount the original receipt
    # credited to the GRNI account.
    grni_clearing_value = (receipt_base_value + receipt_vat_value - receipt_total_wht).quantize(Decimal('0.001'))

    # The final A/P liability is the actual invoice total minus the WHT we pay on the supplier's behalf.
    final_ap_liability = (invoice.actual_subtotal + invoice.actual_vat - receipt_total_wht).quantize(Decimal('0.001'))

    # PPV is the difference between the invoice subtotal and the receipt (PO) subtotal.
    purchase_price_variance = (invoice.actual_subtotal - receipt_base_value).quantize(Decimal('0.001'))

    # The VAT variance is the difference between the actual invoice VAT and the VAT booked at receipt.
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

        # DEBIT: Clear the GRNI account for the value of the receipts
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
                entry_type=ppv_type,
                sub_ledger_object=invoice.supplier
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

        # CREDIT: Accounts Payable for the final liability
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
        invoice.total_amount = actual_invoice_total # Update total amount to actual
        invoice.save(update_fields=['status', 'journal_entry', 'total_amount'])
        logger.info(f"<-- Successfully posted SupplierInvoice ID {invoice.id}.")

    return je


def allocate_landed_costs(invoice: SupplierInvoice):
    """
    Allocates landed costs associated with a supplier invoice to the
    costing_unit_price of the related inventory receipts.

    This should be done BEFORE posting the invoice.
    """
    from ..models import InventoryLog
    from .costing_service import recalculate_cost_history_for_product
    logger.info(f"--> Attempting to allocate landed costs for SupplierInvoice ID {invoice.id}.")
    logger.debug(f"    (This is the old method, `allocate_landed_costs_from_invoice` is preferred).")

    if invoice.status != SupplierInvoice.InvoiceStatus.DRAFT:
        logger.error(f"Validation failed for Invoice ID {invoice.id}: Status is '{invoice.status}', not 'Draft'.")
        raise ValidationError(_("Landed costs can only be allocated on 'Draft' invoices."))

    total_landed_cost = invoice.landed_costs.aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    if total_landed_cost <= 0:
        logger.warning(f"No landed costs to allocate for Invoice ID {invoice.id}. Total is {total_landed_cost}.")
        raise ValueError(_("No landed costs to allocate."))
    logger.debug(f"    Total landed cost to allocate: {total_landed_cost}")

    receipts = list(invoice.items.select_related('receipt').values_list('receipt', flat=True))
    receipt_logs = InventoryLog.objects.filter(pk__in=receipts)
    logger.debug(f"    Found {len(receipt_logs)} receipt logs to allocate costs to: {[r.id for r in receipt_logs]}")
    
    total_receipt_value = sum(
        (log.base_unit_price * Decimal(str(log.quantity))) for log in receipt_logs
    )
    logger.debug(f"    Total base value of receipts: {total_receipt_value}")

    if total_receipt_value <= 0:
        logger.error(f"Cannot allocate landed costs for Invoice ID {invoice.id}: Total receipt value is zero.")
        raise ValueError(_("Cannot allocate landed costs to receipts with zero value."))

    with transaction.atomic():
        logger.debug("    Transaction started for cost allocation.")
        products_to_recalculate = set()
        earliest_receipt_date = None

        for log in receipt_logs:
            receipt_value = log.base_unit_price * Decimal(str(log.quantity))
            allocation_ratio = receipt_value / total_receipt_value
            allocated_cost = (total_landed_cost * allocation_ratio).quantize(Decimal('0.001'))
            
            landed_cost_per_unit = (allocated_cost / Decimal(str(log.quantity))).quantize(Decimal('0.001'))
            logger.debug(f"      Processing Receipt ID {log.id} (Product ID {log.product_id}):")
            logger.debug(f"        - Receipt Value: {receipt_value}")
            logger.debug(f"        - Allocation Ratio: {allocation_ratio}")
            logger.debug(f"        - Allocated Cost: {allocated_cost}")
            logger.debug(f"        - Landed Cost Per Unit: {landed_cost_per_unit}")

            # Update the log's cost fields
            log.landed_cost_component = landed_cost_per_unit
            log.costing_unit_price += landed_cost_per_unit
            log.save(update_fields=['landed_cost_component', 'costing_unit_price'])
            logger.debug(f"        - Updated Receipt ID {log.id}: New Costing Unit Price={log.costing_unit_price}")

            products_to_recalculate.add(log.product_id)
            if earliest_receipt_date is None or log.release_timestamp.date() < earliest_receipt_date:
                earliest_receipt_date = log.release_timestamp.date()
        
        logger.debug(f"    Transaction finished. Earliest receipt date: {earliest_receipt_date}")

    # After allocation, trigger a cost recalculation for all affected products
    # starting from the date of the earliest receipt in this allocation.
    logger.debug(f"    Products needing cost history recalculation: {products_to_recalculate}")
    for product_id in products_to_recalculate:
        logger.info(f"Triggering cost recalculation for Product ID {product_id} from {earliest_receipt_date}.")
        recalculate_cost_history_for_product(product_id, start_datetime=earliest_receipt_date)

    logger.info(f"<-- Successfully allocated {total_landed_cost} to {len(receipt_logs)} receipts for Invoice ID {invoice.id}.")


def create_purchase_return(user, return_data: dict, items_data: list) -> PurchaseReturn:
    """
    Creates a Purchase Return and its items, validating that the return quantity
    does not exceed the available quantity from the original receipt.
    """
    from ..models import PurchaseReturn, PurchaseReturnItem, InventoryLog
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
            receipt = InventoryLog.objects.get(pk=receipt_id)
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
        raise PermissionError(_("This return has already been processed."))

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


def create_debit_memo_from_return(user, purchase_return: PurchaseReturn, memo_data: dict) -> 'SupplierDebitMemo':
    """
    Creates a SupplierDebitMemo from a processed Purchase Return, generating
    the final financial document for the transaction.
    """
    from ..models import SupplierDebitMemo
    logger.info(f"--> User {user.username} attempting to create Debit Memo from PR-{purchase_return.id}.")
    logger.debug(f"    Memo Data: {memo_data}")

    if purchase_return.status != PurchaseReturn.Status.COMPLETED:
        logger.error(f"Permission denied: PR-{purchase_return.id} has status '{purchase_return.status}', not 'Completed'.")
        raise PermissionError(_("Inventory must be processed before a debit memo can be created."))
    
    if hasattr(purchase_return, 'debit_memo') and purchase_return.debit_memo:
        logger.error(f"Permission denied: A debit memo (DM-{purchase_return.debit_memo.id}) already exists for PR-{purchase_return.id}.")
        raise PermissionError(_("A debit memo has already been created for this return."))

    if not all([memo_data.get('memo_number'), memo_data.get('memo_date')]):
        logger.error("Validation failed: Memo Number or Memo Date is missing.")
        raise ValidationError(_("Memo Number and Memo Date are required."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        total_amount = sum(
            (item.original_receipt.costing_unit_price * Decimal(str(item.quantity_returned)))
            for item in purchase_return.items.all()
        )
        logger.debug(f"    Calculated total debit memo amount: {total_amount}")

        debit_memo = SupplierDebitMemo.objects.create(
            supplier=purchase_return.supplier,
            memo_number=memo_data['memo_number'],
            memo_date=memo_data['memo_date'],
            total_amount=total_amount.quantize(Decimal('0.001')),
            purchase_return=purchase_return,
            status=SupplierDebitMemo.Status.OPEN
        )
        logger.debug(f"    Created SupplierDebitMemo DM-{debit_memo.id}.")
        
        # --- NEW: Create the Journal Entry for the Debit Memo ---
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
        # Debit A/P to reduce liability
        logger.debug(f"      Creating DEBIT line to A/P Account {ap_account.code} for {debit_memo.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=debit_memo.total_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=debit_memo.supplier
        )
        # Credit the clearing account to offset the inventory adjustment
        logger.debug(f"      Creating CREDIT line to Clearing Account {clearing_account.code} for {debit_memo.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=debit_memo.total_amount,
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


def void_inventory_receipt(
    log_entry: 'InventoryLog', 
    user, 
    justification: str
) -> 'InventoryLog':
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



def create_purchase_order(user, po_data: dict, items_data: list) -> PurchaseOrder:
    """
    Creates a new Purchase Order and its items from validated data.
    """
    logger.info(f"--> User {user.username} attempting to create a Purchase Order.")
    logger.debug(f"    PO Data: {po_data}")
    logger.debug(f"    Items Data: {items_data}")

    if not all([po_data.get('po_number'), po_data.get('supplier_id'), po_data.get('order_date')]):
        logger.error("Validation failed: PO Number, Supplier, or Order Date is missing.")
        raise ValidationError(_("PO Number, Supplier, and Order Date are required."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exists():
        logger.error(f"Validation failed: PO Number '{po_data['po_number']}' already exists.")
        raise ValidationError(_("A Purchase Order with this number already exists."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        po = PurchaseOrder.objects.create(
            po_number=po_data['po_number'],
            supplier_id=po_data['supplier_id'],
            order_date=po_data['order_date']
        )
        logger.debug(f"    Created PurchaseOrder header PO-{po.id} with number {po.po_number}.")

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
                    base_price_per_unit=Decimal(item_data['base_price_per_unit']),
                    vat_rate=Decimal(item_data.get('vat_rate', '0.14')),
                    withholding_tax_rate=Decimal(item_data.get('withholding_tax_rate', '0.01'))
                )
            )
        
        if not items_to_create:
            logger.error("Validation failed: No items were provided for the PO.")
            raise ValidationError(_("A Purchase Order must have at least one item."))
            
        logger.debug(f"    Bulk creating {len(items_to_create)} PurchaseOrderItem objects.")
        PurchaseOrderItem.objects.bulk_create(items_to_create)
        logger.debug("    Transaction finished.")

    logger.info(f"<-- User {user.username} successfully created Purchase Order {po.po_number}.")
    return po


def update_purchase_order(user, po: PurchaseOrder, po_data: dict, items_data: list) -> PurchaseOrder:
    """
    Updates an existing Purchase Order and its items.
    """
    logger.info(f"--> User {user.username} attempting to update Purchase Order {po.po_number} (ID: {po.id}).")
    logger.debug(f"    New PO Data: {po_data}")
    logger.debug(f"    New Items Data: {items_data}")

    if po.items.filter(receipts__isnull=False).exists():
        logger.error(f"Permission denied: Cannot edit PO {po.po_number} because it has received items.")
        raise PermissionError(_("Cannot edit a Purchase Order that has received items."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exclude(pk=po.pk).exists():
        logger.error(f"Validation failed: Another PO with number '{po_data['po_number']}' already exists.")
        raise ValidationError(_("Another Purchase Order with this number already exists."))

    with transaction.atomic():
        logger.debug("    Transaction started.")
        po.po_number = po_data['po_number']
        po.supplier_id = po_data['supplier_id']
        po.order_date = po_data['order_date']
        po.save()
        logger.debug(f"    Updated PO header for {po.po_number}.")

        logger.debug("    Deleting existing items.")
        po.items.all().delete()

        items_to_create = []
        for item_data in items_data:
            logger.debug(f"      Processing new item: {item_data}")
            items_to_create.append(
                PurchaseOrderItem(
                    purchase_order=po,
                    product_id=item_data['product_id'],
                    quantity_ordered=float(item_data['quantity']),
                    base_price_per_unit=Decimal(item_data['base_price_per_unit']),
                    vat_rate=Decimal(item_data.get('vat_rate', '0.14')),
                    withholding_tax_rate=Decimal(item_data.get('withholding_tax_rate', '0.01'))
                )
            )
        
        if not items_to_create:
            logger.error("Validation failed: An updated PO must have at least one item.")
            raise ValidationError(_("A Purchase Order must have at least one item."))

        logger.debug(f"    Bulk creating {len(items_to_create)} new PurchaseOrderItem objects.")
        PurchaseOrderItem.objects.bulk_create(items_to_create)
        logger.debug("    Transaction finished.")

    logger.info(f"<-- User {user.username} successfully updated Purchase Order {po.po_number}.")
    return po


def update_po_status_after_receipt(inventory_log_id: Optional[int], is_final_receipt: bool, old_po_item_id: Optional[int] = None):
    """
    Updates the status of a Purchase Order based on its received items.
    This should be triggered after an InventoryLog is saved or deleted.

    Args:
        inventory_log_id: The ID of the newly created/updated InventoryLog. Can be None if a log was deleted.
        is_final_receipt: A boolean flag from the UI indicating if an under-delivery should close the PO line.
        old_po_item_id: The ID of a PurchaseOrderItem that was previously linked to a log, used for deletions or edits.
    """
    from ..models import InventoryLog, PurchaseOrder, PurchaseOrderItem
    from django.db.models import Sum, F, FloatField, Q
    from django.db.models.functions import Coalesce
    logger.debug(f"--> Triggered PO status update. Log ID: {inventory_log_id}, Is Final: {is_final_receipt}, Old PO Item ID: {old_po_item_id}")

    po_to_update = None
    po_item_to_check = None

    if inventory_log_id:
        try:
            log = InventoryLog.objects.select_related('po_item__purchase_order').get(pk=inventory_log_id)
            if log.po_item:
                po_to_update = log.po_item.purchase_order
                po_item_to_check = log.po_item
                logger.debug(f"    Found PO {po_to_update.po_number} via InventoryLog {inventory_log_id}.")
        except InventoryLog.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent InventoryLog ID {inventory_log_id}.")
            # Fall through to handle old_po_item_id if it exists
    
    if not po_to_update and old_po_item_id:
        try:
            old_item = PurchaseOrderItem.objects.select_related('purchase_order').get(pk=old_po_item_id)
            po_to_update = old_item.purchase_order
            logger.debug(f"    Found PO {po_to_update.po_number} via old_po_item_id {old_po_item_id}.")
            # In deletion/edit cases, we don't have a specific new item to check,
            # the aggregation will handle the overall status.
        except PurchaseOrderItem.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent old_po_item_id {old_po_item_id}.")
            return

    if not po_to_update:
        logger.info("update_po_status_after_receipt called with no associated PO to update. Exiting.")
        return

    # --- Handle manual closing of an under-delivered item ---
    if po_item_to_check and is_final_receipt:
        logger.debug(f"    'is_final_receipt' is True for PO Item {po_item_to_check.id}. Checking for under-delivery.")
        total_received_for_item = po_item_to_check.receipts.aggregate(
            total=Coalesce(Sum('quantity'), 0.0, output_field=FloatField())
        )['total']
        logger.debug(f"    PO Item {po_item_to_check.id}: Ordered={po_item_to_check.quantity_ordered}, Total Received={total_received_for_item}")
        if total_received_for_item < po_item_to_check.quantity_ordered:
            po_item_to_check.is_closed = True
            po_item_to_check.save(update_fields=['is_closed'])
            logger.info(f"PO Item ID {po_item_to_check.id} for PO {po_to_update.po_number} was manually closed short.")

    # --- Update overall PO status based on all its items ---
    logger.debug(f"    Recalculating overall status for PO {po_to_update.po_number}.")
    all_items = po_to_update.items.all()
    
    # An item is considered "complete" if it's fully received OR manually closed.
    completed_items_count = all_items.annotate(
        total_received=Coalesce(Sum('receipts__quantity'), 0.0, output_field=FloatField())
    ).filter(
        Q(total_received__gte=F('quantity_ordered')) | Q(is_closed=True)
    ).count()

    total_received_on_po = all_items.aggregate(
        total=Coalesce(Sum('receipts__quantity'), 0.0, output_field=FloatField())
    )['total']
    logger.debug(f"    PO {po_to_update.po_number}: Total Items={all_items.count()}, Completed Items={completed_items_count}, Total Qty Received={total_received_on_po}")

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


def post_landed_cost_invoice(invoice: 'LandedCostInvoice') -> 'JournalEntry':
    """
    Posts a 'Draft' LandedCostInvoice to the General Ledger.

    - Debits a 'Landed Costs Clearing' account.
    - Credits Accounts Payable to the third-party vendor.
    - Updates the invoice status to 'Awaiting Allocation'.
    """
    from ..models import LandedCostInvoice

    logger.info(f"--> Attempting to post LandedCostInvoice ID {invoice.id}.")
    logger.debug(f"    Invoice details: Number={invoice.invoice_number}, Date={invoice.invoice_date}, Vendor={invoice.vendor.name}, Amount={invoice.total_amount}")

    if invoice.status != LandedCostInvoice.Status.DRAFT:
        logger.error(f"Validation failed for LC Invoice {invoice.id}: Status is '{invoice.status}', not 'Draft'.")
        raise ValidationError(_("Only draft landed cost invoices can be posted."))
    if invoice.journal_entry:
        logger.error(f"Validation failed for LC Invoice {invoice.id}: Already has a journal entry (JE-{invoice.journal_entry.id}).")
        raise ValidationError(_("This invoice has already been posted."))

    _check_period_is_open(invoice.invoice_date)
    logger.debug("    Pre-checks passed.")

    settings = GeneralAccountingSettings.load()
    clearing_account = settings.landed_costs_clearing_account
    ap_account = settings.accounts_payable

    if not all([clearing_account, ap_account]):
        logger.error("CRITICAL: Landed Costs Clearing or A/P accounts are not configured.")
        raise ValueError(_("Landed Costs Clearing or A/P accounts are not configured."))
    logger.debug(f"    Accounts loaded: Clearing={clearing_account.code}, A/P={ap_account.code}")

    with transaction.atomic():
        logger.debug("    Transaction started.")
        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=_("Landed Cost Invoice %(num)s from %(vendor)s") % {
                'num': invoice.invoice_number, 'vendor': invoice.vendor.name
            },
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )
        logger.debug(f"    Created JE-{je.id}.")
        # Debit the clearing account
        logger.debug(f"      Creating DEBIT line to Clearing Account {clearing_account.code} for {invoice.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=invoice.total_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Accounts Payable
        logger.debug(f"      Creating CREDIT line to A/P Account {ap_account.code} for {invoice.total_amount}.")
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=invoice.total_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT, sub_ledger_object=invoice.vendor
        )
        logger.debug(f"    Validating balance for JE-{je.id}.")
        je.validate_balance()

        invoice.status = LandedCostInvoice.Status.AWAITING_ALLOCATION
        invoice.journal_entry = je
        invoice.save(update_fields=['status', 'journal_entry'])
        logger.debug(f"    Updated LC Invoice {invoice.id} status to AWAITING_ALLOCATION and linked JE-{je.id}.")
        logger.info(f"<-- Successfully posted LandedCostInvoice ID {invoice.id}.")

    return je


def allocate_landed_costs_from_invoice(
    landed_cost_invoice_ids: list[int],
    receipt_log_ids: list[int],
    user
) -> None:
    """
    REDEFINED: Allocates landed costs to receipts using a non-destructive revaluation model.
    - It no longer triggers a historical cost recalculation that modifies past transactions.
    - It creates a journal entry that splits the landed cost debit between the inventory
      revaluation account (for on-hand stock) and a manufacturing variance account (for
      stock that has already been sold).
    - It updates the product's moving average cost for future transactions only.
    """
    from ..models import LandedCostInvoice, InventoryLog, LandedCostAllocation, Product
    from .costing_service import get_inventory_state_at_datetime, recalculate_cost_history_for_product
    logger.info(f"--> User {user.username} attempting to allocate landed costs with revaluation logic.")
    logger.debug(f"    Invoice IDs: {landed_cost_invoice_ids}, Receipt Log IDs: {receipt_log_ids}")

    if not landed_cost_invoice_ids or not receipt_log_ids:
        raise ValidationError(_("You must provide both invoices and receipts to allocate."))

    with transaction.atomic():
        invoices = LandedCostInvoice.objects.filter(pk__in=landed_cost_invoice_ids)
        receipts = InventoryLog.objects.select_related('product').filter(pk__in=receipt_log_ids)
        
        total_cost_to_allocate = invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.0')
        total_receipt_value = sum((log.base_unit_price * Decimal(str(log.quantity))) for log in receipts)

        if total_cost_to_allocate <= 0:
            raise ValidationError(_("Selected invoices have no cost to allocate."))
        if total_receipt_value <= 0:
            raise ValidationError(_("Selected receipts have a total value of zero, cannot allocate costs."))

        settings = GeneralAccountingSettings.load()
        clearing_account = settings.landed_costs_clearing_account
        variance_account = settings.manufacturing_variance_account
        revaluation_account = settings.inventory_revaluation_account

        if not all([clearing_account, variance_account, revaluation_account]):
            raise ValueError(_("Landed Cost Clearing, Manufacturing Variance, or Inventory Revaluation accounts are not configured."))

        allocation_date = timezone.now()
        _check_period_is_open(allocation_date.date()) # <-- FINAL SAFEGUARD ADDED

        je = JournalEntry.objects.create(
            date=allocation_date,
            description=_(
                "تخصيص تكاليف إضافية من %(invoice_count)d فاتورة إلى %(receipt_count)d إيصال استلام"
            ) % {'invoice_count': invoices.count(), 'receipt_count': receipts.count()},
            notes=f"Allocation performed by {user.username}",
            status=JournalEntry.Status.POSTED
        )
        
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=total_cost_to_allocate,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )

        costs_by_product = {}
        products_to_recalculate = set()

        for log in receipts:
            receipt_value = log.base_unit_price * Decimal(str(log.quantity))
            proportion = receipt_value / total_receipt_value
            cost_to_add = (total_cost_to_allocate * proportion).quantize(Decimal('0.001'))
            cost_per_unit_to_add = cost_to_add / Decimal(str(log.quantity))
            
            log.landed_cost_component += cost_per_unit_to_add
            log.costing_unit_price += cost_per_unit_to_add
            log.save(update_fields=['landed_cost_component', 'costing_unit_price'])
            
            products_to_recalculate.add(log.product_id)
            
            if log.product_id not in costs_by_product:
                costs_by_product[log.product_id] = {'total_cost': Decimal('0.0'), 'total_qty': Decimal('0.0'), 'product': log.product}
            
            costs_by_product[log.product_id]['total_cost'] += cost_to_add
            costs_by_product[log.product_id]['total_qty'] += Decimal(str(log.quantity))

            for inv in invoices:
                # Simplified audit trail
                LandedCostAllocation.objects.create(
                    landed_cost_item=inv.items.first(), receipt_log=log,
                    allocated_amount=cost_to_add / invoices.count(), journal_entry=je
                )

        for product_id, data in costs_by_product.items():
            total_cost_for_product = data['total_cost']
            total_qty_from_receipts = data['total_qty']
            product = data['product']

            state = get_inventory_state_at_datetime(product_id, allocation_date)
            current_on_hand = state.get('quantity', Decimal('0.0'))

            qty_to_revalue_in_inventory = min(total_qty_from_receipts, current_on_hand)
            cost_per_unit = total_cost_for_product / total_qty_from_receipts

            cost_for_inventory = (qty_to_revalue_in_inventory * cost_per_unit).quantize(Decimal('0.001'))
            cost_for_variance = (total_cost_for_product - cost_for_inventory).quantize(Decimal('0.001'))

            if cost_for_inventory > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je, account=revaluation_account, amount=cost_for_inventory,
                    entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=product
                )
            if cost_for_variance > 0:
                JournalEntryLine.objects.create(
                    journal_entry=je, account=variance_account, amount=cost_for_variance,
                    entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=product
                )

        je.validate_balance()
        invoices.update(status=LandedCostInvoice.Status.FULLY_ALLOCATED)

    # --- Trigger a forward-looking MAC update outside the transaction ---
    for product_id in products_to_recalculate:
        recalculate_cost_history_for_product(product_id, timezone.now())

    logger.info(f"<-- User {user.username} successfully allocated {total_cost_to_allocate} from {invoices.count()} invoices to {receipts.count()} receipts.")

