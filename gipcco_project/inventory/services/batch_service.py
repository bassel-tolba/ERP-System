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
        # Add a pessimistic lock to prevent race conditions from double-clicks.
        batch = Batch.objects.select_for_update().get(pk=batch.pk)

        # --- CRITICAL STEP 1: Snapshot costs and update items ---
        items_to_update = []
        product_ids_to_recalc = set()
        for item in batch.items.all():
            state = get_inventory_state_at_datetime(item.primitive_product_id, batch.creation_date)
            mac_at_consumption = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            item.cost_at_consumption = mac_at_consumption.quantize(Decimal('0.001'))
            items_to_update.append(item)
            product_ids_to_recalc.add(item.primitive_product_id)
            
            # --- NEW: Defensive logging to debug zero-cost issues ---
            logger.debug(
                f"    Item {item.id}: Product {item.primitive_product.name}, "
                f"State at {batch.creation_date}: qty={state['quantity']}, value={state['value']}, "
                f"Calculated MAC={mac_at_consumption}"
            )
        
        BatchItem.objects.bulk_update(items_to_update, ['cost_at_consumption'])
        logger.info(f"Snapshotted costs for {len(items_to_update)} items in Batch {batch.id}.")

        # --- CRITICAL STEP 2: Create the Journal Entry ---
        # Reload the batch with explicit prefetch to ensure fresh item data
        batch = Batch.objects.prefetch_related('items__primitive_product').get(pk=batch.pk)
        
        # --- NEW: Validate that costs were actually set ---
        fresh_items = list(batch.items.all())
        zero_cost_items = [item for item in fresh_items if not item.cost_at_consumption or item.cost_at_consumption == 0]
        if zero_cost_items:
            logger.warning(
                f"Batch {batch.id} has {len(zero_cost_items)} items with zero cost. "
                f"Products: {[item.primitive_product.name for item in zero_cost_items]}. "
                f"This may indicate missing inventory data at the batch creation date."
            )
        
        create_je_for_production_consumption(batch)

        # --- CRITICAL STEP 3: Update batch status ---
        batch.status = Batch.Status.IN_PROGRESS
        batch.save(update_fields=['status'])

    # --- CRITICAL STEP 4: Update the final moving average cost on the products ---
    for pid in product_ids_to_recalc:
        recalculate_cost_history_for_product(pid, batch.creation_date)

    logger.info(f"Successfully started production for Batch {batch.id}.")
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

    # --- NEW: Add circular dependency check within the service ---
    if parent_batch_id:
        if parent_batch_id == batch.pk:
            raise ValidationError(_("A batch cannot be its own parent."))
        
        # Traverse up the hierarchy to detect deeper circular references
        ancestor = Batch.objects.get(pk=parent_batch_id)
        while ancestor:
            if ancestor.pk == batch.pk:
                raise ValidationError(_("Circular dependency detected. A batch cannot be a continuation of one of its own descendants."))
            ancestor = ancestor.parent_batch

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
        item_ids_from_form = {int(item_data['item_id']) for item_data in items_data if 'item_id' in item_data and item_data['item_id']}

        # 1. Delete items that are no longer in the form
        ids_to_delete = set(items_in_db.keys()) - item_ids_from_form
        if ids_to_delete:
            BatchItem.objects.filter(id__in=ids_to_delete).delete()

        items_to_create = []
        items_to_update = []
        
        # 2. Update existing items and identify new items to create
        for item_data in items_data:
            item_id = item_data.get('item_id')
            if item_id:
                item = items_in_db.get(int(item_id))
                if item:
                    item.theoretical_quantity = item_data['theoretical_quantity']
                    item.actual_quantity = item_data['actual_quantity']
                    item.source_log_id = item_data['source_log_id'] or None
                    item.cost_at_consumption = None # Ensure cost is null as it's a draft
                    items_to_update.append(item)
            else:
                # This is a new item, not in the DB yet
                items_to_create.append(
                    BatchItem(
                        batch=batch_to_update,
                        primitive_product_id=item_data['product_id'],
                        theoretical_quantity=item_data['theoretical_quantity'],
                        actual_quantity=item_data['actual_quantity'],
                        source_log_id=item_data['source_log_id'],
                    )
                )
        
        # 3. Perform bulk operations for efficiency
        if items_to_update:
            BatchItem.objects.bulk_update(items_to_update, ['theoretical_quantity', 'actual_quantity', 'source_log_id', 'cost_at_consumption'])
        
        if items_to_create:
            BatchItem.objects.bulk_create(items_to_create)

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

    # MODIFICATION: Enforce stricter workflow. Items can ONLY be added to Draft batches.
    # For batches in progress, a Continuation Batch must be created.
    if batch.status != Batch.Status.DRAFT:
        raise ValidationError(_("Items can only be added to 'Draft' batches. For running batches, please create a Continuation Batch."))

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
        new_item = BatchItem.objects.create(
            batch=batch,
            primitive_product_id=product_id,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=actual_quantity,
            source_log_id=source_log_id,
            cost_at_consumption=None # Cost is always null for draft items.
        )

        logger.info(f"Added item {new_item.id} to Draft Batch {batch.id}.")
        check_and_update_batch_customization(batch.id)

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
    # MODIFIED: Import necessary models and helpers for consolidated reversal
    from django.db.models import Q
    from ..models import BatchItem, JournalEntry, JournalEntryLine, TransactionCorrection
    from .accounting._helpers import _check_period_is_open
    from .costing_service import recalculate_cost_history_for_product
    from django.contrib.contenttypes.models import ContentType

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
        # MODIFICATION START: Find and reverse ALL related journal entries, not just the one on the Batch.
        if original_status == Batch.Status.IN_PROGRESS:
            batch_content_type = ContentType.objects.get_for_model(Batch)
            batch_item_content_type = ContentType.objects.get_for_model(BatchItem)
            item_ids = batch.items.values_list('id', flat=True)

            journal_entries_to_reverse = JournalEntry.objects.filter(
                Q(content_type=batch_content_type, object_id=batch.pk) |
                Q(content_type=batch_item_content_type, object_id__in=list(item_ids))
            ).distinct().prefetch_related('lines')

            if journal_entries_to_reverse.exists():
                correction_date = timezone.now()
                _check_period_is_open(correction_date.date())

                # Aggregate all lines to create a single consolidated reversal
                total_debits_by_account = {}
                total_credits_by_account = {}

                for je in journal_entries_to_reverse:
                    for line in je.lines.all():
                        account_id = line.account_id
                        if line.entry_type == JournalEntryLine.EntryType.DEBIT:
                            total_debits_by_account[account_id] = total_debits_by_account.get(account_id, Decimal('0.0')) + line.amount
                        elif line.entry_type == JournalEntryLine.EntryType.CREDIT:
                            total_credits_by_account[account_id] = total_credits_by_account.get(account_id, Decimal('0.0')) + line.amount

                description = _(
                    "Reversal for cancelled Batch SO: %(so)s. Justification: %(justification)s"
                ) % {'so': batch.shop_order_number, 'justification': justification}

                reversing_je = JournalEntry.objects.create(
                    date=correction_date,
                    description=description,
                    source_object=batch,
                    status=JournalEntry.Status.POSTED
                )

                lines_to_create = []
                for account_id, amount in total_credits_by_account.items():
                    lines_to_create.append(JournalEntryLine(journal_entry=reversing_je, account_id=account_id, amount=amount, entry_type=JournalEntryLine.EntryType.DEBIT))
                for account_id, amount in total_debits_by_account.items():
                    lines_to_create.append(JournalEntryLine(journal_entry=reversing_je, account_id=account_id, amount=amount, entry_type=JournalEntryLine.EntryType.CREDIT))
                
                JournalEntryLine.objects.bulk_create(lines_to_create)
                reversing_je.validate_balance()

                # Link the reversal to all original JEs for audit trail
                corrections_to_create = [
                    TransactionCorrection(
                        original_journal_entry=original_je,
                        reversing_journal_entry=reversing_je,
                        justification=justification, corrected_by=user, correction_date=correction_date
                    ) for original_je in journal_entries_to_reverse
                ]
                TransactionCorrection.objects.bulk_create(corrections_to_create)
                logger.info(f"    Created consolidated reversing JE-{reversing_je.id} for Batch ID {batch.id}, reversing {journal_entries_to_reverse.count()} original JEs.")
            else:
                logger.warning(f"    No original JEs found for In-Progress Batch ID {batch.id}. Skipping reversal.")
        # MODIFICATION END

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