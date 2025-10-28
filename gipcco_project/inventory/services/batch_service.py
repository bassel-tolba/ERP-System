import logging
from datetime import datetime, time
from typing import List, Dict, Any, Tuple

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal
from django.utils.translation import gettext_lazy as _

from ..models import Batch, BatchItem, Product, JournalEntry, InventoryLog, ProductionReturn
from .accounting_service import create_je_for_production_consumption
from .costing_service import recalculate_cost_history_for_product, get_inventory_state_at_datetime
from .batch_helpers import validate_stock_availability, check_and_update_batch_customization

logger = logging.getLogger(__name__)


def create_batch(
    *,
    template_id: int,
    shop_order_number: str,
    batch_number_from: str,
    creation_date: datetime.date,
    items_data: List[Dict[str, Any]],
    batch_number_to: str = None,
    is_continuation: bool = False,
    parent_batch_id: int = None,
    notes: str = '',
    machine_hours_consumed: float = None,
    labor_hours_consumed: float = None
) -> Batch:
    """
    Creates a new Batch, its items, updates the item costs via MAC recalculation, 
    and creates the corresponding accounting journal entry within a single transaction.
    """
    if not all([template_id, shop_order_number, batch_number_from, creation_date, items_data]):
        raise ValidationError("Missing required data for batch creation.")

    is_valid, error_msg = validate_stock_availability(
        product_ids=[item['product_id'] for item in items_data],
        actual_quantities=[item['actual_quantity'] for item in items_data],
        source_log_ids=[item['source_log_id'] for item in items_data],
        batch_creation_date=creation_date
    )
    if not is_valid:
        raise ValidationError(error_msg)

    with transaction.atomic():
        final_batch_number = batch_number_from
        if batch_number_to and int(batch_number_to) >= int(batch_number_from):
            final_batch_number = f"{batch_number_from}-{batch_number_to}"
        
        creation_datetime = timezone.make_aware(datetime.combine(creation_date, time.min))

        batch = Batch.objects.create(
            template_id=template_id,
            shop_order_number=shop_order_number,
            batch_number=final_batch_number,
            creation_date=creation_datetime,
            is_customized=True, # Will be re-evaluated later
            is_continuation=is_continuation,
            parent_batch_id=parent_batch_id if is_continuation and parent_batch_id else None,
            notes=notes,
            machine_hours_consumed=machine_hours_consumed,
            labor_hours_consumed=labor_hours_consumed
        )

        # --- CRITICAL STEP 1: Create items and snapshot the cost ---
        items_to_create = []
        for item_data in items_data:
            state = get_inventory_state_at_datetime(item_data['product_id'], batch.creation_date)
            mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            
            items_to_create.append(
                BatchItem(
                    batch=batch,
                    primitive_product_id=item_data['product_id'],
                    theoretical_quantity=item_data['theoretical_quantity'],
                    actual_quantity=item_data['actual_quantity'],
                    source_log_id=item_data['source_log_id'],
                    cost_at_consumption=mac_at_consumption.quantize(Decimal('0.001'))
                )
            )
        BatchItem.objects.bulk_create(items_to_create)

        # --- CRITICAL STEP 2: Create the Journal Entry ---
        create_je_for_production_consumption(batch)

    # --- CRITICAL STEP 3: Update the final moving average cost on the products ---
    product_ids_to_recalc = {item['product_id'] for item in items_data}
    for pid in product_ids_to_recalc:
        recalculate_cost_history_for_product(pid, batch.creation_date)

    check_and_update_batch_customization(batch.id)
    logger.info(f"Successfully created Batch {batch.id} with {len(items_to_create)} items and its Journal Entry.")
    return batch


