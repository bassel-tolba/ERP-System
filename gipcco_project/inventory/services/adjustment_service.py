# gipcco_project/inventory/services/adjustment_service.py

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List

from django.db import transaction
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models import Sum, F, FloatField, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.core.exceptions import ValidationError


from ..models import (
    InventoryCount, InventoryCountItem, InventoryAdjustment, Product,
    InventoryLog, FinishedProductReceipt, FinishedProductDispatch
)
from ..services.costing_service import get_inventory_state_at_datetime, recalculate_cost_history_for_product

logger = logging.getLogger(__name__)


def start_inventory_count(product_ids: List[int], reason: str, user: User, include_quarantined: bool = True) -> InventoryCount:
    """
    Creates a new InventoryCount event and populates it with items,
    snapshotting the current system quantity for each product.
    """
    logger.info(f"Starting inventory count process for user '{user.username}' with reason: '{reason}'. Product IDs: {product_ids}")
    with transaction.atomic():
        inventory_count = InventoryCount.objects.create(
            count_date=timezone.now().date(),
            reason=reason,
            created_by=user,
            status=InventoryCount.CountStatus.IN_PROGRESS
        )

        items_to_create = []
        for product_id in product_ids:
            logger.debug(f"Getting inventory state for product ID {product_id} at {timezone.now()}.")
            state = get_inventory_state_at_datetime(product_id, timezone.now(), include_quarantined=include_quarantined)
            system_qty = state.get('quantity', Decimal('0.0'))
            logger.debug(f"Product {product_id} has system quantity {system_qty}.")
            
            items_to_create.append(
                InventoryCountItem(
                    inventory_count=inventory_count,
                    product_id=product_id,
                    system_quantity=system_qty
                )
            )
        
        InventoryCountItem.objects.bulk_create(items_to_create)
        logger.info(f"Successfully started Inventory Count {inventory_count.id} with {len(items_to_create)} items.")

    return inventory_count


def create_adjustments_from_form(count_item_id: int, allocations: List[dict], reason: str, notes: str) -> List[InventoryAdjustment]:
    """
    Creates granular InventoryAdjustment records from a single count item's allocation form.
    """
    logger.info(f"Creating manual adjustments for count item ID {count_item_id}. Reason: {reason}, Notes: {notes}.")
    logger.debug(f"Allocations data: {allocations}")
    adjustments = []
    count_item = InventoryCountItem.objects.select_related('product', 'inventory_count').get(pk=count_item_id)
    product = count_item.product
    logger.debug(f"Processing adjustments for product '{product.name}' (ID: {product.id}).")
    
    # First, delete any existing adjustments for this count item to prevent duplicates
    logger.warning(f"Deleting existing adjustments for count {count_item.inventory_count.id} and product {product.id} before creating new ones.")
    InventoryAdjustment.objects.filter(inventory_count=count_item.inventory_count, product=product).delete()

    with transaction.atomic():
        for alloc in allocations:
            adj_qty = Decimal(alloc['quantity'])
            source_type = alloc['source_type']
            source_id = int(alloc['source_id'])
            logger.debug(f"Processing allocation: qty={adj_qty}, source_type='{source_type}', source_id={source_id}.")

            if adj_qty == 0:
                logger.debug("Skipping allocation with zero quantity.")
                continue

            source_log_instance = None
            source_receipt_instance = None
            cost_for_adjustment = None # Start with None

            if source_type == 'log':
                source_log_instance = InventoryLog.objects.get(pk=source_id)
                cost_for_adjustment = source_log_instance.costing_unit_price
                logger.debug(f"Found source log: {source_log_instance}. Using cost from log: {cost_for_adjustment}")
            elif source_type == 'receipt':
                source_receipt_instance = FinishedProductReceipt.objects.get(pk=source_id)
                cost_for_adjustment = (source_receipt_instance.total_cost / Decimal(str(source_receipt_instance.total_quantity_produced))) if source_receipt_instance.total_quantity_produced > 0 else Decimal('0.000')
                logger.debug(f"Found source receipt: {source_receipt_instance}. Using cost from receipt: {cost_for_adjustment}")

            # --- FIX: If cost is still not determined (e.g., for overages with no source), calculate it now ---
            if cost_for_adjustment is None or cost_for_adjustment <= 0:
                logger.warning(f"Cost for adjustment is {cost_for_adjustment}. Recalculating current MAC for product {product.id}.")
                state = get_inventory_state_at_datetime(product.id, timezone.now())
                if state['quantity'] > 0:
                    cost_for_adjustment = (state['value'] / state['quantity']).quantize(Decimal('0.001'))
                    logger.info(f"Calculated current MAC as: {cost_for_adjustment}")
                else:
                    cost_for_adjustment = product.moving_average_cost # Fallback to the stored one if qty is zero
                    logger.warning(f"Current quantity is zero. Falling back to stored MAC: {cost_for_adjustment}")


            adj = InventoryAdjustment.objects.create(
                product=product,
                adjustment_quantity=float(adj_qty),
                adjustment_date=timezone.now(),
                cost_at_adjustment=cost_for_adjustment,
                reason_code=reason,
                notes=notes,
                source_log=source_log_instance,
                source_finished_product=source_receipt_instance,
                inventory_count=count_item.inventory_count
            )
            adjustments.append(adj)
            logger.info(f"Created InventoryAdjustment {adj.id} for product {product.id} with quantity {adj_qty}.")
    
    logger.info(f"Finished creating {len(adjustments)} manual adjustments for count item {count_item_id}.")
    return adjustments


