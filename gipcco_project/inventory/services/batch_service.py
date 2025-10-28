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
    Creates a new Batch in DRAFT status, along with its items.
    No journal entries are created or costs calculated at this stage.
    """
    if not all([template_id, shop_order_number, batch_number_from, creation_date, items_data]):
        raise ValidationError("Missing required data for batch creation.")

    # Stock validation is still important at creation time to ensure feasibility
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
            # Status defaults to DRAFT
        )

        items_to_create = [
            BatchItem(
                batch=batch,
                primitive_product_id=item_data['product_id'],
                theoretical_quantity=item_data['theoretical_quantity'],
                actual_quantity=item_data['actual_quantity'],
                source_log_id=item_data['source_log_id'],
                cost_at_consumption=None # Cost will be snapshotted upon starting production
            ) for item_data in items_data
        ]
        BatchItem.objects.bulk_create(items_to_create)

    check_and_update_batch_customization(batch.id)
    logger.info(f"Successfully created Batch {batch.id} in Draft status with {len(items_to_create)} items.")
    return batch


def submit_batch_for_approval(batch: Batch, user) -> Batch:
    """
    Submits a batch for approval, changing its status from Draft to Pending Approval.
    """
    if batch.status != Batch.Status.DRAFT:
        raise ValidationError(_("Only batches in 'Draft' status can be submitted for approval."))
    
    batch.status = Batch.Status.PENDING_APPROVAL
    batch.submitted_by = user
    batch.submitted_at = timezone.now()
    batch.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    logger.info(f"Batch {batch.id} submitted for approval by {user.username}.")
    return batch


def approve_batch(batch: Batch, user) -> Batch:
    """
    Approves a batch, changing its status from Pending Approval to Approved.
    """
    if batch.status != Batch.Status.PENDING_APPROVAL:
        raise ValidationError(_("Only batches 'Pending Approval' can be approved."))
    
    batch.status = Batch.Status.APPROVED
    batch.approved_by = user
    batch.approved_at = timezone.now()
    batch.save(update_fields=['status', 'approved_by', 'approved_at'])
    logger.info(f"Batch {batch.id} approved by {user.username}.")
    return batch


def reject_batch(batch: Batch, user, justification: str) -> Batch:
    """
    Rejects a batch that is pending approval, returning it to Draft status.
    """
    if batch.status != Batch.Status.PENDING_APPROVAL:
        raise ValidationError(_("Only batches 'Pending Approval' can be rejected."))
    
    batch.status = Batch.Status.DRAFT
    # Clearing approval fields to allow for resubmission.
    batch.submitted_by = None
    batch.submitted_at = None
    batch.save(update_fields=['status', 'submitted_by', 'submitted_at'])
    logger.info(f"Batch {batch.id} rejected by {user.username} with justification: {justification}. Status returned to Draft.")
    return batch


def start_batch_production(batch: Batch) -> Batch:
    """
    Starts production for an approved batch. This is the point where:
    1. Costs are snapshotted for all items.
    2. The production consumption Journal Entry is created.
    3. The final Moving Average Cost is recalculated for consumed products.
    4. The batch status is moved to 'In Progress'.
    """
    if batch.status != Batch.Status.APPROVED:
        raise ValidationError(_("Only 'Approved' batches can be started."))

    with transaction.atomic():
        # --- CRITICAL STEP 1: Snapshot costs and update items ---
        items_to_update = []
        product_ids_to_recalc = set()
        for item in batch.items.all():
            state = get_inventory_state_at_datetime(item.primitive_product_id, batch.creation_date)
            mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            item.cost_at_consumption = mac_at_consumption.quantize(Decimal('0.001'))
            items_to_update.append(item)
            product_ids_to_recalc.add(item.primitive_product_id)
        
        BatchItem.objects.bulk_update(items_to_update, ['cost_at_consumption'])
        logger.info(f"Snapshotted costs for {len(items_to_update)} items in Batch {batch.id}.")

        # --- CRITICAL STEP 2: Create the Journal Entry ---
        create_je_for_production_consumption(batch)

        # --- CRITICAL STEP 3: Update batch status ---
        batch.status = Batch.Status.IN_PROGRESS
        batch.save(update_fields=['status'])

    # --- CRITICAL STEP 4: Update the final moving average cost on the products ---
    for pid in product_ids_to_recalc:
        recalculate_cost_history_for_product(pid, batch.creation_date)

    logger.info(f"Successfully started production for Batch {batch.id} and created its Journal Entry.")
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
    Updates a Batch in 'Draft' status.
    Since no financial transactions have occurred, this is a direct update.
    """
    original_creation_date = batch.creation_date

    if batch.status != Batch.Status.DRAFT:
        raise ValidationError(_("Only 'Draft' batches can be edited."))

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
        
        for item_data in items_data:
            item = items_in_db.get(item_data['item_id'])
            if item:
                item.theoretical_quantity = item_data['theoretical_quantity']
                item.actual_quantity = item_data['actual_quantity']
                item.source_log_id = item_data['source_log_id'] or None
                item.cost_at_consumption = None # Ensure cost is null as it's a draft
                item.save()

    check_and_update_batch_customization(batch.pk)
    logger.info(f"Successfully updated Draft Batch {batch.id}.")
    
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
    Adds an item to a batch.
    - If the batch is a DRAFT, it simply adds the item.
    - If the batch is IN_PROGRESS, it adds the item and creates a
      separate, auditable journal entry for that supplemental addition.
    """
    from .accounting_service import create_je_for_production_supplemental_issue
    if not all([product_id, actual_quantity, source_log_id]) or theoretical_quantity <= 0 or actual_quantity <= 0:
        raise ValidationError("A valid product, theoretical quantity, actual quantity, and source log must be provided.")

    if batch.status not in [Batch.Status.DRAFT, Batch.Status.IN_PROGRESS]:
        raise ValidationError(_("Items can only be added to 'Draft' or 'In Progress' batches."))

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
        mac_at_consumption = None
        # If batch is in progress, we need to snapshot cost and create a JE.
        if batch.status == Batch.Status.IN_PROGRESS:
            state = get_inventory_state_at_datetime(product_id, batch.creation_date)
            mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')

        new_item = BatchItem.objects.create(
            batch=batch,
            primitive_product_id=product_id,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=actual_quantity,
            source_log_id=source_log_id,
            cost_at_consumption=mac_at_consumption.quantize(Decimal('0.001')) if mac_at_consumption else None
        )

        # If in progress, create the specific JE for this supplemental issue.
        if batch.status == Batch.Status.IN_PROGRESS:
            create_je_for_production_supplemental_issue(new_item)
            logger.info(f"Added supplemental item {new_item.id} to Batch {batch.id} and created a dedicated JE.")
        else:
            logger.info(f"Added item {new_item.id} to Draft Batch {batch.id}.")

        check_and_update_batch_customization(batch.id)

    # If in progress, update the final MAC on the product.
    if batch.status == Batch.Status.IN_PROGRESS:
        recalculate_cost_history_for_product(product_id, batch.creation_date)

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
    Cancels a batch non-destructively.
    - If batch was 'In Progress', it creates a reversing journal entry and recalculates costs.
    - If batch was in a pre-production state, it simply marks it as cancelled.
    """
    from .accounting.correction_transactions import create_reversing_je_for_correction
    from .costing_service import recalculate_cost_history_for_product
    from django.contrib.contenttypes.models import ContentType
    from ..models import JournalEntry

    logger.info(f"--> User '{user.username}' attempting to cancel Batch ID {batch.id}.")

    original_status = batch.status

    # --- Strict Pre-checks ---
    if original_status in [Batch.Status.CANCELLED, Batch.Status.COMPLETED]:
        raise ValidationError(_(f"Cannot cancel a batch that is already '{batch.get_status_display()}'."))

    if batch.receipts.exists():
        raise ValidationError(_("Cannot cancel this batch as finished goods have already been received against it."))

    products_to_recalc = {item.primitive_product_id for item in batch.items.all()}
    
    with transaction.atomic():
        # Only reverse financial transactions if the batch was actually in production
        if original_status == Batch.Status.IN_PROGRESS:
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
                logger.warning(f"    No original JE found for In-Progress Batch ID {batch.id}. Skipping reversal.")

        # Update the status to CANCELLED
        batch.status = Batch.Status.CANCELLED
        batch.save(update_fields=['status'])
        logger.info(f"    Set status to CANCELLED for Batch ID {batch.id}.")

    # If the batch was in progress, its cancellation affects inventory costs.
    if original_status == Batch.Status.IN_PROGRESS:
        for product_id in products_to_recalc:
            recalculate_cost_history_for_product(product_id, batch.creation_date)
            logger.info(f"    Triggered cost recalculation for Product ID {product_id}.")

    logger.info(f"<-- Successfully cancelled Batch ID {batch.id}.")
    return batch