def update_batch(
    *,
    batch: Batch,
    shop_order_number: str,
    creation_date: datetime.date,
    batch_number_from: str,
    items_data: List[Dict[str, Any]],
    batch_number_to: str = None,
    is_continuation: bool = False,
    parent_batch_id: int = None,
    notes: str = '',
    machine_hours_consumed: float = None,
    labor_hours_consumed: float = None
) -> datetime:
    """
    Updates a Batch, its items, updates item costs, and recreates the journal entry 
    within a single transaction.
    """
    original_creation_date = batch.creation_date

    is_valid, error_msg = validate_stock_availability(
        product_ids=[item['product_id'] for item in items_data],
        actual_quantities=[item['actual_quantity'] for item in items_data],
        source_log_ids=[item['source_log_id'] for item in items_data],
        batch_creation_date=creation_date,
        batch_id_to_exclude=batch.pk
    )
    if not is_valid:
        raise ValidationError(error_msg)

    with transaction.atomic():
        # --- Delete the old Journal Entry first ---
        content_type = ContentType.objects.get_for_model(Batch)
        JournalEntry.objects.filter(content_type=content_type, object_id=batch.pk).delete()

        batch_to_update = Batch.objects.select_for_update().get(pk=batch.pk)
        
        batch_to_update.shop_order_number = shop_order_number
        batch_to_update.creation_date = timezone.make_aware(datetime.combine(creation_date, time.min))
        batch_to_update.notes = notes
        batch_to_update.is_continuation = is_continuation
        batch_to_update.parent_batch_id = parent_batch_id if is_continuation and parent_batch_id else None
        batch_to_update.machine_hours_consumed = machine_hours_consumed
        batch_to_update.labor_hours_consumed = labor_hours_consumed

        final_batch_number = batch_number_from
        if batch_number_to and int(batch_number_to) >= int(batch_number_from):
            final_batch_number = f"{batch_number_from}-{batch_number_to}"
        batch_to_update.batch_number = final_batch_number
        
        batch_to_update.save()

        items_in_db = {item.id: item for item in batch_to_update.items.all()}
        product_ids_to_recalc = set()
        
        for item_data in items_data:
            product_ids_to_recalc.add(item_data['product_id'])
            item = items_in_db.get(item_data['item_id'])
            if item:
                item.theoretical_quantity = item_data['theoretical_quantity']
                item.actual_quantity = item_data['actual_quantity']
                item.source_log_id = item_data['source_log_id'] or None
                
                # Re-snapshot the cost
                state = get_inventory_state_at_datetime(item_data['product_id'], batch_to_update.creation_date)
                mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
                item.cost_at_consumption = mac_at_consumption.quantize(Decimal('0.001'))
                
                item.save()

        # --- Recreate the Journal Entry with the updated data ---
        create_je_for_production_consumption(batch_to_update)

    # --- Update final MACs ---
    for pid in product_ids_to_recalc:
        recalculate_cost_history_for_product(pid, batch_to_update.creation_date)

    check_and_update_batch_customization(batch.pk)
    logger.info(f"Successfully updated Batch {batch.id} and recreated its Journal Entry.")
    
    return min(original_creation_date, batch_to_update.creation_date)


def add_item_to_batch(
    *, 
    batch: Batch, 
    product_id: int, 
    theoretical_quantity: float,
    actual_quantity: float,
    source_log_id: int
) -> BatchItem:
    """
    REDEFINED: Adds a supplemental item to an existing batch and creates a
    separate, auditable journal entry for that addition. Does not modify the
    original batch consumption JE.
    """
    from .accounting_service import create_je_for_production_supplemental_issue
    if not all([product_id, actual_quantity, source_log_id]) or theoretical_quantity <= 0 or actual_quantity <= 0:
        raise ValidationError("A valid product, theoretical quantity, actual quantity, and source log must be provided.")

    # 1. Validate stock for the new item.
    is_valid, error_msg = validate_stock_availability(
        product_ids=[product_id],
        actual_quantities=[actual_quantity],
        source_log_ids=[source_log_id],
        batch_creation_date=batch.creation_date.date(),
        batch_id_to_exclude=batch.pk
    )
    if not is_valid:
        raise ValidationError(error_msg)

    with transaction.atomic():
        # --- CRITICAL STEP 1: Snapshot the cost ---
        state = get_inventory_state_at_datetime(product_id, batch.creation_date)
        mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')

        new_item = BatchItem.objects.create(
            batch=batch,
            primitive_product_id=product_id,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=actual_quantity,
            source_log_id=source_log_id,
            cost_at_consumption=mac_at_consumption.quantize(Decimal('0.001'))
        )

        # --- CRITICAL STEP 2: Create a specific, auditable JE for this supplemental issue ---
        create_je_for_production_supplemental_issue(new_item)

        check_and_update_batch_customization(batch.id)

    # --- CRITICAL STEP 3: Update the final MAC on the product ---
    recalculate_cost_history_for_product(product_id, batch.creation_date)

    logger.info(f"Added supplemental item {new_item.id} to Batch {batch.id} and created a dedicated JE.")
    return new_item


