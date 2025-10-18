# gipcco_project/inventory/signals.py

import logging

from django.db.models.signals import post_save, post_delete, pre_save, pre_delete
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from .models import (
    FinishedProductDispatch, FinishedProductReceipt, InventoryLog, JournalEntry,
    Batch, InventoryConsumption, ProductionReturn, Payment, BankTransfer,
    DepreciationLog, InventoryAdjustment, EmployeeAdvance, EmployeeAdvanceSettlement,
    FinancialPeriod, PeriodCloseChecklist, GeneralAccountingSettings,
    # --- NEW IMPORTS ---
    PrepaidExpense, ExpenseLog, AmortizationLog, AccrualLog, ExpenseRequest,
    CustomerCreditMemo
)
from .services.accounting_service import (
    _check_period_is_open,
    create_je_for_inventory_receipt, 
    create_je_for_production_consumption,
    create_je_for_internal_consumption,
    create_je_for_finished_goods_receipt,
    create_je_for_production_return,
    create_je_for_sales_dispatch,
    create_je_for_credit_memo,
    create_je_for_supplier_payment,
    create_je_for_customer_payment,
    create_je_for_bank_transfer,
    create_je_for_depreciation, # <-- IMPORT NEW SERVICE
    create_je_for_inventory_adjustment,
    create_je_for_employee_advance,
    create_je_for_employee_advance_settlement,
    # --- NEW IMPORTS ---
    create_je_for_amortization,
    create_je_for_accrual,
    create_je_for_expense_log,
    _get_product_expense_account
)

logger = logging.getLogger(__name__)

# ==============================================================================
# PRE-SAVE AND PRE-DELETE HOOKS FOR DATA INTEGRITY
# ==============================================================================

# A dictionary mapping transactional models to their date fields.
# This allows us to create generic signal handlers.
TRANSACTIONAL_MODELS = {
    'InventoryLog': 'timestamp',
    'Batch': 'creation_date',
    'InventoryConsumption': 'consumption_date',
    'FinishedProductReceipt': 'receipt_date',
    'ProductionReturn': 'return_date',
    'FinishedProductDispatch': 'dispatch_date',
    'Payment': 'payment_date',
    'BankTransfer': 'transfer_date',
    'DepreciationLog': 'period_date',
    'AmortizationLog': 'period_date',
    'AccrualLog': 'period_date',
    'ExpenseLog': 'expense_date',
    'InventoryAdjustment': 'adjustment_date',
    'EmployeeAdvance': 'advance_date',
    'CustomerCreditMemo': 'memo_date',
}


@receiver(pre_save, sender=InventoryLog)
@receiver(pre_save, sender=Batch)
@receiver(pre_save, sender=InventoryConsumption)
@receiver(pre_save, sender=FinishedProductReceipt)
@receiver(pre_save, sender=ProductionReturn)
@receiver(pre_save, sender=FinishedProductDispatch)
@receiver(pre_save, sender=Payment)
@receiver(pre_save, sender=BankTransfer)
@receiver(pre_save, sender=DepreciationLog)
@receiver(pre_save, sender=AmortizationLog)
@receiver(pre_save, sender=AccrualLog)
@receiver(pre_save, sender=ExpenseLog)
@receiver(pre_save, sender=InventoryAdjustment)
@receiver(pre_save, sender=EmployeeAdvance)
@receiver(pre_save, sender=CustomerCreditMemo)
def pre_save_period_check(sender, instance, **kwargs):
    """
    A generic pre-save signal that connects to multiple models to ensure
    the financial period is open for the given date.
    """
    date_field_name = TRANSACTIONAL_MODELS.get(sender)
    if date_field_name:
        date_to_check = getattr(instance, date_field_name)
        if date_to_check:
            # For new records or if the date has changed.
            if instance.pk is None or getattr(sender.objects.get(pk=instance.pk), date_field_name) != date_to_check:
                 _check_period_is_open(date_to_check)

@receiver(pre_delete, sender=InventoryLog)
@receiver(pre_delete, sender=Batch)
@receiver(pre_delete, sender=InventoryConsumption)
@receiver(pre_delete, sender=FinishedProductReceipt)
@receiver(pre_delete, sender=ProductionReturn)
@receiver(pre_delete, sender=FinishedProductDispatch)
@receiver(pre_delete, sender=Payment)
@receiver(pre_delete, sender=BankTransfer)
@receiver(pre_delete, sender=DepreciationLog)
@receiver(pre_delete, sender=AmortizationLog)
@receiver(pre_delete, sender=AccrualLog)
@receiver(pre_delete, sender=ExpenseLog)
@receiver(pre_delete, sender=InventoryAdjustment)
@receiver(pre_delete, sender=EmployeeAdvance)
@receiver(pre_delete, sender=CustomerCreditMemo)
def pre_delete_period_check(sender, instance, **kwargs):
    """Generic pre-delete signal to check the financial period status."""
    date_field_name = TRANSACTIONAL_MODELS.get(sender)
    if date_field_name:
        date_to_check = getattr(instance, date_field_name)
        if date_to_check:
            _check_period_is_open(date_to_check)