def auto_distribute_finished_good_shortage(count_item_id: int, reason: str, notes: str, receipt_ids: List[int] = None) -> List[InventoryAdjustment]:
    """
    Automatically creates negative adjustments for a finished good shortage
    by taking whole numbers from the newest available batches first (LIFO).
    If receipt_ids are provided, it will only operate on those specific receipts.
    """
    logger.info(f"Starting auto-distribution of finished good shortage for count item ID {count_item_id}.")
    if receipt_ids:
        logger.info(f"Operating on a specific list of {len(receipt_ids)} receipt IDs: {receipt_ids}")

    count_item = InventoryCountItem.objects.select_related('product', 'inventory_count').get(pk=count_item_id)
    product = count_item.product
    shortage_qty = Decimal(str(abs(count_item.variance_quantity))).quantize(Decimal('0.001'))
    logger.debug(f"Product: '{product.name}' (ID: {product.id}), Total shortage quantity: {shortage_qty}.")

    if shortage_qty <= 0 or product.product_type != Product.ProductType.FINAL_PRODUCT:
        logger.warning(f"Skipping auto-distribution for product '{product.name}': Shortage is zero or not a final product.")
        return []

    # --- ROBUST SUBQUERY APPROACH TO PREVENT JOIN MULTIPLICATION ---
    
    # Subquery for total dispatched
    dispatched_subquery = FinishedProductDispatch.objects.filter(
        sales_order_item__finished_product_id=OuterRef('pk')
    ).values('sales_order_item__finished_product_id').annotate(total=Sum('quantity')).values('total')

    # Subquery for total adjusted
    adjusted_subquery = InventoryAdjustment.objects.filter(
        source_finished_product_id=OuterRef('pk')
    ).values('source_finished_product_id').annotate(total=Sum('adjustment_quantity')).values('total')

    # Base query for receipts
    receipts_query = FinishedProductReceipt.objects.filter(
        batch__template__final_product=product
    ).exclude(status=FinishedProductReceipt.Status.REJECTED)

    # If specific receipt IDs are provided, filter the query
    if receipt_ids:
        receipts_query = receipts_query.filter(id__in=receipt_ids)
    
    # Annotate with the correct remaining quantity using subqueries
    receipts_with_remaining_qs = receipts_query.annotate(
        total_dispatched=Coalesce(Subquery(dispatched_subquery, output_field=FloatField()), 0.0),
        total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
    ).annotate(
        remaining_quantity=F('total_quantity_produced') - F('total_dispatched') + F('total_adjusted')
    ).filter(remaining_quantity__gt=0.001).order_by('release_date') # Oldest first (FIFO) for distribution

    receipts_with_remaining = [
        {
            'receipt': r,
            'remaining_quantity': Decimal(str(r.remaining_quantity)),
            'total_cost': r.total_cost,
            'total_quantity_produced': Decimal(str(r.total_quantity_produced))
        } for r in receipts_with_remaining_qs
    ]
    
    logger.debug(f"Found {len(receipts_with_remaining)} receipts with remaining stock after precise calculation.")

    adjustments = []
    
    # --- NEW PROPORTIONAL DISTRIBUTION LOGIC ---
    total_available_from_selection = sum(r['remaining_quantity'] for r in receipts_with_remaining)
    
    if total_available_from_selection < shortage_qty:
        error_msg = f"لا يمكن توزيع عجز بقيمة {shortage_qty}. الدفعات المحددة لديها فقط {total_available_from_selection} متوفر."
        logger.error(error_msg)
        raise ValidationError(error_msg)

    qty_to_distribute = shortage_qty
    num_batches = len(receipts_with_remaining)

    if num_batches == 0:
        return [] # Should be caught by the validation above, but as a safeguard.

    # --- REVISED: Proportional Distribution Logic ---
    adjustments_to_make = {}
    running_total = Decimal('0.0')

    for i, r_data in enumerate(receipts_with_remaining):
        receipt_id = r_data['receipt'].id
        
        # For the last item, assign the remaining shortage to avoid rounding errors
        if i == num_batches - 1:
            adjustment_for_this_receipt = qty_to_distribute - running_total
        else:
            proportion = r_data['remaining_quantity'] / total_available_from_selection
            adjustment_for_this_receipt = (qty_to_distribute * proportion).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        
        adjustments_to_make[receipt_id] = adjustment_for_this_receipt
        running_total += adjustment_for_this_receipt
    # --- END: Proportional Distribution Logic ---


    # First, delete any existing adjustments for this count item
    logger.warning(f"Deleting existing adjustments for count {count_item.inventory_count.id} and product {product.id} before auto-distributing.")
    InventoryAdjustment.objects.filter(inventory_count=count_item.inventory_count, product=product).delete()


    with transaction.atomic():
        for r_data in receipts_with_remaining:
            receipt = r_data['receipt']
            adjustment_for_this_receipt = adjustments_to_make.get(receipt.id, Decimal('0.0'))

            if adjustment_for_this_receipt > 0:
                cost_per_unit = (r_data['total_cost'] / r_data['total_quantity_produced']) if r_data['total_quantity_produced'] > 0 else product.moving_average_cost

                logger.info(f"Creating PROPORTIONAL adjustment of {-adjustment_for_this_receipt} against receipt {receipt.id} with cost {cost_per_unit}.")
                adj = InventoryAdjustment.objects.create(
                    product=product,
                    adjustment_quantity=-float(adjustment_for_this_receipt),
                    adjustment_date=timezone.now(),
                    cost_at_adjustment=cost_per_unit,
                    reason_code=reason,
                    notes=f"{notes} (Auto-distributed)",
                    source_finished_product=receipt,
                    inventory_count=count_item.inventory_count
                )
                adjustments.append(adj)

    final_distributed_qty = sum(Decimal(str(adj.adjustment_quantity)) for adj in adjustments)
    logger.info(f"Finished auto-distribution for count item {count_item_id}. Created {len(adjustments)} adjustments totaling {final_distributed_qty}.")

    if abs(final_distributed_qty) != qty_to_distribute:
         logger.error(f"CRITICAL LOGIC ERROR: Intended to distribute {qty_to_distribute} but only distributed {abs(final_distributed_qty)}")

    return adjustments


