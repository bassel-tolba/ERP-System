import logging
from datetime import datetime, time
from typing import List, Dict, Any, Tuple

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from ..models import Batch, BatchItem, Product, JournalEntry, InventoryLog
from .accounting_service import create_je_for_production_consumption
from .costing_service import recalculate_cost_history_for_product
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
            is_customized=True,
            is_continuation=is_continuation,
            parent_batch_id=parent_batch_id if is_continuation and parent_batch_id else None,
            notes=notes,
            machine_hours_consumed=machine_hours_consumed,
            labor_hours_consumed=labor_hours_consumed
        )

        items_to_create = [
            BatchItem(
                batch=batch,
                primitive_product_id=item['product_id'],
                theoretical_quantity=item['theoretical_quantity'],
                actual_quantity=item['actual_quantity'],
                source_log_id=item['source_log_id']
            ) for item in items_data
        ]
        BatchItem.objects.bulk_create(items_to_create)

        # --- CRITICAL STEP 1: CALCULATE & SET COST SNAPSHOT ---
        # This ensures BatchItem.cost_at_consumption is set before the JE reads it.
        product_ids_to_recalc = {item['product_id'] for item in items_data}
        for pid in product_ids_to_recalc:
            recalculate_cost_history_for_product(pid, batch.creation_date)

        # --- CRITICAL STEP 2: Explicitly call the accounting service ---
        create_je_for_production_consumption(batch)

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
                item.save()

        # --- CRITICAL STEP 1: CALCULATE & SET COST SNAPSHOT ---
        for pid in product_ids_to_recalc:
            recalculate_cost_history_for_product(pid, batch_to_update.creation_date)

        # --- CRITICAL STEP 2: Recreate the Journal Entry with the updated data ---
        create_je_for_production_consumption(batch_to_update)

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
    Adds a new item to an existing batch, validates stock, updates item cost, and recreates the JE.
    """
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
        # Step 1: Delete the old Journal Entry first (to be replaced by the new one)
        content_type = ContentType.objects.get_for_model(Batch)
        JournalEntry.objects.filter(content_type=content_type, object_id=batch.id).delete()

        # Step 2: Create the new BatchItem with full data
        product = Product.objects.get(pk=product_id)
        source_log = InventoryLog.objects.get(pk=source_log_id)
        
        new_item = BatchItem.objects.create(
            batch=batch,
            primitive_product=product,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=actual_quantity,
            source_log=source_log
        )
        
        # --- CRITICAL STEP 3: CALCULATE & SET COST SNAPSHOT ---
        # Recalculate cost history for the affected product starting from the batch date.
        recalculate_cost_history_for_product(product_id, batch.creation_date)

        # Step 4: Check and update customization flag
        check_and_update_batch_customization(batch.id)
        
        # Step 5: Recreate JE after item is added (now with correct cost)
        create_je_for_production_consumption(batch)

    logger.info(f"Added item {new_item.id} to Batch {batch.id} and recreated JE.")
    return new_item


def delete_item_from_batch(*, item: BatchItem) -> Dict[str, Any]:
    """Deletes an item from a batch, recreates the JE, and returns info for side effects."""
    batch = item.batch
    info = {
        'batch_id': batch.id,
        'product_id': item.primitive_product_id,
        'recalc_start_date': batch.creation_date
    }
    
    with transaction.atomic():
        # Recreate JE logic
        content_type = ContentType.objects.get_for_model(Batch)
        JournalEntry.objects.filter(content_type=content_type, object_id=batch.id).delete()

        item.delete()
        
        # --- CRITICAL STEP 1: CALCULATE & SET COST SNAPSHOT ---
        # Recalculate cost history to ensure the remaining inventory state is correct
        recalculate_cost_history_for_product(info['product_id'], info['recalc_start_date'])

        check_and_update_batch_customization(info['batch_id'])

        # Recreate JE after item is deleted (reflecting the lower total cost)
        create_je_for_production_consumption(batch)

    logger.info(f"Deleted item {item.id} from Batch {info['batch_id']} and recreated JE.")
    return info


def delete_batch(*, batch: Batch) -> Dict[str, Any]:
    """Deletes a batch and returns info needed for side effects."""
    
    # We must collect the products and date *before* deletion
    product_ids_to_recalc = {item.primitive_product_id for item in batch.items.all()}
    recalc_start_date = batch.creation_date
    batch_id = batch.id

    with transaction.atomic():
        # The JE will be cascade deleted with the batch, but we must update the MAC ledger.
        batch.delete()
        
        # Trigger MAC recalculation to reverse the consumption effect
        for pid in product_ids_to_recalc:
            recalculate_cost_history_for_product(pid, recalc_start_date)

    info = {
        'product_ids_to_recalc': product_ids_to_recalc,
        'recalc_start_date': recalc_start_date
    }
    logger.info(f"Deleted Batch {batch_id}.")
    return info