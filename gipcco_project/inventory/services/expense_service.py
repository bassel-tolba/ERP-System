from datetime import date
from decimal import Decimal
from django.db.models import QuerySet
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from ..models import (
    ExpenseRequest, Product, CostPool, FixedAsset, SupplierInvoice, Account, PrepaidExpense
)

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
def request_direct_expense(user: User, amount: Decimal, request_date: date, description: str, cost_pool: CostPool, category: str, classification: str) -> ExpenseRequest:
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.DIRECT_EXPENSE,
        requested_by=user,
        amount=amount,
        request_date=request_date,
        description=description,
        cost_pool=cost_pool,
        category=category,
        classification=classification
    )

def request_inventory_expense(user: User, product: Product, quantity: Decimal, request_date: date, description: str, cost_pool: CostPool) -> ExpenseRequest:
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVENTORY_EXPENSE,
        requested_by=user,
        product=product,
        quantity=quantity,
        request_date=request_date,
        description=description,
        cost_pool=cost_pool
    )

def request_inventory_capitalization(user: User, product: Product, quantity: Decimal, request_date: date, description: str, fixed_asset: FixedAsset) -> ExpenseRequest:
    return ExpenseRequest.objects.create(
        request_type=ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
        requested_by=user,
        product=product,
        quantity=quantity,
        request_date=request_date,
        description=description,
        fixed_asset=fixed_asset
    )

def request_inventory_prepaid(user: User, product: Product, quantity: Decimal, request_date: date, description: str, asset_account: Account, expense_account: Account, start_date: date, end_date: date) -> ExpenseRequest:
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

def request_prepaid_from_invoice(user: User, invoice: SupplierInvoice, description: str, asset_account: Account, expense_account: Account, start_date: date, end_date: date) -> ExpenseRequest:
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

# --- CANCEL ---
def cancel_pending_request(request_id: int, user: User) -> ExpenseRequest:
    request = get_expense_request(request_id)
    _can_user_modify_request(user, request)
    request.status = ExpenseRequest.Status.CANCELLED
    request.processed_by = user
    request.processed_at = timezone.now()
    request.save()
    return request
