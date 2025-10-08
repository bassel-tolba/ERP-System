from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.db.models import Q
from decimal import Decimal, InvalidOperation

from ..models import ExpenseRequest, Product, CostPool, FixedAsset, Account, SupplierInvoice, AccrualLog, Company, BankAccount, ExpenseLog
from ..services import expense_service, approval_service

@login_required
def manage_expense_requests(request):
    """
    Handles displaying, creating, and processing expense requests.
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'create':
                request_type = request.POST.get('request_type')
                description = request.POST.get('description')
                request_date = request.POST.get('request_date')

                if not all([request_type, description, request_date]):
                    raise ValidationError("Request Type, Date, and Description are required.")

                if request_type == ExpenseRequest.RequestType.DIRECT_EXPENSE:
                    amount_str = request.POST.get('amount')
                    cost_pool_id_str = request.POST.get('cost_pool')
                    if not amount_str or not cost_pool_id_str:
                        raise ValidationError("Amount and Cost Pool are required for a direct expense.")
                    
                    # --- NEW: Handle settlement fields ---
                    settlement_method = request.POST.get('settlement_method')
                    supplier_id_str = request.POST.get('supplier')
                    bank_account_id_str = request.POST.get('bank_account')

                    if not settlement_method:
                        raise ValidationError("A settlement method is required for direct expenses.")

                    expense_service.request_direct_expense(
                        user=request.user,
                        amount=Decimal(amount_str),
                        request_date=request_date,
                        description=description,
                        cost_pool_id=int(cost_pool_id_str),
                        category=request.POST.get('category'),
                        classification=request.POST.get('classification'),
                        settlement_method=settlement_method,
                        supplier_id=int(supplier_id_str) if supplier_id_str else None,
                        bank_account_id=int(bank_account_id_str) if bank_account_id_str else None
                    )
                elif request_type == ExpenseRequest.RequestType.INVENTORY_EXPENSE:
                    product_id_str = request.POST.get('product')
                    quantity_str = request.POST.get('quantity')
                    cost_pool_id_str = request.POST.get('cost_pool')
                    if not all([product_id_str, quantity_str, cost_pool_id_str]):
                        raise ValidationError("Product, Quantity, and Cost Pool are required for an inventory expense.")

                    expense_service.request_inventory_expense(
                        user=request.user,
                        product_id=int(product_id_str),
                        quantity=Decimal(quantity_str),
                        request_date=request_date,
                        description=description,
                        cost_pool_id=int(cost_pool_id_str)
                    )
                elif request_type == ExpenseRequest.RequestType.INVENTORY_CAPITALIZE:
                    product_id_str = request.POST.get('product')
                    quantity_str = request.POST.get('quantity')
                    fixed_asset_id_str = request.POST.get('fixed_asset')
                    if not all([product_id_str, quantity_str, fixed_asset_id_str]):
                        raise ValidationError("Product, Quantity, and Fixed Asset are required for capitalization.")

                    expense_service.request_inventory_capitalization(
                        user=request.user,
                        product_id=int(product_id_str),
                        quantity=Decimal(quantity_str),
                        request_date=request_date,
                        description=description,
                        fixed_asset_id=int(fixed_asset_id_str)
                    )
                elif request_type == ExpenseRequest.RequestType.INVENTORY_PREPAID:
                    product_id_str = request.POST.get('product')
                    quantity_str = request.POST.get('quantity')
                    asset_account_id_str = request.POST.get('asset_account')
                    expense_account_id_str = request.POST.get('expense_account')
                    start_date = request.POST.get('amortization_start_date')
                    end_date = request.POST.get('amortization_end_date')

                    if not all([product_id_str, quantity_str, asset_account_id_str, expense_account_id_str, start_date, end_date]):
                        raise ValidationError("All fields are required for a prepaid inventory request.")

                    expense_service.request_inventory_prepaid(
                        user=request.user,
                        product_id=int(product_id_str),
                        quantity=Decimal(quantity_str),
                        request_date=request_date,
                        description=description,
                        asset_account_id=int(asset_account_id_str),
                        expense_account_id=int(expense_account_id_str),
                        start_date=start_date,
                        end_date=end_date
                    )
                elif request_type == ExpenseRequest.RequestType.INVOICE_PREPAID:
                    invoice_id_str = request.POST.get('source_invoice')
                    asset_account_id_str = request.POST.get('asset_account')
                    expense_account_id_str = request.POST.get('expense_account')
                    start_date = request.POST.get('amortization_start_date')
                    end_date = request.POST.get('amortization_end_date')

                    if not all([invoice_id_str, asset_account_id_str, expense_account_id_str, start_date, end_date]):
                        raise ValidationError("All fields are required for a prepaid invoice request.")

                    expense_service.request_prepaid_from_invoice(
                        user=request.user,
                        invoice_id=int(invoice_id_str),
                        description=description,
                        asset_account_id=int(asset_account_id_str),
                        expense_account_id=int(expense_account_id_str),
                        start_date=start_date,
                        end_date=end_date
                    )
                elif request_type == ExpenseRequest.RequestType.ACCRUAL:
                    amount_str = request.POST.get('amount')
                    expense_account_id_str = request.POST.get('expense_account')
                    start_date = request.POST.get('accrual_start_date')
                    end_date = request.POST.get('accrual_end_date')

                    if not all([amount_str, expense_account_id_str, start_date, end_date]):
                        raise ValidationError("Amount, Expense Account, Start Date, and End Date are required for an accrual.")

                    expense_service.request_accrual(
                        user=request.user,
                        amount=Decimal(amount_str),
                        request_date=request_date,
                        description=description,
                        expense_account_id=int(expense_account_id_str),
                        start_date=start_date,
                        end_date=end_date
                    )
                else:
                    messages.error(request, "Invalid or unsupported request type specified.")
                
                if not messages.get_messages(request):
                    messages.success(request, "Expense request created successfully and is pending approval.")

            elif action == 'approve':
                request_id = request.POST.get('request_id')
                approval_service.approve_request(request_id, request.user)
                messages.success(request, f"Request #{request_id} has been approved.")

            elif action == 'reject':
                request_id = request.POST.get('request_id')
                reason = request.POST.get('rejection_reason')
                approval_service.reject_request(request_id, request.user, reason)
                messages.warning(request, f"Request #{request_id} has been rejected.")

            elif action == 'cancel':
                request_id = request.POST.get('request_id')
                expense_service.cancel_pending_request(request_id, request.user)
                messages.info(request, f"Request #{request_id} has been cancelled.")

            elif action == 'correct':
                request_id = request.POST.get('request_id')
                justification = request.POST.get('justification')
                expense_service.correct_approved_request(request_id, request.user, justification)
                messages.success(request, f"Correction for request #{request_id} has been processed successfully.")

            elif action == 'settle_accrual':
                accrual_log_id_str = request.POST.get('accrual_log_id')
                invoice_id_str = request.POST.get('invoice_id')

                if not accrual_log_id_str or not invoice_id_str:
                    raise ValidationError("Accrual Log and Invoice are required for settlement.")

                expense_service.settle_accrual(
                    user=request.user,
                    accrual_log_id=int(accrual_log_id_str),
                    invoice_id=int(invoice_id_str)
                )
                messages.success(request, f"Accrual Log #{accrual_log_id_str} has been successfully settled.")

        except (ValidationError, PermissionDenied, ValueError, TypeError, InvalidOperation) as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:manage_expense_requests')

    # GET request handling
    pending_requests = ExpenseRequest.objects.filter(status=ExpenseRequest.Status.PENDING).order_by('-request_date')
    processed_requests = ExpenseRequest.objects.exclude(status=ExpenseRequest.Status.PENDING).order_by('-processed_at')[:20]
    unsettled_accrual_logs = AccrualLog.objects.filter(
        settling_invoice__isnull=True
    ).select_related('accrued_expense', 'financial_period').order_by('-financial_period__start_date')

    context = {
        'active_page': 'expenses',
        'pending_requests': pending_requests,
        'processed_requests': processed_requests,
        'products': Product.objects.all(),
        'cost_pools': CostPool.objects.all(),
        'fixed_assets': FixedAsset.objects.all(),
        'asset_accounts': Account.objects.filter(account_type=Account.AccountType.ASSET),
        'expense_accounts': Account.objects.filter(account_type=Account.AccountType.EXPENSE),
        'invoices': SupplierInvoice.objects.filter(status=SupplierInvoice.InvoiceStatus.AWAITING_PAYMENT),
        'request_types': ExpenseRequest.RequestType.choices,
        'unsettled_accrual_logs': unsettled_accrual_logs,
        'categories': ExpenseLog.Category.choices,
        'classifications': ExpenseLog.Classification.choices,
        'settlement_methods': ExpenseRequest.SettlementMethod.choices,
        'suppliers': Company.objects.filter(is_supplier=True),
        'bank_accounts': BankAccount.objects.all(),
    }
    return render(request, 'inventory/expense_requests/manage.html', context)
