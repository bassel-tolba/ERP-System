# inventory/services/expense_service.py
from datetime import date 
from decimal import Decimal 
from typing import List 
from django.db.models import QuerySet
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.db import transaction 
from django.contrib.contenttypes.models import ContentType # <-- ADD THIS IMPORT

from ..models import (
    ExpenseRequest, Product, CostPool, FixedAsset, SupplierInvoice, Account, PrepaidExpense, AccrualLog,
    TransactionCorrection, Company, BankAccount, ExpenseLog, SupplierInvoiceItem, EmployeeAdvance,
    EmployeeAdvanceSettlement, GeneralAccountingSettings, JournalEntry, JournalEntryLine
    
)
from . import adjusting_entries_service, accounting_service

User = settings.AUTH_USER_MODEL

# --- UTILITY (Internal) ---
def _can_user_modify_request(user: User, request: ExpenseRequest) -> bool:
    """Checks if a user has permission to modify a request."""
    if request.status != ExpenseRequest.Status.PENDING:
        raise PermissionDenied("Only PENDING requests can be modified.")
    if request.requested_by != user and not user.is_staff: # Example permission
        raise PermissionDenied("You do not have permission to modify this request.")
    return True

# --- CREATE ---
def request_direct_expense(
    user: User, amount: Decimal, request_date: date, description: str,
    cost_pool_id: int, category: str, classification: str,
    settlement_method: str, supplier_id: int = None, bank_account_id: int = None
) -> ExpenseRequest:
    cost_pool = get_object_or_404(CostPool, pk=cost_pool_id)

    # Validation
    if settlement_method == ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER and not supplier_id:
        raise ValidationError("A supplier is required for the 'Accrue and Pay Later' settlement method.")
    if settlement_method == ExpenseRequest.SettlementMethod.DIRECT_PAYMENT and not bank_account_id:
        raise ValidationError("A bank account is required for the 'Direct Payment' settlement method.")

    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.DIRECT_EXPENSE,
        requested_by=user,
        amount=amount,
        request_date=request_date,
        description=description,
        cost_pool=cost_pool,
        category=category,
        classification=classification,
        settlement_method=settlement_method,
        supplier_id=supplier_id,
        bank_account_id=bank_account_id
    )

def request_inventory_expense(user: User, product_id: int, quantity: Decimal, request_date: date, description: str, cost_pool_id: int) -> ExpenseRequest:
    product = get_object_or_404(Product, pk=product_id)
    cost_pool = get_object_or_404(CostPool, pk=cost_pool_id)
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVENTORY_EXPENSE,
        requested_by=user,
        product=product,
        quantity=quantity,
        request_date=request_date,
        description=description,
        cost_pool=cost_pool
    )

def request_inventory_capitalization(user: User, product_id: int, quantity: Decimal, request_date: date, description: str, fixed_asset_id: int) -> ExpenseRequest:
    product = get_object_or_404(Product, pk=product_id)
    fixed_asset = get_object_or_404(FixedAsset, pk=fixed_asset_id)
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
        requested_by=user,
        product=product,
        quantity=quantity,
        request_date=request_date,
        description=description,
        fixed_asset=fixed_asset
    )

def request_inventory_prepaid(user: User, product_id: int, quantity: Decimal, request_date: date, description: str, asset_account_id: int, expense_account_id: int, start_date: date, end_date: date) -> ExpenseRequest:
    product = get_object_or_404(Product, pk=product_id)
    asset_account = get_object_or_404(Account, pk=asset_account_id)
    expense_account = get_object_or_404(Account, pk=expense_account_id)
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVENTORY_PREPAID,
        requested_by=user,
        product=product,
        quantity=quantity,
        request_date=request_date,
        description=description,
        asset_account=asset_account,
        expense_account=expense_account,
        amortization_start_date=start_date,
        amortization_end_date=end_date
    )

