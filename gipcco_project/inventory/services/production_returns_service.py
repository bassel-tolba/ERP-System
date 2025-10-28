# gipcco_project/inventory/services/production_returns_service.py

import logging
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.db.models.functions import Coalesce

from ..models import ProductionReturn, BatchItem, InventoryConsumption, InventoryAdjustment
from .accounting.correction_transactions import create_reversing_je_for_correction
from .costing_service import recalculate_cost_history_for_product

logger = logging.getLogger(__name__)


def create_production_return(
    *,
    product_id: int,
    source_log_id: int,
    quantity: float,
    return_date: datetime,
    notes: str = '',
    batch_id: int = None
) -> ProductionReturn:
    """
    Creates a new Production Return record after validating the returnable quantity.
    """
    if not all([product_id, source_log_id, quantity, return_date]):
        raise ValidationError(_("Product, source log, quantity, and return date are required."))

    with transaction.atomic():
        # Validation
        total_consumed = BatchItem.objects.filter(source_log_id=source_log_id).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
        total_returned = ProductionReturn.objects.filter(source_log_id=source_log_id).exclude(status=ProductionReturn.Status.CANCELLED).aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
        max_returnable = total_consumed - total_returned

        if quantity > max_returnable + 0.001:
            raise ValidationError(_(f"Return quantity ({quantity}) exceeds the maximum returnable quantity ({max_returnable:.3f}) from this source."))

        pr_return = ProductionReturn.objects.create(
            product_id=product_id,
            source_log_id=source_log_id,
            quantity=quantity,
            return_date=return_date,
            notes=notes,
            batch_id=batch_id
        )
        # The post_save signal on ProductionReturn will create the JE and trigger cost recalculation.
    
    logger.info(f"Successfully created ProductionReturn {pr_return.id}.")
    return pr_return


def cancel_production_return(
    prod_return: ProductionReturn, 
    user, 
    justification: str
) -> ProductionReturn:
    """
    Cancels a production return non-destructively.

    - Creates a reversing journal entry for the original transaction.
    - Sets the production return's status to CANCELLED.
    - Triggers a cost recalculation for the affected product.
    """
    logger.info(f"User '{user.username}' attempting to cancel ProductionReturn ID {prod_return.id}.")
    
    if prod_return.status == ProductionReturn.Status.CANCELLED:
        logger.warning(f"Attempted to cancel already-cancelled ProductionReturn ID {prod_return.id}.")
        raise ValidationError(_("This production return has already been cancelled."))

    # --- SAFETY CHECK: Ensure the returned stock has not been subsequently used ---
    source_log = prod_return.source_log
    
    # Calculate total consumption from this specific log that happened *after* the return
    subsequent_consumption = BatchItem.objects.filter(
        source_log=source_log,
        batch__creation_date__gt=prod_return.return_date
    ).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']

    if subsequent_consumption > 0:
        raise ValidationError(
            _("Cannot cancel this return. The returned stock (or a portion of it) has already been consumed in a subsequent production batch.")
        )

    with transaction.atomic():
        # 1. Create the reversing journal entry
        create_reversing_je_for_correction(
            original_object=prod_return,
            justification=justification,
            user=user,
            correction_date=timezone.now()
        )
        logger.info(f"Successfully created reversing JE for ProductionReturn ID {prod_return.id}.")

        # 2. Mark the production return as cancelled
        prod_return.status = ProductionReturn.Status.CANCELLED
        prod_return.save(update_fields=['status'])
        logger.info(f"Set status to CANCELLED for ProductionReturn ID {prod_return.id}.")

    # 3. Trigger cost recalculation (outside the transaction)
    # This is crucial to reflect the inventory change in the moving average cost.
    recalculate_cost_history_for_product(prod_return.product_id, prod_return.return_date)
    logger.info(f"Triggered cost recalculation for product ID {prod_return.product_id} following cancellation.")

    logger.info(f"<-- Successfully cancelled ProductionReturn ID {prod_return.id}.")
    return prod_return
