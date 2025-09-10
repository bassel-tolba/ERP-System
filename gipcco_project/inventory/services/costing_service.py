# gipcco_project/inventory/services/costing_service.py

import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (
    Product, InventoryLog, OpeningBalance, BatchItem,
    ProductionReturn, InventoryConsumption
)

logger = logging.getLogger(__name__)


def get_inventory_state_at_datetime(product_id: int, target_datetime: timezone.datetime) -> dict:
    """
    Calculates the total stock quantity and its total value for a product up to a specific datetime.
    This is a core function for historical valuation and ledger calculations.
    It correctly handles all transaction types: receipts, returns, production consumption, and internal consumption.
    """
    most_recent_ob = OpeningBalance.objects.filter(
        product_id=product_id, balance_date__lt=target_datetime
    ).order_by('-balance_date').first()

    if most_recent_ob:
        running_qty = Decimal(str(most_recent_ob.quantity))
        running_value = most_recent_ob.total_value
        effective_date = most_recent_ob.balance_date
    else:
        running_qty = Decimal('0.0')
        running_value = Decimal('0.0')
        # Use a very old date as the floor if no opening balance exists
        effective_date = timezone.make_aware(datetime.min)

    # Query all relevant transaction types within the date range
    logs = InventoryLog.objects.filter(
        product_id=product_id,
        status=InventoryLog.Status.RELEASED,
        release_timestamp__gte=effective_date,
        release_timestamp__lt=target_datetime
    )
    batch_consumptions = BatchItem.objects.filter(
        primitive_product_id=product_id,
        batch__creation_date__gte=effective_date,
        batch__creation_date__lt=target_datetime
    )
    returns = ProductionReturn.objects.filter(
        product_id=product_id,
        return_date__gte=effective_date,
        return_date__lt=target_datetime
    )
    internal_consumptions = InventoryConsumption.objects.filter(
        product_id=product_id,
        consumption_date__gte=effective_date,
        consumption_date__lt=target_datetime
    )

    # Combine and sort all transactions chronologically
    transactions = sorted(
        list(logs) + list(batch_consumptions) + list(returns) + list(internal_consumptions),
        key=lambda x: (
            x.release_timestamp if isinstance(x, InventoryLog) else
            x.batch.creation_date if isinstance(x, BatchItem) else
            x.consumption_date if isinstance(x, InventoryConsumption) else
            x.return_date,
            # Prioritize IN transactions within the same timestamp
            1 if isinstance(x, (InventoryLog, ProductionReturn)) else 2
        )
    )

    # Process each transaction to calculate the final state
    for trx in transactions:
        current_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')

        if isinstance(trx, InventoryLog):
            # Incoming goods increase quantity and value based on their purchase price
            incoming_qty = Decimal(str(trx.quantity))
            running_value += incoming_qty * trx.costing_unit_price
            running_qty += incoming_qty

        elif isinstance(trx, ProductionReturn):
            # Returned goods increase quantity and value, ideally at their original cost
            return_qty = Decimal(str(trx.quantity))
            cost_of_return = trx.source_log.costing_unit_price if trx.source_log else current_avg_cost
            running_value += return_qty * cost_of_return
            running_qty += return_qty

        elif isinstance(trx, BatchItem):
            # Goods consumed by production decrease quantity and value based on the running MAC
            consumed_qty = Decimal(str(trx.actual_quantity or 0.0))
            running_value -= consumed_qty * current_avg_cost
            running_qty -= consumed_qty
        
        elif isinstance(trx, InventoryConsumption):
            # Goods used internally decrease quantity and value based on their recorded cost at consumption
            consumed_qty = Decimal(str(trx.quantity_consumed))
            # NOTE: For internal consumptions, we subtract the pre-calculated total cost,
            # as its unit cost is fixed from its source log at the time of creation.
            running_value -= trx.cost_at_consumption
            running_qty -= consumed_qty

    return {'quantity': running_qty, 'value': running_value}


def recalculate_cost_history_for_product(product_id: int, start_datetime: timezone.datetime):
    """
    Recalculates the entire cost and consumption history for a product from a specific point in time.
    This is the "master" function for ensuring data integrity after any historical change.
    It updates the 'cost_at_consumption' for all affected BatchItems and the final 'moving_average_cost' on the Product.
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        logger.info(f"Starting cost recalculation for '{product.name}' from {start_datetime.date()}...")

        # Get the inventory state (quantity and value) just before the recalculation start time.
        state = get_inventory_state_at_datetime(product_id, start_datetime)
        running_qty = state['quantity']
        running_value = state['value']

        # Query all transactions that occurred *after* the start time
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
        # Note: Internal consumptions don't need recalculation as their cost is fixed,
        # but they are accounted for in get_inventory_state_at_datetime.

        transactions = sorted(
            list(logs) + list(batch_consumptions) + list(returns),
            key=lambda x: (
                x.release_timestamp if isinstance(x, InventoryLog) else
                x.batch.creation_date if isinstance(x, BatchItem) else
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

        # Perform a single bulk update for efficiency
        if batch_items_to_update:
            BatchItem.objects.bulk_update(batch_items_to_update, ['cost_at_consumption'])
            logger.info(f"Updated cost_at_consumption for {len(batch_items_to_update)} batch items of '{product.name}'.")

        # Finally, update the product's official Moving Average Cost to the latest calculated value
        final_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')
        product.moving_average_cost = final_avg_cost.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        logger.info(f"Finished recalculating cost history for '{product.name}'. New MAC: {product.moving_average_cost}")