def return_item_from_batch(*, item: BatchItem, quantity: float, return_date: datetime.date, notes: str) -> 'ProductionReturn':
    """
    Creates a ProductionReturn to move a specified quantity of a component
    from a batch back into inventory. This is the non-destructive way to 'remove' an item.
    """
    from ..models import ProductionReturn
    
    batch = item.batch
    if quantity <= 0:
        raise ValidationError(_("Return quantity must be positive."))

    # You might add more validation here, e.g., ensuring return quantity
    # doesn't exceed the original actual_quantity for the item.

    with transaction.atomic():
        # Create the compensating transaction
        prod_return = ProductionReturn.objects.create(
            product=item.primitive_product,
            source_log=item.source_log,
            batch=batch,
            quantity=quantity,
            return_date=timezone.make_aware(datetime.combine(return_date, time.min)),
            notes=notes
        )
        # The post_save signal on ProductionReturn will create the JE and trigger cost recalculation.
    
    logger.info(f"Created ProductionReturn {prod_return.id} to return {quantity} of {item.primitive_product.name} from Batch {batch.id}.")
    return prod_return





def cancel_batch(batch: Batch, user, justification: str) -> Batch:
    """
    Cancels a batch non-destructively, with strict safety checks.
    """
    from .accounting.correction_transactions import create_reversing_je_for_correction
    from .costing_service import recalculate_cost_history_for_product
    from django.contrib.contenttypes.models import ContentType
    from ..models import JournalEntry

    logger.info(f"--> User '{user.username}' attempting to cancel Batch ID {batch.id}.")

    # --- Strict Pre-checks ---
    if batch.status in [Batch.Status.CANCELLED, Batch.Status.COMPLETED]:
        raise ValidationError(_(f"Cannot cancel a batch with status '{batch.get_status_display()}'. Only In-Progress batches can be cancelled."))

    if batch.receipts.exists():
        raise ValidationError(_("Cannot cancel this batch as finished goods have already been received against it."))

    with transaction.atomic():
        # Reverse the original consumption JE, if it exists.
        content_type = ContentType.objects.get_for_model(Batch)
        original_je = JournalEntry.objects.filter(
            content_type=content_type, object_id=batch.pk
        ).first()

        if original_je:
            create_reversing_je_for_correction(
                original_object=batch,
                justification=justification,
                user=user,
                correction_date=timezone.now()
            )
            logger.info(f"    Created reversing JE for Batch ID {batch.id}.")
        else:
            logger.warning(f"    No original JE found for Batch ID {batch.id}. Skipping reversal as it may have been a zero-cost batch.")

        # Update the status to CANCELLED
        batch.status = Batch.Status.CANCELLED
        batch.save(update_fields=['status'])
        logger.info(f"    Set status to CANCELLED for Batch ID {batch.id}.")

    # Trigger cost recalculation for all components outside the main transaction
    products_to_recalc = {item.primitive_product_id for item in batch.items.all()}
    for product_id in products_to_recalc:
        recalculate_cost_history_for_product(product_id, batch.creation_date)
        logger.info(f"    Triggered cost recalculation for Product ID {product_id}.")

    logger.info(f"<-- Successfully cancelled Batch ID {batch.id}.")
    return batch