def finalize_inventory_count(count_id: int):
    """
    Finalizes the count, triggers cost recalculation for all affected products,
    and marks the count as Completed.
    """
    logger.info(f"Finalizing inventory count ID {count_id}.")
    count = InventoryCount.objects.get(pk=count_id)
    products_to_recalculate = set(
        count.adjustments.values_list('product_id', flat=True)
    )
    logger.debug(f"Products to recalculate cost for: {products_to_recalculate}.")

    if not products_to_recalculate:
        logger.warning(f"No adjustments found for count {count_id}. Nothing to recalculate. Finalizing anyway.")
        count.status = InventoryCount.CountStatus.COMPLETED
        count.save(update_fields=['status'])
        return

    # Use a date at the beginning of the day of the earliest adjustment
    start_recalc_date = count.adjustments.earliest('adjustment_date').adjustment_date
    start_recalc_date = start_recalc_date.replace(hour=0, minute=0, second=0, microsecond=0)
    logger.debug(f"Cost recalculation will start from {start_recalc_date}.")

    for product_id in products_to_recalculate:
        logger.info(f"Triggering cost recalculation for product ID {product_id}.")
        recalculate_cost_history_for_product(product_id, start_recalc_date)
    
    count.status = InventoryCount.CountStatus.COMPLETED
    count.save(update_fields=['status'])
    logger.info(f"Successfully finalized Inventory Count {count.id} and triggered all cost recalculations.")
