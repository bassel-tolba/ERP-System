# gipcco_project/inventory/services/production_service.py

import logging
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from ..models import ProductionReturn
from .accounting.correction_transactions import create_reversing_je_for_correction
from .costing_service import recalculate_cost_history_for_product

logger = logging.getLogger(__name__)


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
