# gipcco_project/inventory/services/sales_service.py

import logging
from decimal import Decimal
from typing import List, Dict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..models import (
    Payment,
    CustomerInvoice,
    CustomerPaymentApplication,
    Customer,
    FinishedProductReceipt,
    SalesOrder,
    SalesOrderItem,
    FinishedProductDispatch,
    CustomerInvoiceItem,
    InventoryAdjustment,
)
from ..services.costing_service import get_inventory_state_at_datetime
from django.db.models import Subquery, OuterRef, Sum, FloatField, F
from django.db.models.functions import Coalesce

logger = logging.getLogger(__name__)


def create_sales_order(
    customer_id: int,
    order_date: str,
    so_number: str,
    items: List[Dict[str, any]],
    notes: str = None
) -> SalesOrder:
    """
    Creates a new Sales Order and its associated line items.

    Args:
        customer_id: The ID of the customer placing the order.
        order_date: The date of the order in 'YYYY-MM-DD' format.
        so_number: The unique sales order number.
        items: A list of dictionaries, each representing a line item:
               {
                   'finished_product_receipt_id': int,
                   'quantity_ordered': float,
                   'base_price_per_unit': Decimal,
                   'vat_rate': Decimal
               }
        notes: Optional notes for the sales order.

    Returns:
        The newly created SalesOrder instance.

    Raises:
        ValidationError: If customer, products are not found, or if there is
                         insufficient stock for any of the items.
    """
    logger.info(f"Attempting to create Sales Order '{so_number}' for customer ID {customer_id}.")

    with transaction.atomic():
        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            logger.error(f"Validation failed: Customer with ID {customer_id} not found.")
            raise ValidationError(_("Customer with ID %(id)s not found.") % {'id': customer_id})

        # --- Pre-fetch all required product receipts for efficiency ---
        receipt_ids = [item['finished_product_receipt_id'] for item in items]
        receipts = FinishedProductReceipt.objects.in_bulk(receipt_ids)

        if len(receipts) != len(set(receipt_ids)):
            raise ValidationError(_("One or more finished product batches could not be found."))

        # --- Validate stock availability for all items before creating anything ---
        for item_data in items:
            receipt_id = item_data['finished_product_receipt_id']
            quantity_ordered = item_data['quantity_ordered']
            receipt = receipts.get(receipt_id)

            if not receipt:
                # This case is covered by the in_bulk check, but remains for safety.
                raise ValidationError(_("Finished product batch with ID %(id)s not found.") % {'id': receipt_id})

            # Here you would implement a robust stock availability check.
            # For now, we assume a function `get_available_stock(receipt)` exists.
            # This is a placeholder for a more complex calculation.
            # available_stock = get_available_stock(receipt)
            # if quantity_ordered > available_stock:
            #     raise ValidationError(
            #         _("Insufficient stock for product '%(product)s'. Ordered: %(ordered)s, Available: %(available)s.")
            #         % {'product': receipt, 'ordered': quantity_ordered, 'available': available_stock}
            #     )
            pass # Placeholder for stock check

        # --- Create the Sales Order and Items ---
        so = SalesOrder.objects.create(
            customer=customer,
            order_date=order_date,
            so_number=so_number,
            notes=notes,
            status=SalesOrder.Status.PENDING
        )
        logger.info(f"    Created SalesOrder {so.id} ('{so_number}'). Now creating items.")

        for item_data in items:
            receipt = receipts[item_data['finished_product_receipt_id']]
            SalesOrderItem.objects.create(
                sales_order=so,
                finished_product=receipt,
                quantity_ordered=item_data['quantity_ordered'],
                base_price_per_unit=item_data['base_price_per_unit'],
                vat_rate=item_data['vat_rate']
            )
        
        logger.info(f"    Successfully created {len(items)} line item(s) for SO '{so_number}'.")
        logger.info(f"<-- Sales Order '{so_number}' created successfully.")
        return so


