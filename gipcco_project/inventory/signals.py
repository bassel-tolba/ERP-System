# gipcco_project/inventory/signals.py

import logging

from django.db.models.signals import post_save, post_delete, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType

from .models import (
    FinishedProductDispatch, FinishedProductReceipt, InventoryLog, JournalEntry,
    Batch, InventoryConsumption, ProductionReturn, Payment, BankTransfer,
    DepreciationLog
)
from .services.accounting_service import (
    _check_period_is_open, # Import the gatekeeper function
    create_je_for_inventory_receipt, 
    create_je_for_production_consumption,
    create_je_for_internal_consumption,
    create_je_for_finished_goods_receipt,
    create_je_for_production_return,
    create_je_for_sales_dispatch,
    create_je_for_supplier_payment,
    create_je_for_customer_payment,
    create_je_for_bank_transfer
)

logger = logging.getLogger(__name__)

# ==============================================================================
# PRE-SAVE AND PRE-DELETE HOOKS FOR DATA INTEGRITY
# ==============================================================================

# A dictionary mapping transactional models to their date fields.
# This allows us to create generic signal handlers.
TRANSACTIONAL_MODELS = {
    InventoryLog: 'release_timestamp',
    Batch: 'creation_date',
    InventoryConsumption: 'consumption_date',
    FinishedProductReceipt: 'receipt_date',
    ProductionReturn: 'return_date',
    FinishedProductDispatch: 'dispatch_date',
    Payment: 'payment_date',
    BankTransfer: 'transfer_date',
    DepreciationLog: 'period_date',
}

def pre_save_period_check(sender, instance, **kwargs):
    """Generic pre-save signal to check the financial period status."""
    date_field_name = TRANSACTIONAL_MODELS.get(sender)
    if date_field_name:
        date_to_check = getattr(instance, date_field_name)
        if date_to_check:
            # For new records or if the date has changed.
            if instance.pk is None or getattr(sender.objects.get(pk=instance.pk), date_field_name) != date_to_check:
                 _check_period_is_open(date_to_check)

def pre_delete_period_check(sender, instance, **kwargs):
    """Generic pre-delete signal to check the financial period status."""
    date_field_name = TRANSACTIONAL_MODELS.get(sender)
    if date_field_name:
        date_to_check = getattr(instance, date_field_name)
        if date_to_check:
            _check_period_is_open(date_to_check)

# Connect the signals dynamically
for model, date_field in TRANSACTIONAL_MODELS.items():
    pre_save.connect(pre_save_period_check, sender=model, weak=False)
    pre_delete.connect(pre_delete_period_check, sender=model, weak=False)


# ==============================================================================
# POST-SAVE HOOKS FOR JOURNAL ENTRY CREATION
# ==============================================================================

@receiver(post_save, sender=InventoryLog)
def handle_inventory_log_release(sender, instance: InventoryLog, **kwargs):
    """
    Listens for an InventoryLog to be saved and triggers the creation of a 
    Journal Entry if its status is 'RELEASED'.
    """
    if instance.status == InventoryLog.Status.RELEASED:
        logger.debug(f"Signal triggered for released InventoryLog ID {instance.id}. Attempting to create JE.")
        try:
            create_je_for_inventory_receipt(inventory_log=instance)
        except Exception as e:
            logger.error(
                f"Error creating Journal Entry from signal for InventoryLog ID {instance.id}: {e}",
                exc_info=True
            )


@receiver(post_delete, sender=InventoryLog)
def handle_inventory_log_deletion(sender, instance: InventoryLog, **kwargs):
    """
    Listens for an InventoryLog to be deleted and cleans up its associated Journal Entry.
    """
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted InventoryLog ID {instance.id}.")
    except Exception as e:
        logger.error(
            f"Error cleaning up Journal Entry for deleted InventoryLog ID {instance.id}: {e}",
            exc_info=True
        )

# --- NEW SIGNAL HANDLERS FOR CONSUMPTION ---

@receiver(post_save, sender=Batch)
def handle_batch_creation_or_update(sender, instance: Batch, created, **kwargs):
    """
    Listens for a Batch to be saved. If it's updated, it deletes the old JE.
    Then, it creates a new JE for the production consumption.
    """
    # If the record was updated, not created, first delete the old JE to allow recreation.
    if not created:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
            logger.info(f"Deleted existing JE for updated Batch ID {instance.id} to allow regeneration.")
        except Exception as e:
            logger.error(f"Error deleting old JE for updated Batch ID {instance.id}: {e}", exc_info=True)

    # Now, attempt to create the JE. The service function has its own guards.
    try:
        create_je_for_production_consumption(batch=instance)
    except Exception as e:
        logger.error(f"Error creating JE for Batch ID {instance.id}: {e}", exc_info=True)


@receiver(post_delete, sender=Batch)
def handle_batch_deletion(sender, instance: Batch, **kwargs):
    """Deletes the associated Journal Entry when a Batch is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted Batch ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted Batch ID {instance.id}: {e}", exc_info=True)


@receiver(post_save, sender=InventoryConsumption)
def handle_internal_consumption_creation_or_update(sender, instance: InventoryConsumption, created, **kwargs):
    """
    Listens for an InventoryConsumption record to be saved. If updated, it deletes
    the old JE before creating a new one.
    """
    if not created:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
            logger.info(f"Deleted existing JE for updated InventoryConsumption ID {instance.id} to allow regeneration.")
        except Exception as e:
            logger.error(f"Error deleting old JE for updated InventoryConsumption ID {instance.id}: {e}", exc_info=True)
    
    try:
        create_je_for_internal_consumption(consumption=instance)
    except Exception as e:
        logger.error(f"Error creating JE for InventoryConsumption ID {instance.id}: {e}", exc_info=True)


@receiver(post_delete, sender=InventoryConsumption)
def handle_internal_consumption_deletion(sender, instance: InventoryConsumption, **kwargs):
    """Deletes the associated Journal Entry when an InventoryConsumption record is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted InventoryConsumption ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted InventoryConsumption ID {instance.id}: {e}", exc_info=True)
        