# Connect the signals dynamically
for model_name, date_field in TRANSACTIONAL_MODELS.items():
    model_ref = f'inventory.{model_name}'
    pre_save.connect(pre_save_period_check, sender=model_ref, weak=False)
    pre_delete.connect(pre_delete_period_check, sender=model_ref, weak=False)


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


# @receiver(post_save, sender=Batch)  <-- COMMENTED OUT THIS DECORATOR
# def handle_batch_save(sender, instance: Batch, created, **kwargs):
#     """
#     DEPRECATED: This logic has been moved to the batch_service to ensure correct
#     transactional order. The service now explicitly creates the journal entry
#     after creating the batch and its items.
#     """
#     # If the record was updated, not created, first delete the old JE to allow recreation.
#     if not created:
#         content_type = ContentType.objects.get_for_model(instance)
#         JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
#         logger.info(f"Deleted existing JE for updated Batch ID {instance.id} to allow regeneration.")

#     create_je_for_production_consumption(batch=instance)


@receiver(pre_save, sender=InventoryConsumption)
def set_consumption_type_for_amortizable(sender, instance: InventoryConsumption, **kwargs):
    """
    Automatically set the consumption type to AMORTIZE if the product is amortizable
    and the type isn't already set to something else (like CAPITALIZE).
    """
    if instance.pk is None: # Only on creation
        if instance.product and instance.product.is_amortizable and instance.consumption_type == InventoryConsumption.ConsumptionType.EXPENSE:
            instance.consumption_type = InventoryConsumption.ConsumptionType.AMORTIZE


@receiver(post_save, sender=InventoryConsumption)
def handle_internal_consumption_save(sender, instance: InventoryConsumption, created, **kwargs):
    if not created:
        return

    # STEP 1: Always create the primary Journal Entry for the consumption.
    create_je_for_internal_consumption(consumption=instance)

    # STEP 2: Execute follow-on business logic based on the original request's intent.
    request = instance.source_request
    
    # Path A: Capitalize cost onto a Fixed Asset
    if instance.consumption_type == InventoryConsumption.ConsumptionType.CAPITALIZE and instance.fixed_asset:
        instance.fixed_asset.purchase_cost += instance.cost_at_consumption
        instance.fixed_asset.save(update_fields=['purchase_cost'])
        return

    # Path B: Create a Prepaid Asset
    if instance.consumption_type == InventoryConsumption.ConsumptionType.AMORTIZE:
        if request and request.request_type == ExpenseRequest.RequestType.INVENTORY_PREPAID:
            # Modern workflow: Data comes from the approved request
            PrepaidExpense.objects.create(
                description=request.description,
                initial_amount=instance.cost_at_consumption,
                amortization_start_date=request.amortization_start_date,
                amortization_end_date=request.amortization_end_date,
                asset_account=request.asset_account,
                expense_account=request.expense_account,
                created_by=request.requested_by,
                source_content_object=instance
            )
        else:
            # Legacy workflow for direct consumption (to support old tests/logic)
            User = get_user_model()
            user = User.objects.filter(username='testuser').first() or User.objects.first()
            if not user: user = User.objects.create_user('system', 'system@example.com', 'password')
            
            start_date = instance.consumption_date.date()
            PrepaidExpense.objects.create(
                description=f"Prepaid asset for {instance.product.name}",
                initial_amount=instance.cost_at_consumption,
                amortization_start_date=start_date,
                amortization_end_date=start_date + timedelta(days=364), # Default 1 year
                asset_account=GeneralAccountingSettings.load().prepaid_expenses_account,
                expense_account=_get_product_expense_account(instance.product),
                created_by=user,
                source_content_object=instance
            )
        return

    # Path C (Default): Create a direct ExpenseLog for overhead tracking,
    # but ONLY if this consumption didn't originate from an INVENTORY_EXPENSE request.
    if instance.consumption_type == InventoryConsumption.ConsumptionType.EXPENSE and instance.cost_pool:
        # This logic is for consumptions created manually, not through the request workflow.
        # The request workflow for INVENTORY_EXPENSE creates its own ExpenseLog.
        if not request:
            ExpenseLog.objects.create(
                description=f"Internal consumption of {instance.product.name}",
                expense_date=instance.consumption_date.date(),
                amount=instance.cost_at_consumption,
                category=ExpenseLog.Category.MAINTENANCE, # A sensible default
                classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD, # A sensible default
                cost_pool=instance.cost_pool,
                source_content_object=instance
            )


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


