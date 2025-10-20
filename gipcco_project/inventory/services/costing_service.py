# gipcco_project/inventory/services/costing_service.py

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q, F, FloatField, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (
    Product, InventoryLog, BatchItem,
    ProductionReturn, InventoryConsumption, InventoryAdjustment, FinishedProductReceipt,
    FinishedProductDispatch
)

logger = logging.getLogger(__name__)


def get_inventory_state_at_datetime(
    product_id: int, 
    target_datetime: timezone.datetime,
    include_quarantined: bool = True
) -> dict:
    """
    Calculates the total stock quantity and its total value for a product up to a specific datetime.
    This is a core function for historical valuation and ledger calculations.
    It uses aggregation for robustness and correctly handles the include_quarantined flag.
    """
    product = Product.objects.get(pk=product_id)

    # The concept of a separate OpeningBalance model is removed. The state is calculated
    # from the beginning of transaction history.
    running_qty = Decimal('0.0')
    running_value = Decimal('0.0')

    # --- Combined Logic for All Product Types ---

    # --- INFLOWS ---
    # 1. Raw Material Receipts
    logs_query = InventoryLog.objects.filter(
        product_id=product_id, timestamp__lte=target_datetime
    )
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        # Final products are handled by FinishedProductReceipt, so ignore logs for them here.
        logs_query = logs_query.none()

    if not include_quarantined:
        logs_query = logs_query.filter(status=InventoryLog.Status.RELEASED)
    else:
        logs_query = logs_query.exclude(status__in=[InventoryLog.Status.REJECTED, InventoryLog.Status.SCRAPPED])
    
    log_total_val_expression = Sum(
        Case(
            When(
                vat_treatment=InventoryLog.VatTreatment.CAPITALIZED,
                then=(F('base_unit_price') * F('quantity')) + F('vat_amount')
            ),
            default=(F('base_unit_price') * F('quantity')),
            output_field=DecimalField()
        )
    )
    log_inflows = logs_query.aggregate(
        total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(log_total_val_expression, Decimal('0.0'), output_field=DecimalField())
    )
    running_qty += Decimal(str(log_inflows['total_qty']))
    running_value += log_inflows['total_val']

    # 2. Finished Good Receipts
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        receipts_query = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id,
            receipt_date__lte=target_datetime.date()
        )
        if not include_quarantined:
            receipts_query = receipts_query.filter(status=FinishedProductReceipt.Status.RELEASED)
        else:
            receipts_query = receipts_query.exclude(status=FinishedProductReceipt.Status.REJECTED)
        
        receipt_inflows = receipts_query.aggregate(
            total_qty=Coalesce(Sum('total_quantity_produced'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('total_cost') + F('allocated_overhead_cost')), Decimal('0.0'), output_field=DecimalField())
        )
        running_qty += receipt_inflows['total_qty']
        running_value += receipt_inflows['total_val']

    # 3. Production Returns (Inflow for Raw Materials)
    if product.product_type != Product.ProductType.FINAL_PRODUCT:
        return_inflows = ProductionReturn.objects.filter(
            product_id=product_id, return_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('quantity') * F('source_log__base_unit_price')), Decimal('0.0'), output_field=DecimalField()) # Simplified valuation
        )
        running_qty += Decimal(str(return_inflows['total_qty']))
        running_value += return_inflows['total_val']


    # --- OUTFLOWS ---
    # 1. Production Consumption (Outflow for Raw Materials)
    consumption_outflows = BatchItem.objects.filter(
        primitive_product_id=product_id, batch__creation_date__lte=target_datetime
    ).aggregate(
        total_qty=Coalesce(Sum('actual_quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum(F('actual_quantity') * F('cost_at_consumption')), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty -= Decimal(str(consumption_outflows['total_qty']))
    running_value -= consumption_outflows['total_val']

    # 2. Internal Consumption (MRO, etc.)
    internal_use_outflows = InventoryConsumption.objects.filter(
        product_id=product_id, consumption_date__lte=target_datetime
    ).aggregate(
        total_qty=Coalesce(Sum('quantity_consumed'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum('cost_at_consumption'), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty -= Decimal(str(internal_use_outflows['total_qty']))
    running_value -= internal_use_outflows['total_val']

    # 3. Sales Dispatches (Outflow for Finished Goods)
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        dispatch_outflows = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0'), output_field=DecimalField())
        )
        running_qty -= Decimal(str(dispatch_outflows['total_qty']))
        running_value -= dispatch_outflows['total_val']

    # --- ADJUSTMENTS (In or Out) ---
    adjustments = InventoryAdjustment.objects.filter(
        product_id=product_id,
        adjustment_date__lte=target_datetime
    ).aggregate(
        total_qty=Coalesce(Sum('adjustment_quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum(F('adjustment_quantity') * F('cost_at_adjustment')), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty += Decimal(str(adjustments['total_qty']))
    running_value += adjustments['total_val']
    
    return {
        'quantity': running_qty.quantize(Decimal('0.001')),
        'value': running_value.quantize(Decimal('0.001'))
    }


def recalculate_cost_history_for_product(product_id: int, start_datetime: timezone.datetime):
    """
    Recalculates the entire cost and consumption history for a product from a specific point in time.
    This is the "master" function for ensuring data integrity after any historical change.
    It updates the 'cost_at_consumption' for all affected BatchItems and the final 'moving_average_cost' on the Product.
    """
    # This function is complex and its logic remains unchanged for now, but it will benefit from the more accurate
    # starting state provided by the refactored get_inventory_state_at_datetime.
    # We will call the function with its default behavior (include_quarantined=True) for costing.
    
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        logger.info(f"Starting cost recalculation for '{product.name}' from {start_datetime.date()}...")

        # Get the inventory state (quantity and value) just before the recalculation start time.
        # For costing, we should always consider all stock to get the correct value basis.
        state_time = start_datetime - timedelta(microseconds=1)
        state = get_inventory_state_at_datetime(product_id, state_time, include_quarantined=True)
        running_qty = state['quantity']
        running_value = state['value']

        # 1. Get all relevant transactions for the product, sorted chronologically.
        # This now includes transactions for both raw materials and finished goods.
        
        # Raw Material Inflows
        in_logs_query = InventoryLog.objects.filter(
            product_id=product_id, release_timestamp__gte=start_datetime
        )
        
        in_logs = in_logs_query.values('release_timestamp', 'quantity', 'costing_unit_price', 'id')
        
        # Finished Good Inflows
        fg_receipts = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id,
            release_date__gte=start_datetime.date()
        ).annotate(
            unit_cost=Case(
                When(total_quantity_produced__gt=0, then=(F('total_cost') + F('allocated_overhead_cost')) / F('total_quantity_produced')),
                default=Decimal('0.0'),
                output_field=DecimalField()
            )
        ).values('release_date', 'total_quantity_produced', 'unit_cost', 'id')

        # Raw Material Outflows (Production)
        out_batch_items = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=start_datetime
        ).values('batch__creation_date', 'actual_quantity', 'id')

        # Finished Good Outflows (Sales)
        out_dispatches = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__gte=start_datetime
        ).values('dispatch_date', 'quantity', 'id')

        # Raw Material Inflows (Returns)
        in_returns = ProductionReturn.objects.filter(
            product_id=product_id, return_date__gte=start_datetime
        ).annotate(
            costing_unit_price=F('source_log__base_unit_price') # Simplified valuation
        ).values('return_date', 'quantity', 'costing_unit_price', 'id')

        # MRO/Consumable Outflows
        out_consumptions = InventoryConsumption.objects.filter(
            product_id=product_id, consumption_date__gte=start_datetime
        ).values('consumption_date', 'quantity_consumed', 'id')

        # Adjustments (In or Out)
        adjustments = InventoryAdjustment.objects.filter(
            product_id=product_id, adjustment_date__gte=start_datetime
        ).values('adjustment_date', 'adjustment_quantity', 'cost_at_adjustment', 'id')

        # 2. Combine and sort all transactions
        transactions = []
        for log in in_logs:
            transactions.append({
                'date': log['release_timestamp'],
                'type': 'IN_LOG',
                'qty': Decimal(str(log['quantity'])),
                'cost': log['costing_unit_price'],
                'obj_id': log['id']
            })
        for receipt in fg_receipts:
            transactions.append({
                'date': timezone.make_aware(datetime.combine(receipt['release_date'], datetime.min.time())),
                'type': 'FG_RECEIPT',
                'qty': Decimal(str(receipt['total_quantity_produced'])),
                'cost': receipt['unit_cost'],
                'obj_id': receipt['id']
            })
        for item in out_batch_items:
            transactions.append({
                'date': item['batch__creation_date'],
                'type': 'OUT_BATCH',
                'qty': Decimal(str(item['actual_quantity'])),
                'obj_id': item['id']
            })
        for dispatch in out_dispatches:
            transactions.append({
                'date': dispatch['dispatch_date'],
                'type': 'OUT_DISPATCH',
                'qty': Decimal(str(dispatch['quantity'])),
                'obj_id': dispatch['id']
            })
        for ret in in_returns:
            transactions.append({
                'date': ret['return_date'],
                'type': 'IN_RETURN',
                'qty': Decimal(str(ret['quantity'])),
                'cost': ret['costing_unit_price'],
                'obj_id': ret['id']
            })
        for cons in out_consumptions:
            transactions.append({
                'date': cons['consumption_date'],
                'type': 'OUT_CONSUMPTION',
                'qty': Decimal(str(cons['quantity_consumed'])),
                'obj_id': cons['id']
            })
        for adj in adjustments:
            transactions.append({
                'date': adj['adjustment_date'],
                'type': 'ADJUSTMENT',
                'qty': Decimal(str(adj['adjustment_quantity'])),
                'cost': adj['cost_at_adjustment'], # Cost is pre-defined for adjustments
                'obj_id': adj['id']
            })

        transactions.sort(key=lambda x: x['date'])

        # 3. Iterate through transactions and update costs
        batch_items_to_update = []
        consumptions_to_update = []
        adjustments_to_update = []
        dispatches_to_update = []

        for t in transactions:
            if t['type'] in ['IN_LOG', 'IN_RETURN', 'FG_RECEIPT']:
                # Inflows update the running total
                running_value += t['qty'] * t['cost']
                running_qty += t['qty']
            
            elif t['type'] in ['OUT_BATCH', 'OUT_CONSUMPTION', 'OUT_DISPATCH']:
                # Outflows consume at the current moving average cost
                cost_at_consumption = running_value / running_qty if running_qty > 0 else Decimal('0.0')
                
                running_value -= t['qty'] * cost_at_consumption
                running_qty -= t['qty']

                # Mark the transaction object for update
                if t['type'] == 'OUT_BATCH':
                    item = BatchItem.objects.get(pk=t['obj_id'])
                    if item.cost_at_consumption != cost_at_consumption:
                        item.cost_at_consumption = cost_at_consumption
                        batch_items_to_update.append(item)
                elif t['type'] == 'OUT_CONSUMPTION':
                    item = InventoryConsumption.objects.get(pk=t['obj_id'])
                    if item.cost_at_consumption != (t['qty'] * cost_at_consumption):
                        item.cost_at_consumption = t['qty'] * cost_at_consumption
                        consumptions_to_update.append(item)
                elif t['type'] == 'OUT_DISPATCH':
                    item = FinishedProductDispatch.objects.get(pk=t['obj_id'])
                    total_cost = t['qty'] * cost_at_consumption
                    if item.cost_at_dispatch != total_cost:
                        item.cost_at_dispatch = total_cost
                        dispatches_to_update.append(item)

            elif t['type'] == 'ADJUSTMENT':
                # For adjustments, the cost is pre-determined. We just update the running totals.
                # --- MODIFICATION ---
                # For shortages, we MUST recalculate the cost based on the current MAC.
                # For overages, we use the cost stored on the adjustment itself.
                is_shortage = t['qty'] < 0
                if is_shortage:
                    cost_at_adjustment = running_value / running_qty if running_qty > 0 else Decimal('0.0')
                    item = InventoryAdjustment.objects.get(pk=t['obj_id'])
                    if item.cost_at_adjustment != cost_at_adjustment:
                        item.cost_at_adjustment = cost_at_adjustment
                        adjustments_to_update.append(item)
                    
                    running_value += t['qty'] * cost_at_adjustment # qty is negative
                else: # Overage
                    running_value += t['qty'] * t['cost']
                
                running_qty += t['qty']

        # 4. Perform bulk updates for efficiency
        with transaction.atomic():
            if batch_items_to_update:
                BatchItem.objects.bulk_update(batch_items_to_update, ['cost_at_consumption'])
                logger.info(f"Updated cost_at_consumption for {len(batch_items_to_update)} batch items of '{product.name}'.")
            if consumptions_to_update:
                InventoryConsumption.objects.bulk_update(consumptions_to_update, ['cost_at_consumption'])
            if adjustments_to_update:
                InventoryAdjustment.objects.bulk_update(adjustments_to_update, ['cost_at_adjustment'])
            if dispatches_to_update:
                FinishedProductDispatch.objects.bulk_update(dispatches_to_update, ['cost_at_dispatch'])

        # 5. Update the final moving average cost on the product itself
        final_mac = running_value / running_qty if running_qty > 0 else Decimal('0.0')
        product.moving_average_cost = final_mac.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        
        logger.info(f"Finished recalculating cost history for '{product.name}'. New MAC: {product.moving_average_cost}")