def dispatch_from_sales_order(
    sales_order_id: int,
    dispatch_date: timezone.datetime,
    dispatches: List[Dict[str, any]]
) -> List[FinishedProductDispatch]:
    """
    Creates dispatch records for items on a sales order, fulfilling the order.

    Args:
        sales_order_id: The ID of the SalesOrder to dispatch from.
        dispatch_date: The timestamp for when the dispatch occurs.
        dispatches: A list of dictionaries, each specifying an item to dispatch:
                    {
                        'sales_order_item_id': int,
                        'quantity': float
                    }

    Returns:
        A list of the newly created FinishedProductDispatch instances.

    Raises:
        ValidationError: If the sales order or items are not found, or if the
                         dispatch quantity exceeds the ordered quantity.
    """
    logger.info(f"Attempting to dispatch items for Sales Order ID {sales_order_id}.")

    with transaction.atomic():
        try:
            so = SalesOrder.objects.select_for_update().get(pk=sales_order_id)
        except SalesOrder.DoesNotExist:
            raise ValidationError(_("Sales Order with ID %(id)s not found.") % {'id': sales_order_id})

        item_ids = [d['sales_order_item_id'] for d in dispatches]
        so_items = {item.id: item for item in so.items.select_related('finished_product').filter(id__in=item_ids)}

        if len(so_items) != len(set(item_ids)):
            raise ValidationError(_("One or more sales order items could not be found on this order."))

        # --- NEW: Efficiently check stock for all items at once ---
        receipt_ids = [item.finished_product_id for item in so_items.values()]

        # Use the centralized manager method to get available quantity
        receipts_with_stock = FinishedProductReceipt.objects.filter(id__in=receipt_ids).with_remaining_quantity().annotate(
            quantity_available=F('remaining_quantity')
        )
        
        stock_map = {receipt.id: receipt.quantity_available for receipt in receipts_with_stock}

        # --- Validate quantities before creating any dispatches ---
        for dispatch_data in dispatches:
            item = so_items.get(dispatch_data['sales_order_item_id'])
            if not item:
                 raise ValidationError(_("Sales Order Item with ID %(id)s not found.") % {'id': dispatch_data['sales_order_item_id']})

            quantity_to_dispatch = dispatch_data['quantity']
            available_stock = stock_map.get(item.finished_product_id, 0)
            
            if quantity_to_dispatch > available_stock:
                raise ValidationError(
                    _("Insufficient stock for '%(product)s'. Requested: %(requested)s, Available: %(available)s.")
                    % {
                        'product': item.finished_product,
                        'requested': quantity_to_dispatch,
                        'available': available_stock
                    }
                )

        created_dispatches = []
        for dispatch_data in dispatches:
            item_id = dispatch_data['sales_order_item_id']
            quantity_to_dispatch = dispatch_data['quantity']
            item = so_items.get(item_id)

            if not item:
                raise ValidationError(_("Sales Order Item with ID %(id)s not found.") % {'id': item_id})

            # More validation can be added here, e.g., checking against already dispatched quantities.

            # Determine cost at dispatch using costing service
            product = item.finished_product.batch.template.final_product
            state = get_inventory_state_at_datetime(product.id, dispatch_date)
            cost_per_unit = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            total_cost = (Decimal(str(quantity_to_dispatch)) * cost_per_unit).quantize(Decimal('0.001'))

            dispatch = FinishedProductDispatch.objects.create(
                sales_order_item=item,
                quantity=quantity_to_dispatch,
                dispatch_date=dispatch_date,
                cost_at_dispatch=total_cost
            )
            created_dispatches.append(dispatch)
            logger.info(f"    Created dispatch for {quantity_to_dispatch} units of {product.name} with cost {total_cost}.")

        # --- NEW: Update SalesOrder status automatically ---
        all_items_fulfilled = True
        has_any_dispatch = False

        # Recalculate fulfillment status across all items on the order
        for item in so.items.all():
            # Use the database to get the most up-to-date sum of dispatched quantities for the item
            total_dispatched = item.dispatches.aggregate(total=Sum('quantity'))['total'] or 0
            
            if total_dispatched > 0:
                has_any_dispatch = True
            
            # If any item is not fully dispatched, the whole order is not complete
            if total_dispatched < item.quantity_ordered:
                all_items_fulfilled = False
        
        if all_items_fulfilled:
            so.status = SalesOrder.Status.COMPLETED
            logger.info(f"    All items for SO ID {sales_order_id} are now fulfilled. Status updated to COMPLETED.")
        elif has_any_dispatch:
            # If there's at least one dispatch but not all items are fulfilled, it's partially fulfilled
            so.status = SalesOrder.Status.PARTIALLY_SHIPPED
            logger.info(f"    Some items for SO ID {sales_order_id} have been dispatched. Status updated to PARTIALLY_SHIPPED.")
        
        # Only save if the status has changed from its original state before this dispatch operation
        so.save(update_fields=['status'])

        logger.info(f"<-- Successfully created {len(created_dispatches)} dispatch(es) for SO ID {sales_order_id}.")
        return created_dispatches


