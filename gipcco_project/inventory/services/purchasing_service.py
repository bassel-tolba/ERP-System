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
    SupplierDebitMemo, LandedCostInvoice
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

    # --- 1. Pre-checks and Guards ---
    if invoice.status != SupplierInvoice.InvoiceStatus.DRAFT:
        raise ValidationError(_("Only invoices in 'Draft' status can be posted."))
    
    if not invoice.items.exists():
        raise ValidationError(_("Cannot post an invoice with no items."))

    if invoice.journal_entry:
        raise ValidationError(_("This invoice has already been posted and has a journal entry linked."))

    if not invoice.actual_subtotal or not invoice.actual_vat:
        raise ValidationError(_("Actual subtotal and VAT from the physical invoice must be entered before posting."))

    _check_period_is_open(invoice.invoice_date)

    # --- 2. Get Accounts from Configuration ---
    settings = GeneralAccountingSettings.load()
    grni_account = settings.goods_received_not_invoiced_account
    ap_account = settings.accounts_payable
    ppv_account = settings.purchase_price_variance_account
    vat_account = settings.vat_receivable

    if not all([grni_account, ap_account, ppv_account, vat_account]):
        raise ValueError(_("GRNI, A/P, PPV, or VAT accounts are not configured in General Accounting Settings."))

    # --- 3. Calculate Amounts ---
    # --- 3. Calculate Amounts ---
    receipt_base_value = Decimal('0.0')
    receipt_vat_value = Decimal('0.0')
    receipt_total_wht = Decimal('0.0')

    for item in invoice.items.select_related('receipt').all():
        receipt = item.receipt
        if receipt:
            receipt_base_value += receipt.base_unit_price * Decimal(str(receipt.quantity))
            receipt_vat_value += receipt.vat_amount
            receipt_total_wht += receipt.withholding_tax_amount

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

    # --- 4. Create Journal Entry and Lines ---
    with transaction.atomic():
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

        # DEBIT: Clear the GRNI account for the value of the receipts
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=grni_account,
            amount=grni_clearing_value,
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=invoice.supplier
        )

        # DEBIT/CREDIT: Purchase Price Variance
        if purchase_price_variance != 0:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=ppv_account,
                amount=abs(purchase_price_variance),
                entry_type=JournalEntryLine.EntryType.DEBIT if purchase_price_variance > 0 else JournalEntryLine.EntryType.CREDIT,
                sub_ledger_object=invoice.supplier
            )

        # DEBIT/CREDIT: VAT Variance
        if vat_variance != 0:
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=vat_account,
                amount=abs(vat_variance),
                entry_type=JournalEntryLine.EntryType.DEBIT if vat_variance > 0 else JournalEntryLine.EntryType.CREDIT
            )

        # CREDIT: Accounts Payable for the final liability
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=ap_account,
            amount=final_ap_liability,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=invoice.supplier
        )

        je.validate_balance()
        logger.info(f"    Successfully created JE-{je.id} for Invoice ID {invoice.id}.")

        # --- 5. Update Invoice Status ---
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

    if invoice.status != SupplierInvoice.InvoiceStatus.DRAFT:
        raise ValidationError(_("Landed costs can only be allocated on 'Draft' invoices."))

    total_landed_cost = invoice.landed_costs.aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
    if total_landed_cost <= 0:
        raise ValueError(_("No landed costs to allocate."))

    receipts = list(invoice.items.select_related('receipt').values_list('receipt', flat=True))
    receipt_logs = InventoryLog.objects.filter(pk__in=receipts)
    
    total_receipt_value = sum(
        (log.base_unit_price * Decimal(str(log.quantity))) for log in receipt_logs
    )

    if total_receipt_value <= 0:
        raise ValueError(_("Cannot allocate landed costs to receipts with zero value."))

    with transaction.atomic():
        products_to_recalculate = set()
        earliest_receipt_date = None

        for log in receipt_logs:
            receipt_value = log.base_unit_price * Decimal(str(log.quantity))
            allocation_ratio = receipt_value / total_receipt_value
            allocated_cost = (total_landed_cost * allocation_ratio).quantize(Decimal('0.001'))
            
            landed_cost_per_unit = (allocated_cost / Decimal(str(log.quantity))).quantize(Decimal('0.001'))

            # Update the log's cost fields
            log.landed_cost_component = landed_cost_per_unit
            log.costing_unit_price += landed_cost_per_unit
            log.save(update_fields=['landed_cost_component', 'costing_unit_price'])

            products_to_recalculate.add(log.product_id)
            if earliest_receipt_date is None or log.release_timestamp.date() < earliest_receipt_date:
                earliest_receipt_date = log.release_timestamp.date()

    # After allocation, trigger a cost recalculation for all affected products
    # starting from the date of the earliest receipt in this allocation.
    for product_id in products_to_recalculate:
        logger.info(f"Triggering cost recalculation for Product ID {product_id} from {earliest_receipt_date}.")
        recalculate_cost_history_for_product(product_id, start_datetime=earliest_receipt_date)

    logger.info(f"Successfully allocated {total_landed_cost} to {len(receipt_logs)} receipts for Invoice ID {invoice.id}.")


