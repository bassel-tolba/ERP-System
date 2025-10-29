# gipcco_project/inventory/services/finished_product_service.py
import logging
from decimal import Decimal
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.db.models import Count, Sum, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce

from ..models import FinishedProductReceipt, Batch, ReceiptSubBatch
from .accounting.correction_transactions import create_reversing_je_for_correction
from .costing_service import recalculate_cost_history_for_product, get_inventory_state_at_datetime

logger = logging.getLogger(__name__)


def get_finished_goods_status_data() -> dict:
    """
    Fetches the data for the finished goods status page.
    """
    # 1. In Production
    all_plans = Batch.objects.filter(is_continuation=False, status=Batch.Status.IN_PROGRESS).annotate(
        received_count=Count('receipts')
    ).select_related(
        'template__final_product'
    ).order_by('-creation_date')

    in_production_plans = [plan for plan in all_plans if plan.received_count < plan.number_of_batches_in_plan]

    # 2. In Quarantine
    quarantined_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.QUARANTINED
    ).select_related('batch__template__final_product')

    # 3. Released
    released_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).select_related('batch__template__final_product')
    
    return {
        'in_production_plans': in_production_plans,
        'quarantined_receipts': quarantined_receipts,
        'released_receipts': released_receipts,
    }


def release_receipt_from_quarantine(receipt: FinishedProductReceipt):
    """
    Changes a FinishedProductReceipt's status from QUARANTINED to RELEASED.
    """
    if receipt.status != FinishedProductReceipt.Status.QUARANTINED:
        raise ValidationError(_("Only receipts in quarantine can be released."))
    
    with transaction.atomic():
        receipt.status = FinishedProductReceipt.Status.RELEASED
        receipt.release_date = timezone.now().date()
        receipt.save(update_fields=['status', 'release_date'])
    logger.info(f"Released FinishedProductReceipt ID {receipt.id} from quarantine.")


def get_proportional_cost_for_receipt(production_plan: Batch) -> dict:
    """
    Calculates the proportional cost for a single receipt within a production plan,
    including costs from all continuation batches. Returns the total and proportional cost.
    """
    main_plan_cost = Decimal('0.0')
    for item in production_plan.items.all():
        cost = item.cost_at_consumption
        if cost is None: # Fallback calculation if costing service hasn't run yet
            state = get_inventory_state_at_datetime(item.primitive_product_id, production_plan.creation_date)
            mac = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            cost = mac.quantize(Decimal('0.001'))
        main_plan_cost += cost * Decimal(str(item.actual_quantity or 0.0))

    continuation_costs = production_plan.continuation_batches.aggregate(
        total=Sum(
            ExpressionWrapper(
                F('items__actual_quantity') * F('items__cost_at_consumption'),
                output_field=DecimalField()
            )
        )
    )['total'] or Decimal('0.0')

    total_plan_cost = main_plan_cost + continuation_costs
    num_batches_in_plan = production_plan.number_of_batches_in_plan
    proportional_cost = (total_plan_cost / num_batches_in_plan) if num_batches_in_plan > 0 else Decimal('0.0')
    
    return {
        'total_plan_cost': total_plan_cost,
        'proportional_cost': proportional_cost.quantize(Decimal('0.001'))
    }


def create_finished_product_receipt(
    *,
    production_plan: Batch,
    individual_batch_number: str,
    receipt_date: datetime.date,
    market_type: str,
    notes: str,
    sub_batches_data: list
) -> FinishedProductReceipt:
    """
    Creates a FinishedProductReceipt, its sub-batches, and updates the parent batch status.
    """
    # 1. --- Validation ---
    if production_plan.is_continuation:
        raise ValidationError(_("Cannot receive a finished product against a continuation batch. Please use the original plan."))
    if production_plan.status != Batch.Status.IN_PROGRESS:
        raise ValidationError(_("Finished products can only be received for 'In Progress' production plans."))

    if not sub_batches_data:
        raise ValueError(_("At least one sub-batch must be provided."))

    with transaction.atomic():
        total_quantity_produced = sum(float(item['quantity']) for item in sub_batches_data if item.get('quantity'))
        cost_data = get_proportional_cost_for_receipt(production_plan)
        proportional_cost = cost_data['proportional_cost']

        # 2. --- Create Receipt ---
        receipt = FinishedProductReceipt.objects.create(
            batch=production_plan,
            individual_batch_number=individual_batch_number,
            receipt_date=receipt_date,
            market_type=market_type,
            notes=notes,
            total_cost=proportional_cost,
            total_quantity_produced=total_quantity_produced,
            status=FinishedProductReceipt.Status.QUARANTINED
        )

        # 3. --- Create Sub-Batches ---
        sub_batches_to_create = [
            ReceiptSubBatch(
                receipt=receipt,
                sub_batch_identifier=item['identifier'],
                quantity=float(item['quantity'])
            ) for item in sub_batches_data if item.get('identifier') and item.get('quantity')
        ]
        ReceiptSubBatch.objects.bulk_create(sub_batches_to_create)

        # 4. --- Update Parent Batch Status ---
        if production_plan.receipts.count() >= production_plan.number_of_batches_in_plan:
            production_plan.status = Batch.Status.COMPLETED
            production_plan.save(update_fields=['status'])
            logger.info(f"All receipts for Batch ID {production_plan.id} are now received. Status updated to COMPLETED.")

    logger.info(f"Successfully created FinishedProductReceipt ID {receipt.id} for Batch ID {production_plan.id}.")
    return receipt