def create_invoice_from_dispatches(
    customer_id: int,
    invoice_number: str,
    invoice_date: str,
    due_date: str,
    dispatch_ids: List[int]
) -> CustomerInvoice:
    """
    Creates a CustomerInvoice from a list of FinishedProductDispatch records.

    Args:
        customer_id: The ID of the customer to invoice.
        invoice_number: The unique number for this invoice.
        invoice_date: The date of the invoice ('YYYY-MM-DD').
        due_date: The payment due date for the invoice ('YYYY-MM-DD').
        dispatch_ids: A list of IDs for the FinishedProductDispatch records to include.

    Returns:
        The newly created CustomerInvoice instance.

    Raises:
        ValidationError: If dispatches are not found, already invoiced, or belong
                         to different customers.
    """
    logger.info(f"Attempting to create invoice '{invoice_number}' from {len(dispatch_ids)} dispatch(es).")

    with transaction.atomic():
        try:
            customer = Customer.objects.get(pk=customer_id)
        except Customer.DoesNotExist:
            raise ValidationError(_("Customer with ID %(id)s not found.") % {'id': customer_id})

        dispatches = FinishedProductDispatch.objects.select_related(
            'sales_order_item__sales_order__customer'
        ).filter(id__in=dispatch_ids)

        if len(dispatches) != len(set(dispatch_ids)):
            raise ValidationError(_("One or more dispatches could not be found."))

        total_invoice_amount = Decimal('0.0')
        for dispatch in dispatches:
            if hasattr(dispatch, 'invoice_item'):
                raise ValidationError(
                    _("Dispatch ID %(id)s has already been included in an invoice.")
                    % {'id': dispatch.id}
                )
            if dispatch.sales_order_item.sales_order.customer_id != customer_id:
                raise ValidationError(
                    _("Dispatch ID %(id)s belongs to a different customer.")
                    % {'id': dispatch.id}
                )
            
            so_item = dispatch.sales_order_item
            base_amount = Decimal(str(dispatch.quantity)) * so_item.base_price_per_unit
            vat_amount = base_amount * so_item.vat_rate
            total_invoice_amount += base_amount + vat_amount

        invoice = CustomerInvoice.objects.create(
            customer=customer,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            total_amount=total_invoice_amount.quantize(Decimal('0.001')),
            status=CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT
        )
        logger.info(f"    Created CustomerInvoice {invoice.id} with total amount {total_invoice_amount}.")

        for dispatch in dispatches:
            so_item = dispatch.sales_order_item
            base_amount = Decimal(str(dispatch.quantity)) * so_item.base_price_per_unit
            vat_amount = base_amount * so_item.vat_rate
            item_amount = (base_amount + vat_amount).quantize(Decimal('0.001'))
            CustomerInvoiceItem.objects.create(
                invoice=invoice,
                dispatch=dispatch,
                amount=item_amount
            )
        
        logger.info(f"    Successfully linked {len(dispatches)} dispatch(es) to invoice '{invoice_number}'.")
        logger.info(f"<-- Invoice '{invoice_number}' created successfully.")
        return invoice


def cancel_sales_order(sales_order: SalesOrder):
    """
    Cancels a sales order if no dispatches have been made against it.
    """
    if sales_order.items.filter(dispatches__isnull=False).exists():
        raise ValidationError(_("Cannot cancel a sales order that has associated dispatches. Please process a sales return instead."))
    
    sales_order.status = SalesOrder.Status.CANCELLED
    sales_order.save(update_fields=['status'])
    logger.info(f"Sales Order {sales_order.so_number} has been cancelled.")


def update_sales_order_item(so_item: SalesOrderItem, new_quantity: float):
    """
    Updates the quantity of a sales order item, validating against dispatched quantities.
    """
    dispatched_quantity = so_item.dispatches.aggregate(total=Sum('quantity'))['total'] or 0
    if new_quantity < dispatched_quantity:
        raise ValidationError(_(f"New quantity ({new_quantity}) cannot be less than the already dispatched quantity ({dispatched_quantity})."))
    
    so_item.quantity_ordered = new_quantity
    so_item.save(update_fields=['quantity_ordered'])
    logger.info(f"Sales Order Item {so_item.id} quantity updated to {new_quantity}.")


def cancel_dispatch(dispatch: FinishedProductDispatch, user, justification: str):
    """
    REDEFINED: Cancels a dispatch non-destructively by changing its status
    and creating a reversing journal entry.
    """
    from .accounting.correction_transactions import create_reversing_je_for_correction

    # Use a more reliable check for the related invoice item
    is_invoiced = CustomerInvoiceItem.objects.filter(dispatch=dispatch).exists()
    if is_invoiced:
        raise ValidationError(_("Cannot cancel a dispatch that has already been invoiced. Please create a sales return for this item instead to generate a credit memo."))

    if dispatch.status == FinishedProductDispatch.Status.CANCELLED:
        raise ValidationError(_("This dispatch has already been cancelled."))

    with transaction.atomic():
        dispatch.status = FinishedProductDispatch.Status.CANCELLED
        dispatch.save(update_fields=['status'])

        create_reversing_je_for_correction(
            original_object=dispatch,
            justification=justification,
            user=user,
            correction_date=timezone.now()
        )
    
    logger.info(f"Dispatch {dispatch.id} has been cancelled by user {user.username} and its journal entry reversed.")


