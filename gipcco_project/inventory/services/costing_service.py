# gipcco_project/inventory/services/costing_service.py

import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q, F, FloatField, DecimalField, Case, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (
    Product, InventoryLog, OpeningBalance, BatchItem,
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

    # Get the most recent opening balance before the target time
    most_recent_ob = OpeningBalance.objects.filter(
        product_id=product_id, balance_date__lt=target_datetime
    ).order_by('-balance_date').first()

    running_qty = Decimal(str(most_recent_ob.quantity)) if most_recent_ob else Decimal('0.0')
    running_value = most_recent_ob.total_value if most_recent_ob else Decimal('0.0')
    effective_date = most_recent_ob.balance_date if most_recent_ob else timezone.make_aware(datetime.min)

    # --- Logic for Final Products ---
    if product.product_type == Product.ProductType.FINAL_PRODUCT:
        # --- INFLOWS ---
        receipts_query = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id,
            receipt_date__lte=target_datetime.date() # --- FIX: Use __lte to include same-day transactions
        )
        # We must also filter out receipts that might be on the same day but in the future, if we had a time field.
        # Since we only have a date, lte is the best approximation.

        if not include_quarantined:
            receipts_query = receipts_query.filter(status=FinishedProductReceipt.Status.RELEASED)
        else:
            receipts_query = receipts_query.exclude(status=FinishedProductReceipt.Status.REJECTED)
        
        receipt_inflows = receipts_query.aggregate(
            total_qty=Coalesce(Sum('total_quantity_produced'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum('total_cost'), Decimal('0.0'), output_field=DecimalField())
        )

        # --- OUTFLOWS ---
        dispatch_outflows = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0'), output_field=DecimalField())
        )

        # --- ADJUSTMENTS ---
        adjustments = InventoryAdjustment.objects.filter(
            product_id=product_id,
            adjustment_date__lte=target_datetime,
            source_finished_product__isnull=False
        ).aggregate(
            total_qty=Coalesce(Sum('adjustment_quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('adjustment_quantity') * F('cost_at_adjustment')), Decimal('0.0'), output_field=DecimalField())
        )

        final_quantity = running_qty + receipt_inflows['total_qty'] - Decimal(str(dispatch_outflows['total_qty'])) + Decimal(str(adjustments['total_qty']))
        final_value = running_value + receipt_inflows['total_val'] - dispatch_outflows['total_val'] + adjustments['total_val']

    # --- Logic for Raw Materials, MRO, Consumables, etc. ---
    else:
        # --- INFLOWS ---
        logs_query = InventoryLog.objects.filter(
            product_id=product_id, timestamp__gte=effective_date, timestamp__lte=target_datetime
        )
        if not include_quarantined:
            logs_query = logs_query.filter(status=InventoryLog.Status.RELEASED)
        else:
            logs_query = logs_query.exclude(status__in=[InventoryLog.Status.REJECTED, InventoryLog.Status.SCRAPPED])
        
        # --- FIX: Replace F('costing_unit_price') with a Case expression ---
        # The 'costing_unit_price' is a model property, not a DB field, so it cannot be used in aggregations.
        # We must replicate its logic directly in the query.
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

        # --- FIX: Same as above for ProductionReturn which joins on InventoryLog ---
        source_log_costing_unit_price = Case(
            When(
                Q(source_log__quantity__gt=0) & Q(source_log__vat_treatment=InventoryLog.VatTreatment.CAPITALIZED),
                then=((F('source_log__base_unit_price') * F('source_log__quantity')) + F('source_log__vat_amount')) / F('source_log__quantity')
            ),
            When(
                Q(source_log__quantity__gt=0),
                then=F('source_log__base_unit_price')
            ),
            default=Decimal('0.0'),
            output_field=DecimalField()
        )
        return_total_val_expression = Sum(F('quantity') * source_log_costing_unit_price)

        return_inflows = ProductionReturn.objects.filter(
            product_id=product_id, return_date__gte=effective_date, return_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(return_total_val_expression, Decimal('0.0'), output_field=DecimalField())
        )

        # --- OUTFLOWS ---
        batch_outflows = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=effective_date, batch__creation_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('actual_quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('actual_quantity') * F('cost_at_consumption')), Decimal('0.0'), output_field=DecimalField())
        )
        
        consumption_outflows = InventoryConsumption.objects.filter(
            product_id=product_id, consumption_date__gte=effective_date, consumption_date__lte=target_datetime
        ).aggregate(
            total_qty=Coalesce(Sum('quantity_consumed'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('quantity_consumed') * F('cost_at_consumption')), Decimal('0.0'), output_field=DecimalField())
        )

        # --- ADJUSTMENTS ---
        adjustments = InventoryAdjustment.objects.filter(
            product_id=product_id, adjustment_date__gte=effective_date, adjustment_date__lte=target_datetime, source_log__isnull=False
        ).aggregate(
            total_qty=Coalesce(Sum('adjustment_quantity'), Decimal('0.0'), output_field=DecimalField()),
            total_val=Coalesce(Sum(F('adjustment_quantity') * F('cost_at_adjustment')), Decimal('0.0'), output_field=DecimalField())
        )

        final_quantity = (running_qty + 
                        Decimal(str(log_inflows['total_qty'])) + 
                        Decimal(str(return_inflows['total_qty'])) - 
                        Decimal(str(batch_outflows['total_qty'])) - 
                        Decimal(str(consumption_outflows['total_qty'])) + 
                        Decimal(str(adjustments['total_qty'])))
        
        final_value = (running_value + 
                       log_inflows['total_val'] + 
                       return_inflows['total_val'] - 
                       batch_outflows['total_val'] - 
                       consumption_outflows['total_val'] + 
                       adjustments['total_val'])

    return {'quantity': final_quantity, 'value': final_value}


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

        # Query all transactions that occurred *at or after* the start time
        logs = InventoryLog.objects.filter(
            product_id=product_id,
            status=InventoryLog.Status.RELEASED,
            release_timestamp__gte=start_datetime
        )
        batch_consumptions = BatchItem.objects.filter(
            primitive_product_id=product_id,
            batch__creation_date__gte=start_datetime
        )
        returns = ProductionReturn.objects.filter(
            product_id=product_id,
            return_date__gte=start_datetime
        )
        adjustments = InventoryAdjustment.objects.filter(
            product_id=product_id,
            adjustment_date__gte=start_datetime
        )

        transactions = sorted(
            list(logs) + list(batch_consumptions) + list(returns) + list(adjustments),
            key=lambda x: (
                x.release_timestamp if isinstance(x, InventoryLog) else
                x.batch.creation_date if isinstance(x, BatchItem) else
                x.adjustment_date if isinstance(x, InventoryAdjustment) else
                x.return_date,
                1 if isinstance(x, (InventoryLog, ProductionReturn)) else 2
            )
        )

        batch_items_to_update = []

        # Process transactions chronologically, updating costs as we go
        for trx in transactions:
            current_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')

            if isinstance(trx, InventoryLog):
                incoming_qty = Decimal(str(trx.quantity))
                running_value += incoming_qty * trx.costing_unit_price
                running_qty += incoming_qty

            elif isinstance(trx, ProductionReturn):
                return_qty = Decimal(str(trx.quantity))
                cost_of_return = trx.source_log.costing_unit_price if trx.source_log else current_avg_cost
                running_value += return_qty * cost_of_return
                running_qty += return_qty

            elif isinstance(trx, BatchItem):
                # This is the critical step: update the BatchItem's cost
                new_cost = current_avg_cost.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                if trx.cost_at_consumption != new_cost:
                    trx.cost_at_consumption = new_cost
                    batch_items_to_update.append(trx)

                # Update the running value and quantity
                consumed_qty = Decimal(str(trx.actual_quantity or 0.0))
                running_value -= consumed_qty * new_cost
                running_qty -= consumed_qty
            
            elif isinstance(trx, InventoryAdjustment):
                adjustment_qty = Decimal(str(trx.adjustment_quantity))
                # The cost_at_adjustment is determined authoritatively when the
                # adjustment is created. The recalculation service should respect this
                # value and not attempt to recalculate it.
                cost = trx.cost_at_adjustment
                
                # Update running totals using the authoritative cost.
                running_value += adjustment_qty * cost
                running_qty += adjustment_qty


        # Perform a single bulk update for efficiency
        if batch_items_to_update:
            BatchItem.objects.bulk_update(batch_items_to_update, ['cost_at_consumption'])
            logger.info(f"Updated cost_at_consumption for {len(batch_items_to_update)} batch items of '{product.name}'.")

        # Finally, update the product's official Moving Average Cost to the latest calculated value
        final_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')
        product.moving_average_cost = final_avg_cost.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        logger.info(f"Finished recalculating cost history for '{product.name}'. New MAC: {product.moving_average_cost}")