def get_finished_product_cost_breakdown(receipt: FinishedProductReceipt) -> dict:
    """
    Calculates a detailed cost breakdown for a finished product receipt,
    aggregating costs from the parent plan and all its continuations.
    """
    production_plan = receipt.batch

    # 1. Main plan cost
    main_plan_cost = production_plan.items.aggregate(
        total=Coalesce(Sum(
            ExpressionWrapper(
                F('actual_quantity') * F('cost_at_consumption'),
                output_field=DecimalField()
            )
        ), Decimal('0.0'))
    )['total']

    # 2. Continuation batches with costs
    continuation_batches_with_costs = production_plan.continuation_batches.annotate(
        continuation_cost=Coalesce(Sum(
            ExpressionWrapper(
                F('items__actual_quantity') * F('items__cost_at_consumption'),
                output_field=DecimalField()
            )
        ), Decimal('0.0'))
    ).order_by('creation_date')

    # 3. Total continuation cost
    total_continuation_cost = continuation_batches_with_costs.aggregate(
        total=Sum('continuation_cost')
    )['total'] or Decimal('0.0')

    # 4. Grand total
    total_plan_cost = main_plan_cost + total_continuation_cost

    return {
        'main_plan_cost': main_plan_cost,
        'continuation_batches_with_costs': continuation_batches_with_costs,
        'total_continuation_cost': total_continuation_cost,
        'total_plan_cost': total_plan_cost,
    }


def cancel_finished_product_receipt(receipt: FinishedProductReceipt, user, justification: str):
    """
    Cancels a finished product receipt non-destructively.
    1. Validates that it hasn't been dispatched or adjusted.
    2. Sets status to CANCELLED.
    3. Reverts the parent batch status if it was COMPLETED.
    4. Creates a reversing journal entry.
    5. Triggers a cost recalculation for the product.
    """
    logger.info(f"--> User '{user.username}' attempting to cancel FinishedProductReceipt ID {receipt.id}.")

    # 1. --- Validation ---
    if receipt.status == FinishedProductReceipt.Status.CANCELLED:
        raise ValidationError(_("This receipt has already been cancelled."))
    if receipt.dispatches.exists():
        raise ValidationError(_("Cannot cancel a receipt that has associated dispatches. Please process a sales return instead."))
    if receipt.adjustments.exists():
        raise ValidationError(_("Cannot cancel a receipt that has been part of an inventory adjustment."))

    product_to_recalc = receipt.batch.template.final_product
    parent_batch = receipt.batch

    with transaction.atomic():
        # 2. --- Status Change ---
        receipt.status = FinishedProductReceipt.Status.CANCELLED
        receipt.save(update_fields=['status'])
        logger.info(f"    Set status to CANCELLED for receipt ID {receipt.id}.")

        # 3. --- Revert Parent Batch Status ---
        if parent_batch.status == Batch.Status.COMPLETED:
            parent_batch.status = Batch.Status.IN_PROGRESS
            parent_batch.save(update_fields=['status'])
            logger.info(f"    Reverted parent Batch ID {parent_batch.id} status to IN_PROGRESS.")

        # 4. --- Create Reversing Journal Entry ---
        create_reversing_je_for_correction(
            original_object=receipt,
            justification=justification,
            user=user,
            correction_date=timezone.now()
        )
        logger.info(f"    Created reversing JE for receipt ID {receipt.id}.")

    # 5. --- Recalculate Costs ---
    # The date of the original receipt is the correct point to start recalculation from
    recalculation_start_date = timezone.make_aware(timezone.datetime.combine(receipt.receipt_date, timezone.datetime.min.time()))
    recalculate_cost_history_for_product(product_to_recalc.id, recalculation_start_date)
    logger.info(f"    Triggered cost recalculation for Product ID {product_to_recalc.id}.")

    logger.info(f"<-- Successfully cancelled FinishedProductReceipt ID {receipt.id}.")
