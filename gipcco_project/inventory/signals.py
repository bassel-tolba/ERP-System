# gipcco_project/inventory/signals.py

import logging

from django.db.models.signals import post_save, post_delete, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType

from .models import (
    FinishedProductDispatch, FinishedProductReceipt, InventoryLog, JournalEntry,
    Batch, InventoryConsumption, ProductionReturn, Payment, BankTransfer,
    DepreciationLog, InventoryAdjustment, EmployeeAdvance, EmployeeAdvanceSettlement,
    FinancialPeriod, PeriodCloseChecklist
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
    create_je_for_bank_transfer,
    create_je_for_depreciation, # <-- IMPORT NEW SERVICE
    create_je_for_inventory_adjustment,
    create_je_for_employee_advance
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
    InventoryAdjustment: 'adjustment_date',
    EmployeeAdvance: 'advance_date',
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
        # REMOVED try...except block to allow errors to propagate
        create_je_for_inventory_receipt(inventory_log=instance)


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
        logger.error(f"Error deleting Journal Entry for InventoryLog ID {instance.id}: {e}")


@receiver(post_save, sender=Batch)
def handle_batch_save(sender, instance: Batch, created, **kwargs):
    """
    Listens for a Batch to be saved. If it's updated, it deletes the old JE.
    Then, it creates a new JE for the production consumption.
    """
    # If the record was updated, not created, first delete the old JE to allow recreation.
    # The try/except block is removed to ensure that if deleting the old JE fails,
    # the entire transaction is rolled back, preventing duplicate JEs.
    if not created:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted existing JE for updated Batch ID {instance.id} to allow regeneration.")

    # Now, attempt to create the JE. The service function has its own guards.
    create_je_for_production_consumption(batch=instance)


@receiver(post_delete, sender=Batch)
def handle_batch_deletion(sender, instance: Batch, **kwargs):
    """Deletes the associated Journal Entry when a Batch is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted Batch ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for Batch ID {instance.id}: {e}")


@receiver(post_save, sender=InventoryConsumption)
def handle_internal_consumption_save(sender, instance: InventoryConsumption, created, **kwargs):
    """
    Listens for an InventoryConsumption to be saved and triggers the creation of a 
    Journal Entry. Also handles capitalization logic.
    """
    if created:
        create_je_for_internal_consumption(consumption=instance)
        
        # --- NEW: Handle capitalization ---
        if instance.consumption_type == InventoryConsumption.ConsumptionType.CAPITALIZE and instance.fixed_asset:
            asset = instance.fixed_asset
            cost_to_capitalize = instance.cost_at_consumption
            asset.purchase_cost += cost_to_capitalize
            asset.save(update_fields=['purchase_cost'])
            logger.info(f"Capitalized {cost_to_capitalize} to Fixed Asset {asset.asset_tag}. New cost: {asset.purchase_cost}")


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
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted existing JE for updated FinishedProductReceipt ID {instance.id} to allow regeneration.")

    # The service function will create the JE.
    create_je_for_finished_goods_receipt(receipt=instance)

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
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    create_je_for_production_return(prod_return=instance)

@receiver(post_delete, sender=ProductionReturn)
def handle_production_return_delete(sender, instance: ProductionReturn, **kwargs):
    """Deletes the associated JE when a ProductionReturn is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for ProductionReturn ID {instance.id}: {e}")


@receiver(post_save, sender=FinishedProductDispatch)
def handle_dispatch_save(sender, instance: FinishedProductDispatch, created, **kwargs):
    """Creates/updates the JE for a sales dispatch."""
    if not created: # Delete old JE on update
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    create_je_for_sales_dispatch(dispatch=instance)

@receiver(post_delete, sender=FinishedProductDispatch)
def handle_dispatch_delete(sender, instance: FinishedProductDispatch, **kwargs):
    """Deletes the associated JE when a sales dispatch is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for FinishedProductDispatch ID {instance.id}: {e}", exc_info=True)
        
        



@receiver(post_delete, sender=Payment)
def handle_payment_delete(sender, instance: Payment, **kwargs):
    """Deletes the associated JE when a Payment is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted JE for deleted Payment ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for Payment ID {instance.id}: {e}")


@receiver(post_save, sender=Payment)
def handle_payment_save(sender, instance: Payment, created, **kwargs):
    """
    Creates/updates the JE for a payment, routing to the correct service
    based on the payment type (A/P or A/R).
    """
    if not created: # Delete old JE on update to allow regeneration
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted existing JE for updated Payment ID {instance.id}.")
    
    if instance.payment_type == Payment.PaymentType.PAYMENT_OUT:
        create_je_for_supplier_payment(payment=instance)
    elif instance.payment_type == Payment.PaymentType.PAYMENT_IN:
        create_je_for_customer_payment(payment=instance)
        
# --- NEW: BANK TRANSFER SIGNAL HANDLERS ---
@receiver(post_save, sender=BankTransfer)
def handle_bank_transfer_save(sender, instance: BankTransfer, created, **kwargs):
    """Creates/updates the JE for a bank transfer."""
    if not created:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    create_je_for_bank_transfer(transfer=instance)


@receiver(post_delete, sender=BankTransfer)
def handle_bank_transfer_delete(sender, instance: BankTransfer, **kwargs):
    """Deletes the associated JE when a BankTransfer is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for BankTransfer ID {instance.id}: {e}")


# --- NEW SIGNAL FOR DEPRECIATION ---
@receiver(post_save, sender=DepreciationLog)
def handle_depreciation_log_save(sender, instance: DepreciationLog, created, **kwargs):
    """
    Listens for a DepreciationLog to be saved and triggers the creation of a 
    Journal Entry.
    """
    if created:
        create_je_for_depreciation(depreciation_log=instance)

@receiver(post_delete, sender=DepreciationLog)
def handle_depreciation_log_deletion(sender, instance: DepreciationLog, **kwargs):
    """
    Listens for a DepreciationLog to be deleted and cleans up its associated Journal Entry.
    """
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted DepreciationLog ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for DepreciationLog ID {instance.id}: {e}")


@receiver(post_save, sender=InventoryAdjustment)
def handle_inventory_adjustment_save(sender, instance: InventoryAdjustment, created, **kwargs):
    """Creates/updates the JE for an inventory adjustment."""
    logger.info(f"-> Signal 'handle_inventory_adjustment_save' triggered for InventoryAdjustment ID {instance.id}. Created: {created}.")
    if not created:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"   Deleted existing JE for updated InventoryAdjustment ID {instance.id} to allow regeneration.")
    
    logger.info(f"   Calling 'create_je_for_inventory_adjustment' for adjustment ID {instance.id}...")
    create_je_for_inventory_adjustment(adjustment=instance)
    logger.info(f"<- Finished 'handle_inventory_adjustment_save' for adjustment ID {instance.id}.")


@receiver(post_delete, sender=InventoryAdjustment)
def handle_inventory_adjustment_delete(sender, instance: InventoryAdjustment, **kwargs):
    """Deletes the associated JE when an InventoryAdjustment is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for InventoryAdjustment ID {instance.id}: {e}")


@receiver(post_save, sender=EmployeeAdvance)
def handle_employee_advance_save(sender, instance: EmployeeAdvance, created, **kwargs):
    """
    Listens for an EmployeeAdvance to be saved and triggers the creation of a
    Journal Entry.
    """
    if created:
        create_je_for_employee_advance(advance=instance)

@receiver(post_delete, sender=EmployeeAdvance)
def handle_employee_advance_deletion(sender, instance: EmployeeAdvance, **kwargs):
    """
    Listens for an EmployeeAdvance to be deleted and cleans up its associated Journal Entry.
    """
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"Deleted Journal Entry/Entries associated with deleted EmployeeAdvance ID {instance.id}.")
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for EmployeeAdvance ID {instance.id}: {e}")


# --- NEW SIGNAL FOR EMPLOYEE ADVANCE SETTLEMENT ---
@receiver(post_save, sender=EmployeeAdvanceSettlement)
def handle_advance_settlement_save(sender, instance: EmployeeAdvanceSettlement, created, **kwargs):
    """
    Listens for a settlement to be saved and triggers an update on the parent
    EmployeeAdvance's status.
    """
    if created:
        advance = instance.advance
        advance.update_status(save=True)
        logger.info(f"Updated status for EmployeeAdvance ID {advance.id} due to new settlement.")


@receiver(post_save, sender=FinancialPeriod)
def create_period_close_checklist(sender, instance, created, **kwargs):
    """
    Automatically create a PeriodCloseChecklist when a new FinancialPeriod is created.
    """
    if created:
        PeriodCloseChecklist.objects.create(financial_period=instance)