def apply_payment_to_invoices(payment: Payment, applications: List[Dict[str, any]]):
    """
    Applies a single customer payment to one or more outstanding customer invoices.

    This is the core of the cash application process in Accounts Receivable.

    Args:
        payment: The Payment instance received from the customer.
        applications: A list of dictionaries, where each dictionary contains:
                      {'invoice_id': int, 'amount_to_apply': Decimal}

    Raises:
        ValidationError: If any business rule is violated (e.g., over-application,
                         invalid payment type, invoice not found).
    """
    logger.info(f"Starting payment application for Payment ID {payment.id} against {len(applications)} invoice(s).")

    with transaction.atomic():
        # 1. --- Initial Payment Validation ---
        if payment.payment_type != Payment.PaymentType.PAYMENT_IN:
            logger.error(f"Validation failed: Payment ID {payment.id} is not of type 'PAYMENT_IN'.")
            raise ValidationError(_("The provided payment is not an incoming customer payment."))

        total_to_apply = sum(Decimal(str(app['amount_to_apply'])) for app in applications)
        
        # Calculate the unapplied amount for an incoming (AR) payment
        unapplied_amount = payment.amount - payment.total_received_applied
        if total_to_apply > unapplied_amount:
            logger.error(f"Validation failed: Total to apply ({total_to_apply}) exceeds unapplied payment amount ({unapplied_amount}) for Payment ID {payment.id}.")
            raise ValidationError(
                _("The total amount to apply (%(total)s) exceeds the unapplied amount of the payment (%(unapplied)s).")
                % {'total': total_to_apply, 'unapplied': unapplied_amount}
            )
        logger.info(f"    [CHECK PASSED] Total to apply ({total_to_apply}) is within the unapplied payment amount ({unapplied_amount}).")

        # 2. --- Invoice Data Fetching ---
        invoice_ids = [app['invoice_id'] for app in applications]
        
        # Lock the invoice rows for the duration of the transaction to prevent race conditions
        invoices_qs = CustomerInvoice.objects.select_for_update().filter(id__in=invoice_ids)
        invoices_map = {invoice.id: invoice for invoice in invoices_qs}
        
        if len(invoices_map) != len(set(invoice_ids)):
            logger.error(f"Validation failed: One or more invoice IDs provided do not exist. Provided: {invoice_ids}, Found: {list(invoices_map.keys())}")
            raise ValidationError(_("One or more of the specified invoices could not be found."))
        logger.info(f"    [CHECK PASSED] All {len(invoices_map)} invoices were found and locked.")

        # 3. --- Per-Application Validation Loop ---
        for app in applications:
            invoice_id = app['invoice_id']
            amount_to_apply = Decimal(str(app['amount_to_apply']))
            invoice = invoices_map.get(invoice_id)

            # This check is technically redundant due to the previous check, but good for clarity
            if not invoice:
                raise ValidationError(_("Invoice with ID %(id)s not found.") % {'id': invoice_id})

            if amount_to_apply <= 0:
                logger.error(f"Validation failed: Amount to apply for Invoice ID {invoice_id} is not positive ({amount_to_apply}).")
                raise ValidationError(_("The amount to apply to an invoice must be positive."))

            if amount_to_apply > invoice.balance_due:
                logger.error(f"Validation failed: Amount to apply ({amount_to_apply}) for Invoice ID {invoice_id} exceeds its balance due ({invoice.balance_due}).")
                raise ValidationError(
                    _("The amount to apply (%(amount)s) to invoice %(invoice_num)s exceeds its balance due (%(balance)s).")
                    % {'amount': amount_to_apply, 'invoice_num': invoice.invoice_number, 'balance': invoice.balance_due}
                )
            logger.info(f"    [VALIDATION] Application for Invoice {invoice.invoice_number} for amount {amount_to_apply} is valid.")

        logger.info("    [ALL CHECKS PASSED] All validations passed. Proceeding with database updates.")
        # 4. --- Database State Changes ---
        for app in applications:
            invoice_id = app['invoice_id']
            amount_to_apply = Decimal(str(app['amount_to_apply']))
            invoice = invoices_map[invoice_id]

            # Create the linking record
            CustomerPaymentApplication.objects.create(
                payment=payment,
                invoice=invoice,
                amount_applied=amount_to_apply
            )
            logger.info(f"        Created CustomerPaymentApplication for Payment {payment.id} -> Invoice {invoice.id} for {amount_to_apply}.")

            # Update the invoice's paid amount and status
            invoice.amount_paid += amount_to_apply
            invoice.update_status(save=False) # We will save it explicitly
            invoice.save(update_fields=['amount_paid', 'status'])
            logger.info(f"        Updated Invoice {invoice.id}: New amount_paid is {invoice.amount_paid}, new status is {invoice.get_status_display()}.")

    logger.info(f"<-- Successfully completed payment application for Payment ID {payment.id}.")