@receiver(post_save, sender=FinishedProductReceipt)        
def handle_fg_receipt_save(sender, instance: FinishedProductReceipt, created, **kwargs):
    """Creates/updates a JE when a FinishedProductReceipt is saved."""
    # If the record was updated, delete the old JE to allow regeneration.
    if not created:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
            logger.info(f"Deleted existing JE for updated FinishedProductReceipt ID {instance.id} to allow regeneration.")
        except Exception as e:
            logger.error(f"Error deleting old JE for updated FinishedProductReceipt ID {instance.id}: {e}", exc_info=True)

    # The service function will create the JE.
    try:
        create_je_for_finished_goods_receipt(receipt=instance)
    except Exception as e:
        logger.error(f"Error creating JE for FinishedProductReceipt ID {instance.id}: {e}", exc_info=True)

@receiver(post_delete, sender=FinishedProductReceipt)
def handle_fg_receipt_delete(sender, instance: FinishedProductReceipt, **kwargs):
    """Deletes the associated JE when a FinishedProductReceipt is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted FinishedProductReceipt ID {instance.id}: {e}", exc_info=True)

@receiver(post_save, sender=ProductionReturn)
def handle_production_return_save(sender, instance: ProductionReturn, created, **kwargs):
    """Creates/updates the JE for a ProductionReturn."""
    if not created: # Delete old JE on update
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        except Exception as e:
            logger.error(f"Error deleting old JE for updated ProductionReturn ID {instance.id}: {e}", exc_info=True)
    try:
        create_je_for_production_return(prod_return=instance)
    except Exception as e:
        logger.error(f"Error creating JE for ProductionReturn ID {instance.id}: {e}", exc_info=True)

@receiver(post_delete, sender=ProductionReturn)
def handle_production_return_delete(sender, instance: ProductionReturn, **kwargs):
    """Deletes the associated JE when a ProductionReturn is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted ProductionReturn ID {instance.id}: {e}", exc_info=True)

@receiver(post_save, sender=FinishedProductDispatch)
def handle_dispatch_save(sender, instance: FinishedProductDispatch, created, **kwargs):
    """Creates/updates the JE for a sales dispatch."""
    if not created: # Delete old JE on update
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        except Exception as e:
            logger.error(f"Error deleting old JE for updated FinishedProductDispatch ID {instance.id}: {e}", exc_info=True)
    try:
        create_je_for_sales_dispatch(dispatch=instance)
    except Exception as e:
        logger.error(f"Error creating JE for FinishedProductDispatch ID {instance.id}: {e}", exc_info=True)

@receiver(post_delete, sender=FinishedProductDispatch)
def handle_dispatch_delete(sender, instance: FinishedProductDispatch, **kwargs):
    """Deletes the associated JE when a sales dispatch is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted FinishedProductDispatch ID {instance.id}: {e}", exc_info=True)
        
        



@receiver(post_delete, sender=Payment)
def handle_payment_delete(sender, instance: Payment, **kwargs):
    """Deletes the associated JE when a Payment is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted JE for deleted Payment ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted Payment ID {instance.id}: {e}", exc_info=True)
        
        
        
        
        
@receiver(post_save, sender=Payment)
def handle_payment_save(sender, instance: Payment, created, **kwargs):
    """
    Creates/updates the JE for a payment, routing to the correct service
    based on the payment type (A/P or A/R).
    """
    if not created: # Delete old JE on update to allow regeneration
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
            logger.info(f"Deleted existing JE for updated Payment ID {instance.id}.")
        except Exception as e:
            logger.error(f"Error deleting old JE for updated Payment ID {instance.id}: {e}", exc_info=True)
    
    try:
        if instance.payment_type == Payment.PaymentType.PAYMENT_OUT:
            create_je_for_supplier_payment(payment=instance)
        elif instance.payment_type == Payment.PaymentType.PAYMENT_IN:
            create_je_for_customer_payment(payment=instance)
    except Exception as e:
        logger.error(f"Error creating JE for Payment ID {instance.id}: {e}", exc_info=True)
        
# --- NEW: BANK TRANSFER SIGNAL HANDLERS ---
@receiver(post_save, sender=BankTransfer)
def handle_bank_transfer_save(sender, instance: BankTransfer, created, **kwargs):
    """Creates/updates the JE for a bank transfer."""
    if not created:
        try:
            content_type = ContentType.objects.get_for_model(instance)
            JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        except Exception as e:
            logger.error(f"Error deleting old JE for updated BankTransfer ID {instance.id}: {e}", exc_info=True)
    try:
        create_je_for_bank_transfer(transfer=instance)
    except Exception as e:
        logger.error(f"Error creating JE for BankTransfer ID {instance.id}: {e}", exc_info=True)


@receiver(post_delete, sender=BankTransfer)
def handle_bank_transfer_delete(sender, instance: BankTransfer, **kwargs):
    """Deletes the associated JE when a BankTransfer is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error cleaning up JE for deleted BankTransfer ID {instance.id}: {e}", exc_info=True)