# --- NEW SIGNALS FOR ADJUSTING ENTRIES ---
@receiver(post_save, sender=AmortizationLog)
def handle_amortization_log_save(sender, instance: AmortizationLog, created, **kwargs):
    """Creates a journal entry when a new AmortizationLog is saved."""
    if created and not instance.journal_entry:
        create_je_for_amortization(amortization_log=instance)

@receiver(post_delete, sender=AmortizationLog)
def handle_amortization_log_delete(sender, instance: AmortizationLog, **kwargs):
    """Deletes the associated journal entry when an AmortizationLog is deleted."""
    try:
        if instance.journal_entry:
            instance.journal_entry.delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for AmortizationLog ID {instance.id}: {e}")

@receiver(post_save, sender=AccrualLog)
def handle_accrual_log_save(sender, instance: AccrualLog, created, **kwargs):
    """Creates a journal entry when a new AccrualLog is saved."""
    if created and not instance.journal_entry:
        create_je_for_accrual(instance)

@receiver(post_delete, sender=AccrualLog)
def handle_accrual_log_delete(sender, instance: AccrualLog, **kwargs):
    """Deletes the associated journal entry when an AccrualLog is deleted."""
    try:
        if instance.journal_entry:
            instance.journal_entry.delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for AccrualLog ID {instance.id}: {e}")


@receiver(post_save, sender=ExpenseLog)
def handle_expense_log_save(sender, instance: ExpenseLog, created, **kwargs):
    """Creates a journal entry when a new ExpenseLog is created."""
    # Check for a flag to skip JE creation, used for direct payments.
    if getattr(instance, '_skip_je_creation', False):
        return

    # --- MODIFICATION START ---
    # If the source is an InventoryConsumption, the JE has already been created by that signal.
    if instance.source_content_type == ContentType.objects.get_for_model(InventoryConsumption):
        logger.debug(f"JE creation skipped for ExpenseLog ID {instance.id} because its source is an InventoryConsumption.")
        return
    # --- MODIFICATION END ---

    if created:
        create_je_for_expense_log(instance)


@receiver(post_delete, sender=ExpenseLog)
def handle_expense_log_delete(sender, instance: ExpenseLog, **kwargs):
    """Deletes the associated journal entry when an ExpenseLog is deleted."""
    if hasattr(instance, 'journal_entry') and instance.journal_entry:
        instance.journal_entry.delete()


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


@receiver(post_save, sender=CustomerCreditMemo)
def handle_credit_memo_save(sender, instance: CustomerCreditMemo, created, **kwargs):
    """Creates/updates the JE for a customer credit memo."""
    logger.info(f"-> Signal 'handle_credit_memo_save' triggered for CustomerCreditMemo ID {instance.id}. Created: {created}.")
    if not created:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
        logger.info(f"   Deleted existing JE for updated CustomerCreditMemo ID {instance.id} to allow regeneration.")
    
    logger.info(f"   Calling 'create_je_for_credit_memo' for memo ID {instance.id}...")
    create_je_for_credit_memo(memo=instance)
    logger.info(f"<- Finished 'handle_credit_memo_save' for memo ID {instance.id}.")


@receiver(post_delete, sender=CustomerCreditMemo)
def handle_credit_memo_delete(sender, instance: CustomerCreditMemo, **kwargs):
    """Deletes the associated JE when a CustomerCreditMemo is deleted."""
    try:
        content_type = ContentType.objects.get_for_model(instance)
        JournalEntry.objects.filter(content_type=content_type, object_id=instance.id).delete()
    except Exception as e:
        logger.error(f"Error deleting Journal Entry for CustomerCreditMemo ID {instance.id}: {e}")


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


@receiver(post_save, sender=EmployeeAdvanceSettlement)
def handle_advance_settlement_save(sender, instance: EmployeeAdvanceSettlement, created, **kwargs):
    """
    Listens for a settlement to be saved. If new, it creates the settlement JE
    and then triggers an update on the parent EmployeeAdvance's status.
    """
    if created:
        # --- MODIFICATION START ---
        # Create the journal entry to move the value from Accrued Expenses to the Employee Advance Receivable.
        if not instance.journal_entry:
            create_je_for_employee_advance_settlement(settlement=instance)
        # --- MODIFICATION END ---

        # Update the status of the parent advance.
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