def create_purchase_return(user, return_data: dict, items_data: list) -> PurchaseReturn:
    """
    Creates a Purchase Return and its items, validating that the return quantity
    does not exceed the available quantity from the original receipt.
    """
    from ..models import PurchaseReturn, PurchaseReturnItem, InventoryLog

    if not all([return_data.get('supplier_id'), return_data.get('return_date')]):
        raise ValidationError(_("Supplier and Return Date are required."))

    with transaction.atomic():
        pr = PurchaseReturn.objects.create(
            supplier_id=return_data['supplier_id'],
            return_date=return_data['return_date'],
            notes=return_data.get('notes', '')
        )

        items_to_create = []
        for item_data in items_data:
            receipt = InventoryLog.objects.get(pk=item_data['original_receipt_id'])
            quantity_to_return = float(item_data['quantity_returned'])
            
            if quantity_to_return <= 0:
                raise ValidationError(_("Return quantity must be a positive number."))

            # Get quantity already returned against this receipt
            already_returned = receipt.purchase_return_items.aggregate(
                total=Sum('quantity_returned')
            )['total'] or 0.0
            
            available_to_return = receipt.quantity - already_returned

            if quantity_to_return > available_to_return:
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
        
        if not items_to_create:
            raise ValidationError(_("A purchase return must have at least one item."))
            
        PurchaseReturnItem.objects.bulk_create(items_to_create)

    logger.info(f"User {user} created Purchase Return {pr.id}.")
    return pr


def process_inventory_return(user, purchase_return: PurchaseReturn) -> PurchaseReturn:
    """
    Processes the inventory movement for a purchase return by creating
    a negative inventory adjustment for each item.
    """
    if purchase_return.status != PurchaseReturn.Status.PENDING:
        raise PermissionError(_("This return has already been processed."))

    with transaction.atomic():
        for item in purchase_return.items.all():
            InventoryAdjustment.objects.create(
                product=item.original_receipt.product,
                adjustment_date=purchase_return.return_date,
                adjustment_quantity=-item.quantity_returned,
                reason_code=InventoryAdjustment.ReasonCode.RETURN_TO_SUPPLIER,
                cost_at_adjustment=item.original_receipt.costing_unit_price,
                notes=f"Return for PR #{purchase_return.id}",
                source_purchase_return_item=item
            )
        
        purchase_return.status = PurchaseReturn.Status.COMPLETED
        purchase_return.save(update_fields=['status'])
    
    logger.info(f"User {user} processed inventory movements for Purchase Return {purchase_return.id}.")
    return purchase_return