def request_prepaid_from_invoice(user: User, invoice_id: int, description: str, asset_account_id: int, expense_account_id: int, start_date: date, end_date: date) -> ExpenseRequest:
    invoice = get_object_or_404(SupplierInvoice, pk=invoice_id)
    asset_account = get_object_or_404(Account, pk=asset_account_id)
    expense_account = get_object_or_404(Account, pk=expense_account_id)
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVOICE_PREPAID,
        requested_by=user,
        source_invoice=invoice,
        amount=invoice.total_amount,
        request_date=invoice.invoice_date,
        description=description,
        asset_account=asset_account,
        expense_account=expense_account,
        amortization_start_date=start_date,
        amortization_end_date=end_date
    )

def request_accrual(user: User, amount: Decimal, request_date: date, description: str, expense_account_id: int, start_date: date, end_date: date) -> ExpenseRequest:
    """Creates a request to accrue an expense over a period."""
    expense_account = get_object_or_404(Account, pk=expense_account_id)
    if expense_account.account_type != Account.AccountType.EXPENSE:
        raise ValidationError("The selected account must be an expense account.")

    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.ACCRUAL,
        requested_by=user,
        amount=amount,
        request_date=request_date,
        description=description,
        expense_account=expense_account,
        amortization_start_date=start_date,
        amortization_end_date=end_date
    )

# --- READ ---
def get_expense_request(request_id: int) -> ExpenseRequest:
    return ExpenseRequest.objects.get(pk=request_id)

def query_expense_requests(filters: dict) -> QuerySet[ExpenseRequest]:
    return ExpenseRequest.objects.filter(**filters)

# --- UPDATE ---
def update_pending_request(request_id: int, user: User, **data) -> ExpenseRequest:
    request = get_expense_request(request_id)
    _can_user_modify_request(user, request)
    
    for key, value in data.items():
        setattr(request, key, value)
    
    request.full_clean()
    request.save()
    return request

def link_invoice_to_prepaid(user: User, prepaid_asset_id: int, invoice_id: int) -> PrepaidExpense:
    prepaid = PrepaidExpense.objects.get(pk=prepaid_asset_id)
    invoice = SupplierInvoice.objects.get(pk=invoice_id)
    prepaid.notes = f"{prepaid.notes or ''}\nLinked to Invoice {invoice.invoice_number} by {user.username}."
    prepaid.save(update_fields=['notes'])
    return prepaid

def settle_accrual(user: User, accrual_log_id: int, invoice_id: int):
    """
    Settles a specific accrual log with a supplier invoice, creating a true-up JE.
    """
    accrual_log = get_object_or_404(AccrualLog, pk=accrual_log_id)
    invoice = get_object_or_404(SupplierInvoice, pk=invoice_id)

    if accrual_log.settling_invoice or accrual_log.true_up_journal_entry:
        raise ValidationError(f"Accrual Log #{accrual_log.id} has already been settled.")

    # The adjusting_entries_service function handles the core logic
    # including period checks and transaction management.
    je = adjusting_entries_service.settle_accrual_with_invoice(
        accrual_log=accrual_log,
        invoice=invoice
    )
    return je


# --- SETTLEMENT & A/P INTEGRATION ---

def create_invoice_from_expense_logs(
    user: User, supplier_id: int, invoice_number: str, invoice_date: date, due_date: date,
    expense_log_ids: List[int]
) -> SupplierInvoice:
    """
    Creates a SupplierInvoice from one or more unsettled ExpenseLogs.

    This service is used to formalize expenses that were approved with the
    'Accrue and Pay Later' method into a payable invoice. It marks the
    source logs as settled.
    """
    with transaction.atomic():
        supplier = get_object_or_404(Company, pk=supplier_id)
        logs_to_settle = ExpenseLog.objects.select_related('source_request').filter(id__in=expense_log_ids)

        if not logs_to_settle.exists():
            raise ValidationError("No valid Expense Logs were provided.")

        total_amount = Decimal('0.0')
        for log in logs_to_settle:
            if log.settlement_status != ExpenseLog.SettlementStatus.UNSETTLED:
                raise ValidationError(f"Expense Log #{log.id} ('{log.description}') has already been settled.")
            if log.source_request.supplier != supplier:
                raise ValidationError(f"Expense Log #{log.id} does not belong to supplier '{supplier.name}'.")
            total_amount += log.amount

        # Create the invoice header
        invoice = SupplierInvoice.objects.create(
            supplier=supplier,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            due_date=due_date,
            total_amount=total_amount,
            status=SupplierInvoice.InvoiceStatus.DRAFT
        )

        # Create invoice items from the expense logs
        for log in logs_to_settle:
            SupplierInvoiceItem.objects.create(
                invoice=invoice,
                expense_log=log,
                amount=log.amount
            )
            # Settle the log
            log.settlement_status = ExpenseLog.SettlementStatus.SETTLED
            log.settlement_object = invoice
        
        ExpenseLog.objects.bulk_update(logs_to_settle, ['settlement_status', 'settlement_content_type', 'settlement_object_id'])

    return invoice


