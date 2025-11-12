# gipcco_project/inventory/services/costing_service.py

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q, F, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from .accounting._helpers import _check_period_is_open

from ..models import (
    Product, InventoryLog, BatchItem, Batch,
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

    running_qty = Decimal('0.0')
    running_value = Decimal('0.0')

    # --- INFLOWS ---
    # 1. Raw Material Receipts
    logs_query = InventoryLog.objects.filter(
        product_id=product_id, timestamp__lte=target_datetime
    )
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        logs_query = logs_query.none()

    if not include_quarantined:
        logs_query = logs_query.filter(status=InventoryLog.Status.RELEASED)
    else:
        logs_query = logs_query.exclude(status__in=[
            InventoryLog.Status.REJECTED, 
            InventoryLog.Status.SCRAPPED,
            InventoryLog.Status.VOIDED
        ])
    
    # CORRECTED: Use the final, immutable 'costing_unit_price' for valuation.
    # This field already includes capitalized VAT and landed costs.
    # Recalculating from base_unit_price is incorrect and can lead to discrepancies.
    log_inflows = logs_query.aggregate(
        total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum(F('quantity') * F('costing_unit_price')), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty += log_inflows['total_qty']
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
        # CORRECTED: Value returns based on the source log's full 'costing_unit_price', not its 'base_unit_price'.
        return_inflows = ProductionReturn.objects.filter(
            product_id=product_id, return_date__lte=target_datetime
        ).exclude(status=ProductionReturn.Status.CANCELLED).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('quantity') * F('source_log__costing_unit_price')), Decimal('0.0'), output_field=DecimalField())
        )
        running_qty += return_inflows['total_qty']
        running_value += return_inflows['total_val']


    # --- OUTFLOWS ---
    # 1. Production Consumption (Outflow for Raw Materials)
    consumption_outflows = BatchItem.objects.filter(
        primitive_product_id=product_id, batch__creation_date__lte=target_datetime
    ).exclude(batch__status=Batch.Status.CANCELLED).aggregate(
        total_qty=Coalesce(Sum('actual_quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum(F('actual_quantity') * F('cost_at_consumption')), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty -= consumption_outflows['total_qty']
    running_value -= consumption_outflows['total_val']

    # 2. Internal Consumption (MRO, etc.)
    internal_use_outflows = InventoryConsumption.objects.filter(
        product_id=product_id, consumption_date__lte=target_datetime
    ).aggregate(
        total_qty=Coalesce(Sum('quantity_consumed'), Decimal('0.0'), output_field=DecimalField()),
        # NOTE: 'cost_at_consumption' on this model is the TOTAL cost of the transaction, not a unit cost. Summing it is correct.
        total_val=Coalesce(Sum('cost_at_consumption'), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty -= internal_use_outflows['total_qty']
    running_value -= internal_use_outflows['total_val']

    # 3. Sales Dispatches (Outflow for Finished Goods)
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        dispatch_outflows = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__lte=target_datetime,
            status=FinishedProductDispatch.Status.COMPLETED
        ).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            # NOTE: 'cost_at_dispatch' is the TOTAL cost of the transaction, not a unit cost. Summing it is correct.
            total_val=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0'), output_field=DecimalField())
        )
        running_qty -= dispatch_outflows['total_qty']
        running_value -= dispatch_outflows['total_val']

    # --- ADJUSTMENTS (In or Out) ---
    adjustments = InventoryAdjustment.objects.filter(
        product_id=product_id,
        adjustment_date__lte=target_datetime
    ).aggregate(
        total_qty=Coalesce(Sum('adjustment_quantity'), Decimal('0.0'), output_field=DecimalField()),
        total_val=Coalesce(Sum(F('adjustment_quantity') * F('cost_at_adjustment')), Decimal('0.0'), output_field=DecimalField())
    )
    running_qty += adjustments['total_qty']
    running_value += adjustments['total_val']
    
    return {
        'quantity': running_qty.quantize(Decimal('0.0001')),
        'value': running_value.quantize(Decimal('0.001'))
    }


def recalculate_cost_history_for_product(product_id: int, start_datetime: timezone.datetime):
    """
    REDEFINED: This function is now a non-destructive calculator.
    Its SOLE purpose is to re-calculate the current moving average cost of a product
    based on its transaction history from a specific point in time.

    IT DOES NOT MODIFY HISTORICAL TRANSACTIONS. It no longer updates 'cost_at_consumption'
    or any other fields on past records. This change is critical to enforce ledger
    immutability. The function's only write operation is to update the
    `moving_average_cost` field on the Product model itself.
    """
    # --- IMMUTABILITY CHECK ---
    # We still check the period to ensure that any action triggering this recalculation
    # is initiated from a valid, open financial period.
    _check_period_is_open(start_datetime.date())
    
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        logger.info(f"Starting MOVING AVERAGE COST recalculation for '{product.name}' from {start_datetime.date()}...")

        # Get the inventory state (quantity and value) just before the recalculation start time.
        state_time = start_datetime - timedelta(microseconds=1)
        state = get_inventory_state_at_datetime(product_id, state_time, include_quarantined=True)
        running_qty = state['quantity']
        running_value = state['value']

        # 1. Get all relevant transactions for the product, sorted chronologically.
        
        # Inflows
        in_logs = InventoryLog.objects.filter(
            product_id=product_id, release_timestamp__gte=start_datetime
        ).values('release_timestamp', 'quantity', 'costing_unit_price')
        
        fg_receipts = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id,
            release_date__gte=start_datetime.date()
        ).annotate(
            unit_cost=Case(
                When(total_quantity_produced__gt=0, then=(F('total_cost') + F('allocated_overhead_cost')) / F('total_quantity_produced')),
                default=Decimal('0.0'),
                output_field=DecimalField()
            )
        ).values('release_date', 'total_quantity_produced', 'unit_cost')

        # CORRECTED: Use the full 'costing_unit_price' from the source log for returns.
        in_returns = ProductionReturn.objects.filter(
            product_id=product_id, return_date__gte=start_datetime
        ).annotate(
            costing_unit_price=F('source_log__costing_unit_price')
        ).values('return_date', 'quantity', 'costing_unit_price')

        # Outflows
        out_batch_items = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=start_datetime
        ).exclude(batch__status=Batch.Status.CANCELLED).values('batch__creation_date', 'actual_quantity', 'cost_at_consumption')

        out_dispatches = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__gte=start_datetime,
            status=FinishedProductDispatch.Status.COMPLETED
        ).values('dispatch_date', 'quantity', 'cost_at_dispatch')

        out_consumptions = InventoryConsumption.objects.filter(
            product_id=product_id, consumption_date__gte=start_datetime
        ).values('consumption_date', 'quantity_consumed', 'cost_at_consumption')

        # Adjustments
        adjustments = InventoryAdjustment.objects.filter(
            product_id=product_id, 
            adjustment_date__gte=start_datetime, 
            status=InventoryAdjustment.Status.POSTED
        ).values('adjustment_date', 'adjustment_quantity', 'cost_at_adjustment')

        # 2. Combine and sort all transactions
        transactions = []
        for log in in_logs:
            transactions.append({
                'date': log['release_timestamp'], 'type': 'INFLOW',
                'qty': log['quantity'], 'cost': log['costing_unit_price'],
            })
        for receipt in fg_receipts:
            transactions.append({
                'date': timezone.make_aware(datetime.combine(receipt['release_date'], datetime.min.time())),
                'type': 'INFLOW', 'qty': receipt['total_quantity_produced'], 'cost': receipt['unit_cost'],
            })
        for ret in in_returns:
            transactions.append({
                'date': ret['return_date'], 'type': 'INFLOW',
                'qty': ret['quantity'], 'cost': ret['costing_unit_price'],
            })
        for item in out_batch_items:
            transactions.append({
                'date': item['batch__creation_date'], 'type': 'OUTFLOW',
                'qty': item['actual_quantity'], 'cost': item['cost_at_consumption']
            })
        for dispatch in out_dispatches:
            cost_per_unit = dispatch['cost_at_dispatch'] / dispatch['quantity'] if dispatch['quantity'] > 0 else Decimal('0.0')
            transactions.append({
                'date': dispatch['dispatch_date'], 'type': 'OUTFLOW',
                'qty': dispatch['quantity'], 'cost': cost_per_unit
            })
        for cons in out_consumptions:
            cost_per_unit = cons['cost_at_consumption'] / cons['quantity_consumed'] if cons['quantity_consumed'] > 0 else Decimal('0.0')
            transactions.append({
                'date': cons['consumption_date'], 'type': 'OUTFLOW',
                'qty': cons['quantity_consumed'], 'cost': cost_per_unit
            })
        for adj in adjustments:
            transactions.append({
                'date': adj['adjustment_date'], 'type': 'ADJUSTMENT',
                'qty': adj['adjustment_quantity'], 'cost': adj['cost_at_adjustment'],
            })

        transactions.sort(key=lambda x: x['date'])

        # 3. Iterate through transactions and calculate final state. DO NOT update historical records.
        for t in transactions:
            qty = t.get('qty') or Decimal('0.0')
            cost = t.get('cost') or Decimal('0.0')

            if t['type'] == 'INFLOW':
                running_value += qty * cost
                running_qty += qty
            
            elif t['type'] == 'OUTFLOW':
                # We now use the historical cost from the record, not a recalculated one.
                # The purpose is to find the final state, not to change the past.
                running_value -= qty * cost
                running_qty -= qty

            elif t['type'] == 'ADJUSTMENT':
                # Adjustments change quantity and value based on their recorded cost.
                running_value += qty * cost
                running_qty += qty

        # 4. Update the final moving average cost on the product itself. This is the only write operation.
        final_mac = running_value / running_qty if running_qty > 0 else Decimal('0.0')
        product.moving_average_cost = final_mac.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        
        logger.info(f"Finished recalculating MOVING AVERAGE COST for '{product.name}'. New MAC: {product.moving_average_cost}")