def create_debit_memo_from_return(user, purchase_return: PurchaseReturn, memo_data: dict) -> 'SupplierDebitMemo':
    """
    Creates a SupplierDebitMemo from a processed Purchase Return, generating
    the final financial document for the transaction.
    """
    from ..models import SupplierDebitMemo

    if purchase_return.status != PurchaseReturn.Status.COMPLETED:
        raise PermissionError(_("Inventory must be processed before a debit memo can be created."))
    
    if hasattr(purchase_return, 'debit_memo') and purchase_return.debit_memo:
        raise PermissionError(_("A debit memo has already been created for this return."))

    if not all([memo_data.get('memo_number'), memo_data.get('memo_date')]):
        raise ValidationError(_("Memo Number and Memo Date are required."))

    with transaction.atomic():
        total_amount = sum(
            (item.original_receipt.costing_unit_price * Decimal(str(item.quantity_returned)))
            for item in purchase_return.items.all()
        )

        debit_memo = SupplierDebitMemo.objects.create(
            supplier=purchase_return.supplier,
            memo_number=memo_data['memo_number'],
            memo_date=memo_data['memo_date'],
            total_amount=total_amount.quantize(Decimal('0.001')),
            purchase_return=purchase_return,
            status=SupplierDebitMemo.Status.OPEN
        )
        
        # --- NEW: Create the Journal Entry for the Debit Memo ---
        settings = GeneralAccountingSettings.load()
        ap_account = settings.accounts_payable
        clearing_account = settings.purchase_returns_clearing_account

        if not ap_account or not clearing_account:
            raise ValueError(_("A/P or Purchase Returns Clearing accounts are not configured."))

        je_desc = _("Debit Memo %(memo_num)s for return to %(supplier)s") % {
            'memo_num': debit_memo.memo_number, 'supplier': debit_memo.supplier.name
        }
        je = JournalEntry.objects.create(
            date=debit_memo.memo_date,
            description=je_desc,
            source_object=debit_memo,
            status=JournalEntry.Status.POSTED
        )
        # Debit A/P to reduce liability
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=debit_memo.total_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT, sub_ledger_object=debit_memo.supplier
        )
        # Credit the clearing account to offset the inventory adjustment
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=debit_memo.total_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        je.validate_balance()
        debit_memo.journal_entry = je
        debit_memo.save(update_fields=['journal_entry'])

    logger.info(f"User {user} created Debit Memo {debit_memo.memo_number} for Purchase Return {purchase_return.id}.")
    return debit_memo