@transaction.atomic
def settle_employee_advance_with_expense(
    user: User, advance_id: int, expense_log_id: int, settlement_date: date
) -> EmployeeAdvanceSettlement:
    """
    Settles an employee advance using an approved expense log.

    This creates a settlement record linking the advance to the expense,
    updates the expense log's status, and relies on a signal to create
    the corresponding journal entry.
    """
    advance = get_object_or_404(EmployeeAdvance.objects.select_for_update(), pk=advance_id)
    expense_log = get_object_or_404(ExpenseLog.objects.select_for_update(), pk=expense_log_id)

    # --- Validations ---
    if advance.status == EmployeeAdvance.Status.SETTLED:
        raise ValidationError(f"Advance {advance.id} is already settled.")

    # --- FIX: Validate against the expense log's status directly ---
    if expense_log.settlement_status == ExpenseLog.SettlementStatus.SETTLED:
        raise ValidationError("This expense has already been settled.")

    if expense_log.amount > advance.unsettled_amount:
        raise ValidationError(
            f"Expense amount ({expense_log.amount}) exceeds the advance's unsettled amount ({advance.unsettled_amount})."
        )
    
    # This check is still valid as a safeguard against race conditions or duplicate submissions
    if EmployeeAdvanceSettlement.objects.filter(
        object_id=expense_log.id, 
        content_type=ContentType.objects.get_for_model(ExpenseLog)
    ).exists():
        raise ValidationError(f"Expense Log {expense_log.id} has already been used to settle an advance.")

    # --- Create Settlement ---
    settlement = EmployeeAdvanceSettlement.objects.create(
        advance=advance,
        source_transaction=expense_log,
        amount_settled=expense_log.amount,
        settlement_date=settlement_date
    )
    
    # --- FIX: Explicitly update the expense log ---
    expense_log.settlement_status = ExpenseLog.SettlementStatus.SETTLED
    expense_log.settlement_object = settlement
    expense_log.save(update_fields=['settlement_status', 'settlement_content_type', 'settlement_object_id'])
    
    # The post_save signal on EmployeeAdvanceSettlement will handle JE creation
    # and updating the advance status.
    
    return settlement
# --- CORRECTION ---
def correct_approved_request(request_id: int, user: User, justification: str) -> TransactionCorrection:
    """
    Initiates the correction of an approved expense request.

    This service function acts as a wrapper around the core accounting logic,
    providing a clear entry point for correcting transactions that originated
    from an expense request. It creates a reversing journal entry and an
    audit trail.
    """
    if not justification:
        raise ValidationError("A justification is required to correct a transaction.")

    # The core logic is handled by the accounting service to maintain separation of concerns.
    correction_record = accounting_service.correct_approved_expense(
        request_id=request_id,
        user=user,
        justification=justification
    )
    return correction_record


# --- CANCEL ---
def cancel_pending_request(request_id: int, user: User) -> ExpenseRequest:
    request = get_expense_request(request_id)
    _can_user_modify_request(user, request)
    request.status = ExpenseRequest.Status.CANCELLED
    request.processed_by = user
    request.processed_at = timezone.now()
    request.save()
    return request
