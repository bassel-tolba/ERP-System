import logging
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from decimal import Decimal
from django.db.models import Sum, F, Value, FloatField
from django.db.models.functions import Coalesce

from .. import models as inventory_models
from . import costing_service

logger = logging.getLogger(__name__)

def _get_fifo_source_log(product: inventory_models.Product, quantity_needed: Decimal) -> inventory_models.InventoryLog:
    """
    Finds the oldest available InventoryLog for a product that can satisfy the quantity needed.
    This implements a FIFO (First-In, First-Out) consumption strategy.
    """
    # Annotate each log with the sum of quantities that have been drawn from it
    logs_with_outflows = inventory_models.InventoryLog.objects.filter(
        product=product,
        status=inventory_models.InventoryLog.Status.RELEASED
    ).annotate(
        total_consumed=Coalesce(Sum('consumptions__quantity_consumed'), 0.0, output_field=FloatField()),
        total_used_in_batch=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
        total_adjusted=Coalesce(Sum('adjustments__adjustment_quantity'), 0.0, output_field=FloatField()) # Note: adjustments can be +/-
    ).annotate(
        # Calculate the net remaining quantity
        quantity_remaining=F('quantity') - F('total_consumed') - F('total_used_in_batch') + F('total_adjusted')
    )

    # Filter for logs that have enough quantity and get the oldest one
    available_log = logs_with_outflows.filter(
        quantity_remaining__gte=float(quantity_needed)
    ).order_by('timestamp').first()

    if not available_log:
        # You might want to handle this more gracefully, e.g., by allowing partial consumption
        # from multiple logs, but for now, we raise an error.
        raise ValidationError(f"Insufficient inventory for product '{product.name}'. Needed: {quantity_needed}, but no single batch has enough.")

    return available_log


def _create_inventory_consumption_from_request(request: inventory_models.ExpenseRequest) -> inventory_models.InventoryConsumption:
    """
    Creates an InventoryConsumption record from an approved request.
    """
    product = request.product
    
    # --- NEW: Find a source log using FIFO before proceeding ---
    source_log = _get_fifo_source_log(product, request.quantity)

    # Use the cost from the selected source log for accuracy, or fall back to MAC if needed.
    # The cost_at_consumption should reflect the value of the specific item being consumed.
    cost_per_unit = source_log.costing_unit_price
    total_cost = (request.quantity * cost_per_unit)

    consumption_type = inventory_models.InventoryConsumption.ConsumptionType.EXPENSE
    if request.request_type == inventory_models.ExpenseRequest.RequestType.INVENTORY_CAPITALIZE:
        consumption_type = inventory_models.InventoryConsumption.ConsumptionType.CAPITALIZE
    elif request.request_type == inventory_models.ExpenseRequest.RequestType.INVENTORY_PREPAID:
        consumption_type = inventory_models.InventoryConsumption.ConsumptionType.AMORTIZE

    consumption = inventory_models.InventoryConsumption.objects.create(
        product=product,
        source_log=source_log, # --- ADDED THIS LINE ---
        quantity_consumed=float(request.quantity),
        consumption_date=timezone.make_aware(timezone.datetime.combine(request.request_date, timezone.now().time())),
        cost_at_consumption=total_cost,
        notes=request.description,
        source_request=request,
        consumption_type=consumption_type,
        fixed_asset=request.fixed_asset,
        cost_pool=request.cost_pool,
        department=inventory_models.InventoryConsumption.Department.PRODUCTION
    )
    return consumption

def _execute_approval(request: inventory_models.ExpenseRequest) -> models.Model:
    """
    Private dispatcher. Creates the initial object that triggers signals.
    """
    request_type = request.request_type

    if request_type == inventory_models.ExpenseRequest.RequestType.DIRECT_EXPENSE:
        return inventory_models.ExpenseLog.objects.create(
            description=request.description,
            expense_date=request.request_date,
            amount=request.amount,
            category=request.category,
            classification=request.classification,
            cost_pool=request.cost_pool,
            source_request=request
        )
    
    elif request_type == inventory_models.ExpenseRequest.RequestType.INVOICE_PREPAID:
        return inventory_models.PrepaidExpense.objects.create(
            description=request.description,
            initial_amount=request.amount,
            amortization_start_date=request.amortization_start_date,
            amortization_end_date=request.amortization_end_date,
            asset_account=request.asset_account,
            expense_account=request.expense_account,
            created_by=request.requested_by,
            source_content_object=request.source_invoice
        )

    elif request_type in [
        inventory_models.ExpenseRequest.RequestType.INVENTORY_EXPENSE,
        inventory_models.ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
        inventory_models.ExpenseRequest.RequestType.INVENTORY_PREPAID
    ]:
        return _create_inventory_consumption_from_request(request)
    
    else:
        raise NotImplementedError(f"Approval logic for request type '{request_type}' is not implemented.")

@transaction.atomic
def approve_request(request_id: int, user) -> inventory_models.ExpenseRequest:
    """
    Approves an expense request, triggering the creation of the relevant financial transaction.
    """
    request = inventory_models.ExpenseRequest.objects.select_for_update().get(pk=request_id)
    
    if request.status != inventory_models.ExpenseRequest.Status.PENDING:
        raise PermissionDenied(f"Cannot approve a request with status '{request.get_status_display()}'.")

    _execute_approval(request)

    request.status = inventory_models.ExpenseRequest.Status.APPROVED
    request.processed_by = user
    request.processed_at = timezone.now()
    request.save(update_fields=['status', 'processed_by', 'processed_at'])
    
    logger.info(f"User '{user.username}' approved ExpenseRequest ID {request.id}.")
    return request

def reject_request(request_id: int, user, reason: str) -> inventory_models.ExpenseRequest:
    """
    Rejects a pending expense request.
    """
    if not reason:
        raise ValidationError("A reason is required for rejection.")

    request = inventory_models.ExpenseRequest.objects.get(pk=request_id)
    
    if request.status != inventory_models.ExpenseRequest.Status.PENDING:
        raise PermissionDenied(f"Cannot reject a request with status '{request.get_status_display()}'.")

    request.status = inventory_models.ExpenseRequest.Status.REJECTED
    request.rejection_reason = reason
    request.processed_by = user
    request.processed_at = timezone.now()
    request.save(update_fields=['status', 'rejection_reason', 'processed_by', 'processed_at'])
    
    logger.info(f"User '{user.username}' rejected ExpenseRequest ID {request.id}.")
    return request
