# inventory/services/expense_service.py
from datetime import date
from decimal import Decimal
from django.db.models import QuerySet
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.shortcuts import get_object_or_404

from ..models import (
    ExpenseRequest, Product, CostPool, FixedAsset, SupplierInvoice, Account, PrepaidExpense, AccrualLog,
    TransactionCorrection, Company, BankAccount
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
