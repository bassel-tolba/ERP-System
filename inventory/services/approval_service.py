# inventory/services/approval_service.py
import logging
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from decimal import Decimal 
from django.db.models import Sum, F, Value, FloatField
from django.db.models.functions import Coalesce
from typing import Optional, List, Dict
from datetime import date


from .. import models as inventory_models
from . import costing_service, accounting_service

logger = logging.getLogger(__name__)

def _get_fifo_source_logs_for_consumption(product: inventory_models.Product, quantity_needed: Decimal) -> List[Dict]:
    """
    REDEFINED: Finds the oldest available InventoryLogs to satisfy the quantity needed,
    drawing from multiple logs if necessary (FIFO).

    Returns a list of dictionaries: [{'log': InventoryLog, 'quantity': Decimal}, ...]
    """
    logs_with_outflows = inventory_models.InventoryLog.objects.filter(
        product=product,
        status=inventory_models.InventoryLog.Status.RELEASED
    ).with_remaining_quantity().filter(remaining_quantity__gt=Decimal('0.0')).order_by('timestamp')

    total_available = logs_with_outflows.aggregate(total=Sum('remaining_quantity'))['total'] or Decimal('0.0')
    if total_available < quantity_needed:
        raise ValidationError(f"Insufficient total inventory for product '{product.name}'. Needed: {quantity_needed}, Available: {total_available:.3f}.")

    consumptions = []
    remaining_to_fulfill = quantity_needed

    for log in logs_with_outflows:
        if remaining_to_fulfill <= 0:
            break
        
        quantity_to_take = min(remaining_to_fulfill, log.remaining_quantity)
        
        consumptions.append({
            'log': log,
            'quantity': quantity_to_take
        })
        remaining_to_fulfill -= quantity_to_take

    return consumptions


def _create_inventory_consumption_from_request(request: inventory_models.ExpenseRequest) -> List[inventory_models.InventoryConsumption]:
    """
    REDEFINED: Creates one or more InventoryConsumption records from an approved request,
    drawing from multiple source logs if necessary (FIFO).
    """
    product = request.product
    
    source_allocations = _get_fifo_source_logs_for_consumption(product, request.quantity)

    consumptions_created = []
    
    consumption_type = inventory_models.InventoryConsumption.ConsumptionType.EXPENSE
    if request.request_type == inventory_models.ExpenseRequest.RequestType.INVENTORY_CAPITALIZE:
        consumption_type = inventory_models.InventoryConsumption.ConsumptionType.CAPITALIZE
    elif request.request_type == inventory_models.ExpenseRequest.RequestType.INVENTORY_PREPAID:
        consumption_type = inventory_models.InventoryConsumption.ConsumptionType.AMORTIZE

    cost_pool = request.cost_pool
    if consumption_type == inventory_models.InventoryConsumption.ConsumptionType.EXPENSE and not cost_pool:
        raise ValidationError("A Cost Pool is required for an inventory expense request.")

    department_value = inventory_models.InventoryConsumption.Department.PRODUCTION

    for allocation in source_allocations:
        source_log = allocation['log']
        quantity_to_consume = allocation['quantity']
        
        cost_per_unit = source_log.costing_unit_price
        total_cost = (quantity_to_consume * cost_per_unit)

        consumption = inventory_models.InventoryConsumption.objects.create(
            product=product,
            source_log=source_log,
            quantity_consumed=quantity_to_consume,
            consumption_date=timezone.now(),
            department=department_value,
            cost_at_consumption=total_cost,
            notes=request.description,
            consumption_type=consumption_type,
            fixed_asset=request.fixed_asset if request.request_type == inventory_models.ExpenseRequest.RequestType.INVENTORY_CAPITALIZE else None,
            cost_pool=cost_pool,
            source_request=request
        )
        consumptions_created.append(consumption)

    return consumptions_created

def _execute_approval(request: inventory_models.ExpenseRequest) -> models.Model:
    """
    Private dispatcher. Creates the initial object that triggers signals.
    """
    request_type = request.request_type

    if request_type == inventory_models.ExpenseRequest.RequestType.DIRECT_EXPENSE:
        if request.settlement_method == inventory_models.ExpenseRequest.SettlementMethod.DIRECT_PAYMENT:
            # This path creates the ExpenseLog and the correct JE (Debit Expense, Credit Bank)
            return accounting_service.create_transaction_for_direct_payment_expense(request)
        else:  # Default to ACCRUE_AND_PAY_LATER
            # This path creates an ExpenseLog that the signal will turn into a JE
            # (Debit Expense, Credit Accrued Liability)
            return inventory_models.ExpenseLog.objects.create(
                description=request.description,
                expense_date=request.request_date,
                amount=request.amount,
                category=request.category,
                classification=request.classification,
                cost_pool=request.cost_pool,
                source_request=request,
                settlement_status=inventory_models.ExpenseLog.SettlementStatus.UNSETTLED
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
    
    elif request_type == inventory_models.ExpenseRequest.RequestType.ACCRUAL:
        settings = inventory_models.GeneralAccountingSettings.load()
        if not settings.accrued_expenses_account:
            raise ValidationError("The master Accrued Expenses Liability account is not configured in General Settings.")

        # Create a scheduled AccruedExpense object. The period-end process will handle the monthly JEs.
        return inventory_models.AccruedExpense.objects.create(
            description=request.description,
            total_estimated_amount=request.amount,
            accrual_start_date=request.amortization_start_date,
            accrual_end_date=request.amortization_end_date,
            target_expense_account=request.expense_account,
            target_liability_account=settings.accrued_expenses_account,
            status=inventory_models.AccruedExpense.Status.ACTIVE,
            source_request=request
        )

    else:
        raise NotImplementedError(f"Approval logic for request type '{request_type}' is not implemented.")


def approve_request(request_id: int, user, processed_date: Optional[date] = None):
    """
    Approves a pending request. This is the main entry point for the approval workflow.
    - Sets the request status to APPROVED.
    - Sets the processed_at timestamp.
    - Calls the dispatcher to create the resulting financial transaction.
    """
    with transaction.atomic():
        try:
            request = inventory_models.ExpenseRequest.objects.select_for_update().get(pk=request_id)
        except inventory_models.ExpenseRequest.DoesNotExist:
            raise ValidationError(f"Expense Request with ID {request_id} not found.")

        if request.status != inventory_models.ExpenseRequest.Status.PENDING:
            raise PermissionDenied(f"Request #{request.id} is not in a pending state and cannot be approved.")

        # This is where the main logic happens
        _execute_approval(request)

        # Update the request status after the transaction is successfully created
        request.status = inventory_models.ExpenseRequest.Status.APPROVED
        request.processed_by = user
        request.processed_at = processed_date or timezone.now()
        request.save()

        logger.info(f"User '{user.username}' approved ExpenseRequest #{request.id}.")

    return request


def reject_request(request_id: int, user, reason: str):
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