def create_purchase_order(user, po_data: dict, items_data: list) -> PurchaseOrder:
    """
    Creates a new Purchase Order and its items from validated data.
    """
    if not all([po_data.get('po_number'), po_data.get('supplier_id'), po_data.get('order_date')]):
        raise ValidationError(_("PO Number, Supplier, and Order Date are required."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exists():
        raise ValidationError(_("A Purchase Order with this number already exists."))

    with transaction.atomic():
        po = PurchaseOrder.objects.create(
            po_number=po_data['po_number'],
            supplier_id=po_data['supplier_id'],
            order_date=po_data['order_date']
        )

        items_to_create = []
        for item_data in items_data:
            if not all([item_data.get('product_id'), item_data.get('quantity'), item_data.get('base_price_per_unit')]):
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
            raise ValidationError(_("A Purchase Order must have at least one item."))
            
        PurchaseOrderItem.objects.bulk_create(items_to_create)

    logger.info(f"User {user} created Purchase Order {po.po_number}.")
    return po


def update_purchase_order(user, po: PurchaseOrder, po_data: dict, items_data: list) -> PurchaseOrder:
    """
    Updates an existing Purchase Order and its items.
    """
    if po.items.filter(receipts__isnull=False).exists():
        raise PermissionError(_("Cannot edit a Purchase Order that has received items."))

    if PurchaseOrder.objects.filter(po_number=po_data['po_number']).exclude(pk=po.pk).exists():
        raise ValidationError(_("Another Purchase Order with this number already exists."))

    with transaction.atomic():
        po.po_number = po_data['po_number']
        po.supplier_id = po_data['supplier_id']
        po.order_date = po_data['order_date']
        po.save()

        po.items.all().delete()

        items_to_create = []
        for item_data in items_data:
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
            raise ValidationError(_("A Purchase Order must have at least one item."))

        PurchaseOrderItem.objects.bulk_create(items_to_create)

    logger.info(f"User {user} updated Purchase Order {po.po_number}.")
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

    po_to_update = None
    po_item_to_check = None

    if inventory_log_id:
        try:
            log = InventoryLog.objects.select_related('po_item__purchase_order').get(pk=inventory_log_id)
            if log.po_item:
                po_to_update = log.po_item.purchase_order
                po_item_to_check = log.po_item
        except InventoryLog.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent InventoryLog ID {inventory_log_id}.")
            # Fall through to handle old_po_item_id if it exists
    
    if not po_to_update and old_po_item_id:
        try:
            old_item = PurchaseOrderItem.objects.select_related('purchase_order').get(pk=old_po_item_id)
            po_to_update = old_item.purchase_order
            # In deletion/edit cases, we don't have a specific new item to check,
            # the aggregation will handle the overall status.
        except PurchaseOrderItem.DoesNotExist:
            logger.warning(f"update_po_status_after_receipt called with non-existent old_po_item_id {old_po_item_id}.")
            return

    if not po_to_update:
        logger.info("update_po_status_after_receipt called with no associated PO to update.")
        return

    # --- Handle manual closing of an under-delivered item ---
    if po_item_to_check and is_final_receipt:
        total_received_for_item = po_item_to_check.receipts.aggregate(
            total=Coalesce(Sum('quantity'), 0.0, output_field=FloatField())
        )['total']
        if total_received_for_item < po_item_to_check.quantity_ordered:
            po_item_to_check.is_closed = True
            po_item_to_check.save(update_fields=['is_closed'])
            logger.info(f"PO Item ID {po_item_to_check.id} for PO {po_to_update.po_number} was manually closed short.")

    # --- Update overall PO status based on all its items ---
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

    if completed_items_count == all_items.count():
        po_to_update.status = PurchaseOrder.Status.COMPLETED
    elif total_received_on_po > 0:
        po_to_update.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
    else:
        po_to_update.status = PurchaseOrder.Status.PENDING
    
    po_to_update.save(update_fields=['status'])
    logger.info(f"Updated status for PO {po_to_update.po_number} to {po_to_update.status}.")


def post_landed_cost_invoice(invoice: 'LandedCostInvoice') -> 'JournalEntry':
    """
    Posts a 'Draft' LandedCostInvoice to the General Ledger.

    - Debits a 'Landed Costs Clearing' account.
    - Credits Accounts Payable to the third-party vendor.
    - Updates the invoice status to 'Awaiting Allocation'.
    """
    from ..models import LandedCostInvoice

    logger.info(f"--> Attempting to post LandedCostInvoice ID {invoice.id}.")

    if invoice.status != LandedCostInvoice.Status.DRAFT:
        raise ValidationError(_("Only draft landed cost invoices can be posted."))
    if invoice.journal_entry:
        raise ValidationError(_("This invoice has already been posted."))

    _check_period_is_open(invoice.invoice_date)

    settings = GeneralAccountingSettings.load()
    clearing_account = settings.landed_costs_clearing_account
    ap_account = settings.accounts_payable

    if not all([clearing_account, ap_account]):
        raise ValueError(_("Landed Costs Clearing or A/P accounts are not configured."))

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=invoice.invoice_date,
            description=_("Landed Cost Invoice %(num)s from %(vendor)s") % {
                'num': invoice.invoice_number, 'vendor': invoice.vendor.name
            },
            source_object=invoice,
            status=JournalEntry.Status.POSTED
        )
        # Debit the clearing account
        JournalEntryLine.objects.create(
            journal_entry=je, account=clearing_account, amount=invoice.total_amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        # Credit Accounts Payable
        JournalEntryLine.objects.create(
            journal_entry=je, account=ap_account, amount=invoice.total_amount,
            entry_type=JournalEntryLine.EntryType.CREDIT, sub_ledger_object=invoice.vendor
        )
        je.validate_balance()

        invoice.status = LandedCostInvoice.Status.AWAITING_ALLOCATION
        invoice.journal_entry = je
        invoice.save(update_fields=['status', 'journal_entry'])
        logger.info(f"<-- Successfully posted LandedCostInvoice ID {invoice.id}.")

    return je


def allocate_landed_costs_from_invoice(
    landed_cost_invoice_ids: list[int],
    receipt_log_ids: list[int],
    user
) -> None:
    """
    Allocates costs from one or more LandedCostInvoices to one or more
    InventoryLog receipts, creating the necessary journal entries.
    """
    from ..models import LandedCostInvoice, InventoryLog, LandedCostAllocation
    from .costing_service import recalculate_cost_history_for_product

    if not landed_cost_invoice_ids or not receipt_log_ids:
        raise ValidationError(_("You must provide both invoices and receipts to allocate."))

    with transaction.atomic():
        invoices = LandedCostInvoice.objects.filter(pk__in=landed_cost_invoice_ids)
        receipts = InventoryLog.objects.filter(pk__in=receipt_log_ids)

        total_cost_to_allocate = invoices.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.0')
        total_receipt_value = sum(
            (log.base_unit_price * Decimal(str(log.quantity))) for log in receipts
        )

        if total_cost_to_allocate <= 0:
            raise ValidationError(_("Selected invoices have no cost to allocate."))
        if total_receipt_value <= 0:
            raise ValidationError(_("Selected receipts have a total value of zero, cannot allocate costs."))

        settings = GeneralAccountingSettings.load()
        clearing_account = settings.landed_costs_clearing_account
        if not clearing_account:
            raise ValueError(_("Landed Cost Clearing Account is not configured."))

        # --- Create a single, consolidated Journal Entry for the allocation ---
        allocation_date = timezone.now()
        description = _(
            "تخصيص تكاليف إضافية من %(invoice_count)d فاتورة إلى %(receipt_count)d إيصال استلام"
        ) % {'invoice_count': len(invoices), 'receipt_count': len(receipts)}

        je = JournalEntry.objects.create(
            date=allocation_date,
            description=description,
            notes=f"Allocation performed by {user.username}",
            status=JournalEntry.Status.POSTED
        )
        
        # CREDIT the clearing account for the total amount being moved out
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=clearing_account,
            amount=total_cost_to_allocate,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )

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

            # DEBIT the specific inventory account for this receipt's share of the cost
            inventory_account = _get_product_inventory_account(log.product)
            JournalEntryLine.objects.create(
                journal_entry=je,
                account=inventory_account,
                amount=cost_to_add,
                entry_type=JournalEntryLine.EntryType.DEBIT,
                sub_ledger_object=log.product
            )
            
            # Create an audit record for this specific allocation
            # This links all invoices to this one receipt log
            for inv in invoices:
                item = inv.items.first()
                if item:
                    LandedCostAllocation.objects.create(
                        landed_cost_item=item,
                        receipt_log=log,
                        allocated_amount=cost_to_add / len(invoices), # Approximate for audit
                        journal_entry=je
                    )

        je.validate_balance()

        # Update invoice statuses
        invoices.update(status=LandedCostInvoice.Status.FULLY_ALLOCATED)

    # --- Trigger cost recalculation outside the transaction ---
    for product_id in products_to_recalculate:
        earliest_receipt_date = receipts.filter(product_id=product_id).earliest('release_timestamp').release_timestamp
        recalculate_cost_history_for_product(product_id, earliest_receipt_date)

    logger.info(f"User {user.username} allocated {total_cost_to_allocate} from {len(invoices)} invoices to {len(receipts)} receipts.")

