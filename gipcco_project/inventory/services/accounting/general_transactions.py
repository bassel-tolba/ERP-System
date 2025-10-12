# gipcco_project/inventory/services/accounting/general_transactions.py

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError, PermissionDenied

from ...models import (
    JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    BankTransfer, ExpenseLog, ExpenseRequest, Product,
    OpeningBalanceEntry, OpeningBalanceEntryLine, InventoryConsumption
)
from ._helpers import (
    _check_period_is_open, _get_product_inventory_account,
    _get_product_expense_account
)

logger = logging.getLogger(__name__)


def create_je_for_internal_consumption(consumption: InventoryConsumption) -> Optional[JournalEntry]:
    """
    Creates a journal entry for the internal consumption of an MRO or Consumable item.
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(consumption),
        object_id=consumption.id
    ).exists():
        logger.debug(f"Journal entry for InventoryConsumption ID {consumption.id} already exists. Aborting.")
        return None
        
    _check_period_is_open(consumption.consumption_date)

    total_cost = consumption.cost_at_consumption
    if total_cost <= 0:
        logger.info(f"Total consumption cost for InventoryConsumption ID {consumption.id} is zero. No JE created.")
        return None
        
    inventory_account = _get_product_inventory_account(consumption.product)
    
    if consumption.consumption_type == InventoryConsumption.ConsumptionType.CAPITALIZE:
        if not consumption.fixed_asset:
            raise ValueError(_("Cannot create capitalization JE for consumption without a linked Fixed Asset."))
        debit_account = consumption.fixed_asset.gl_account
        debit_sub_ledger = consumption.fixed_asset
    elif consumption.consumption_type == InventoryConsumption.ConsumptionType.AMORTIZE:
        settings = GeneralAccountingSettings.load()
        if not settings.prepaid_expenses_account:
            raise ValueError(_("The master Prepaid Expenses account is not configured in General Accounting Settings."))
        debit_account = settings.prepaid_expenses_account
        debit_sub_ledger = None
    else: # Default to EXPENSE
        debit_account = _get_product_expense_account(consumption.product)
        debit_sub_ledger = None

    with transaction.atomic():
        description = _(
            "Internal consumption of %(quantity)s %(unit)s of '%(product)s' by %(dept)s"
        ) % {
            'quantity': consumption.quantity_consumed,
            'unit': consumption.product.unit,
            'product': consumption.product.name,
            'dept': consumption.get_department_display()
        }
        
        je = JournalEntry.objects.create(
            date=consumption.consumption_date,
            description=description,
            source_object=consumption,
            status=JournalEntry.Status.POSTED
        )
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=debit_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.DEBIT,
            sub_ledger_object=debit_sub_ledger
        )
        
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=inventory_account,
            amount=total_cost.quantize(Decimal('0.001')),
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=consumption.product
        )
        
        je.validate_balance()
        logger.info(f"Successfully created Journal Entry JE-{je.id} for InventoryConsumption ID {consumption.id}.")
        
    return je


def create_je_for_bank_transfer(transfer: BankTransfer) -> Optional[JournalEntry]:
    """
    Creates a journal entry for an internal bank transfer.
    """
    if JournalEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(transfer), object_id=transfer.id
    ).exists():
        logger.debug(f"Journal entry for BankTransfer ID {transfer.id} already exists. Aborting.")
        return None

    _check_period_is_open(transfer.transfer_date)
    
    source_gl = transfer.source_account.gl_account
    dest_gl = transfer.destination_account.gl_account

    if not all([source_gl, dest_gl]):
        raise ValueError(_("One of the bank accounts in the transfer is missing its GL account link."))

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=transfer.transfer_date,
            description=transfer.description,
            source_object=transfer,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je, account=dest_gl, amount=transfer.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je, account=source_gl, amount=transfer.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )
        je.validate_balance()
        logger.info(f"Successfully created JE-{je.id} for BankTransfer ID {transfer.id}.")
    return je


def create_je_for_expense_log(expense_log: 'ExpenseLog'):
    """
    Creates a journal entry for a direct expense that is being accrued.
    """
    _check_period_is_open(expense_log.expense_date)

    settings = GeneralAccountingSettings.load()
    if not expense_log.cost_pool or not expense_log.cost_pool.gl_account:
        raise ValidationError(f"ExpenseLog #{expense_log.id} is missing a cost pool with a linked GL account.")
    if not settings.accrued_expenses_account:
        raise ValidationError("The Accrued Expenses liability account is not configured in General Accounting Settings.")

    debit_account = expense_log.cost_pool.gl_account
    credit_account = settings.accrued_expenses_account

    je = JournalEntry.objects.create(
        date=expense_log.expense_date,
        description=f"Direct expense: {expense_log.description}",
        source_object=expense_log,
        status=JournalEntry.Status.POSTED
    )

    JournalEntryLine.objects.create(
        journal_entry=je,
        account=debit_account,
        amount=expense_log.amount,
        entry_type=JournalEntryLine.EntryType.DEBIT
    )
    JournalEntryLine.objects.create(
        journal_entry=je,
        account=credit_account,
        amount=expense_log.amount,
        entry_type=JournalEntryLine.EntryType.CREDIT
    )
    je.validate_balance()


def create_transaction_for_direct_payment_expense(request: 'ExpenseRequest') -> 'ExpenseLog':
    """
    Creates an ExpenseLog and a direct payment Journal Entry for an approved
    direct expense request.
    """
    _check_period_is_open(request.request_date)

    if not request.cost_pool or not request.cost_pool.gl_account:
        raise ValidationError(f"ExpenseRequest #{request.id} is missing a cost pool with a linked GL account.")
    if not request.bank_account or not request.bank_account.gl_account:
        raise ValidationError(f"ExpenseRequest #{request.id} is missing a bank account with a linked GL account.")

    debit_account = request.cost_pool.gl_account
    credit_account = request.bank_account.gl_account

    with transaction.atomic():
        expense_log = ExpenseLog(
            description=request.description,
            expense_date=request.request_date,
            amount=request.amount,
            category=request.category,
            classification=request.classification,
            cost_pool=request.cost_pool,
            source_request=request,
            settlement_status=ExpenseLog.SettlementStatus.SETTLED
        )
        expense_log._skip_je_creation = True
        expense_log.save()

        je = JournalEntry.objects.create(
            date=request.request_date,
            description=f"Direct expense payment: {request.description}",
            source_object=expense_log,
            status=JournalEntry.Status.POSTED
        )

        JournalEntryLine.objects.create(
            journal_entry=je,
            account=debit_account,
            amount=request.amount,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        JournalEntryLine.objects.create(
            journal_entry=je,
            account=credit_account,
            amount=request.amount,
            entry_type=JournalEntryLine.EntryType.CREDIT,
            sub_ledger_object=request.bank_account
        )

        je.validate_balance()
        expense_log.settlement_object = je
        expense_log.save(update_fields=['settlement_content_type', 'settlement_object_id'])

    return expense_log


def create_je_for_opening_balance(ob_entry: 'OpeningBalanceEntry') -> JournalEntry:
    """
    Creates a single, multi-line journal entry from an Opening Balance Entry record.
    """
    logger.info(f"--> Starting Opening Balance JE creation for '{ob_entry.name}'.")
    
    if ob_entry.status == OpeningBalanceEntry.Status.POSTED:
        raise PermissionDenied(_("This opening balance entry has already been posted."))
    
    _check_period_is_open(ob_entry.migration_date)

    with transaction.atomic():
        je = JournalEntry.objects.create(
            date=ob_entry.migration_date,
            description=_(f"Opening Balance as of {ob_entry.migration_date}: {ob_entry.name}"),
            source_object=ob_entry,
            status=JournalEntry.Status.DRAFT
        )
        logger.info(f"    Created draft JE-{je.id} for OB Entry {ob_entry.id}.")

        total_debits = Decimal("0.0")
        total_credits = Decimal("0.0")

        for line in ob_entry.lines.prefetch_related('sub_ledger_details__sub_ledger_object').all():
            logger.info(f"    Processing OB Line for Account '{line.account.code}'...")

            if line.sub_ledger_details.exists():
                if line.account.sub_ledger_model == ContentType.objects.get_for_model(Product):
                    details_by_product = {}
                    for detail in line.sub_ledger_details.all():
                        product_id = detail.sub_ledger_object.pk
                        details_by_product[product_id] = details_by_product.get(product_id, Decimal('0.0')) + detail.amount
                    
                    for product_id, total_amount in details_by_product.items():
                        product_instance = Product.objects.get(pk=product_id)
                        JournalEntryLine.objects.create(
                            journal_entry=je,
                            account=line.account,
                            entry_type=line.entry_type,
                            amount=total_amount,
                            sub_ledger_object=product_instance
                        )
                        logger.info(f"        Created aggregated sub-ledger line for Product '{product_instance.name}': {line.entry_type} {line.account.code} for {total_amount}")

                else:
                    for detail in line.sub_ledger_details.all():
                        JournalEntryLine.objects.create(
                            journal_entry=je,
                            account=line.account,
                            entry_type=line.entry_type,
                            amount=detail.amount,
                            sub_ledger_object=detail.sub_ledger_object
                        )
                        logger.info(f"        Created sub-ledger line: {line.entry_type} {line.account.code} for {detail.amount} -> {detail.sub_ledger_object}")
            else:
                JournalEntryLine.objects.create(
                    journal_entry=je,
                    account=line.account,
                    entry_type=line.entry_type,
                    amount=line.total_amount
                )
                logger.info(f"        Created aggregate line: {line.entry_type} {line.account.code} for {line.total_amount}")

            if line.entry_type == OpeningBalanceEntryLine.EntryType.DEBIT:
                total_debits += line.total_amount
            else:
                total_credits += line.total_amount

        logger.info(f"    Validation: Total Debits = {total_debits}, Total Credits = {total_credits}")
        je.validate_balance()
        if total_debits != total_credits:
            raise ValueError(
                _(f"Opening Balance JE is not balanced. Debits ({total_debits}) do not equal Credits ({total_credits}).")
            )
        
        je.status = JournalEntry.Status.POSTED
        je.save(update_fields=['status'])
        
        ob_entry.journal_entry = je
        ob_entry.status = OpeningBalanceEntry.Status.POSTED
        ob_entry.posted_at = timezone.now()
        ob_entry.save(update_fields=['journal_entry', 'status', 'posted_at'])
        
        logger.info(f"<-- Successfully created and posted JE-{je.id} for Opening Balance Entry {ob_entry.id}.")
        
    return je
