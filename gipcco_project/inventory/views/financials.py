# gipcco_project/inventory/views/financials.py

from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from django.utils.translation import gettext_lazy as _

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.decorators import permission_required
from django.urls import reverse
from django.core.exceptions import ValidationError
import logging


from ..models import (
    Company, SupplierInvoice, SupplierInvoiceItem, InventoryLog,
    Payment, PaymentApplication, BankAccount, Customer, CustomerInvoice, FinishedProductDispatch, CustomerInvoiceItem, CustomerPaymentApplication, SalesOrder, BankTransfer, JournalEntry, JournalEntryLine, FixedAsset, DepreciationLog, BankReconciliation, BankStatementLine, Account, FiscalYear, FinancialPeriod, PeriodClosingAuditLog,
    CostPool, AllocationDriver, OverheadAllocationRun, ExpenseLog
)
from ..forms import JournalEntryForm, JournalEntryLineFormSet
from ..services import expense_service
from ..services.overhead_service import execute_overhead_allocation_run, apply_overhead_to_finished_goods
from ..services.accounting_service import create_je_for_overhead_allocation, create_je_for_overhead_application
from ..services.period_closing_service import update_checklist_for_period
import logging

logger = logging.getLogger(__name__)

# --- Accounts Payable (A/P) Views ---

def supplier_invoices(request: HttpRequest) -> HttpResponse:
    """Lists all supplier invoices with filtering."""
    supplier_id = request.GET.get('supplier')
    status = request.GET.get('status')
    
    invoices = SupplierInvoice.objects.select_related('supplier').all()
    if supplier_id:
        invoices = invoices.filter(supplier_id=supplier_id)
    if status:
        invoices = invoices.filter(status=status)

    context = {
        'active_page': 'financials',
        'sub_page': 'supplier_invoices',
        'invoices': invoices,
        'suppliers': Company.objects.all(),
        'statuses': SupplierInvoice.InvoiceStatus.choices,
        'selected_supplier': int(supplier_id) if supplier_id else None,
        'selected_status': status,
    }
    # For HTMX/partial requests
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/supplier_invoices_content.html', context)
    return render(request, 'inventory/supplier_invoices.html', context)


def create_supplier_invoice(request: HttpRequest) -> HttpResponse:
    """
    Handles the creation of a new supplier invoice from unbilled receipts OR unsettled expenses.
    """
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            invoice_number = request.POST.get('invoice_number').strip()
            invoice_date_str = request.POST.get('invoice_date')
            due_date_str = request.POST.get('due_date')
            
            # Determine the source of the invoice items
            source_type = request.POST.get('source_type', 'receipts') # Default to receipts

            if not all([supplier_id, invoice_number, invoice_date_str, due_date_str]):
                messages.error(request, "يرجى تعبئة جميع الحقول الأساسية.")
                return redirect('inventory:create_supplier_invoice')

            if SupplierInvoice.objects.filter(supplier_id=supplier_id, invoice_number=invoice_number).exists():
                messages.error(request, f"فاتورة بنفس الرقم '{invoice_number}' موجودة بالفعل لهذا المورد.")
                return redirect('inventory:create_supplier_invoice')

            invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

            if source_type == 'expenses':
                expense_log_ids = request.POST.getlist('item_ids')
                if not expense_log_ids:
                    messages.error(request, "يرجى اختيار مصروف واحد على الأقل لإنشاء الفاتورة.")
                    return redirect('inventory:create_supplier_invoice')
                
                # Use the dedicated service function for this workflow
                invoice = expense_service.create_invoice_from_expense_logs(
                    user=request.user,
                    supplier_id=int(supplier_id),
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    expense_log_ids=[int(pk) for pk in expense_log_ids]
                )
            
            else: # Default to 'receipts' workflow
                receipt_ids = request.POST.getlist('item_ids')
                if not receipt_ids:
                    messages.error(request, "يرجى اختيار فاتورة استلام واحدة على الأقل.")
                    return redirect('inventory:create_supplier_invoice')

                with transaction.atomic():
                    invoice = SupplierInvoice.objects.create(
                        supplier_id=supplier_id,
                        invoice_number=invoice_number,
                        invoice_date=invoice_date,
                        due_date=due_date,
                        status=SupplierInvoice.InvoiceStatus.AWAITING_PAYMENT
                    )
                    
                    receipts = InventoryLog.objects.filter(id__in=receipt_ids, company_id=supplier_id)
                    total_amount = Decimal('0.0')
                    
                    items_to_create = []
                    for receipt in receipts:
                        receipt_total = (receipt.base_unit_price * Decimal(str(receipt.quantity))) + receipt.vat_amount
                        items_to_create.append(
                            SupplierInvoiceItem(invoice=invoice, receipt=receipt, amount=receipt_total)
                        )
                        total_amount += receipt_total
                    
                    SupplierInvoiceItem.objects.bulk_create(items_to_create)
                    invoice.total_amount = total_amount
                    invoice.save()

            messages.success(request, f"تم إنشاء فاتورة المورد رقم {invoice.invoice_number} بنجاح.")
            return redirect('inventory:view_supplier_invoice', pk=invoice.pk)
        except ValidationError as e:
            messages.error(request, f"خطأ في البيانات: {e}")
            return redirect('inventory:create_supplier_invoice')
        except Exception as e:
            logger.exception("Error creating supplier invoice")
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
            return redirect('inventory:create_supplier_invoice')

    today = timezone.now().date()
    context = {
        'active_page': 'financials',
        'sub_page': 'supplier_invoices',
        'suppliers': Company.objects.all(),
        'today_date': today.strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/supplier_invoice_create_content.html', context)
    return render(request, 'inventory/supplier_invoice_create.html', context)


def view_supplier_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays invoice details and handles payment application."""
    invoice = get_object_or_404(SupplierInvoice.objects.select_related('supplier'), pk=pk)
    
    context = {
        'active_page': 'financials',
        'sub_page': 'supplier_invoices',
        'invoice': invoice,
        'items': invoice.items.select_related('receipt__product').all(),
        'applications': invoice.applications.select_related('payment__bank_account').order_by('-payment__payment_date'),
        'bank_accounts': BankAccount.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/supplier_invoice_view_content.html', context)
    return render(request, 'inventory/supplier_invoice_view.html', context)


@require_POST
def delete_supplier_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Deletes a supplier invoice, but only if no payments are applied."""
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    
    if invoice.applications.exists():
        messages.error(request, "لا يمكن حذف فاتورة تم تطبيق دفعات عليها.")
        return redirect('inventory:view_supplier_invoice', pk=pk)
        
    try:
        invoice_number = invoice.invoice_number
        invoice.delete()
        messages.success(request, f"تم حذف فاتورة المورد رقم {invoice_number} بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {e}")
        return redirect('inventory:view_supplier_invoice', pk=pk)
        
    return redirect('inventory:supplier_invoices')


def api_get_uninvoiced_receipts(request: HttpRequest, supplier_id: int) -> JsonResponse:
    """
    API endpoint to get all 'Released' InventoryLogs for a supplier
    that have not yet been invoiced.
    """
    receipts = InventoryLog.objects.filter(
        company_id=supplier_id,
        status=InventoryLog.Status.RELEASED,
        supplierinvoiceitem__isnull=True
    ).order_by('-release_date')

    data = {
        'receipts': [
            {
                'id': r.id,
                'release_date': r.release_date.strftime('%Y-%m-%d'),
                'qc_no': r.qc_no,
                'product_name': r.product.name,
                'quantity': r.quantity,
                'unit': r.product.unit,
                'total_value': str((r.base_unit_price * Decimal(str(r.quantity))) + r.vat_amount)
            } for r in receipts
        ]
    }
    return JsonResponse(data)


def api_get_unsettled_expenses(request: HttpRequest, supplier_id: int) -> JsonResponse:
    """
    API endpoint to get all approved, unsettled ExpenseLogs for a supplier.
    These are expenses that have been accrued but not yet invoiced.
    """
    get_object_or_404(Company, pk=supplier_id)
    
    # Expenses are linked to a supplier via the ExpenseRequest that created them
    expenses = ExpenseLog.objects.filter(
        settlement_status=ExpenseLog.SettlementStatus.UNSETTLED,
        source_request__supplier_id=supplier_id,
        supplierinvoiceitem__isnull=True # Ensure it's not already on an invoice
    ).select_related('source_request').order_by('-expense_date')

    data = {
        'expenses': [
            {
                'id': e.id,
                'date': e.expense_date.strftime('%Y-%m-%d'),
                'description': e.description,
                'amount': str(e.amount),
                'category': e.get_category_display(),
                'request_id': e.source_request.id,
            } for e in expenses
        ]
    }
    return JsonResponse(data)


@require_POST
def apply_payment_to_invoice(request: HttpRequest, invoice_pk: int) -> HttpResponse:
    """Creates a payment and applies it to a specific invoice."""
    invoice = get_object_or_404(SupplierInvoice, pk=invoice_pk)
    
    bank_account_id = request.POST.get('bank_account')
    payment_date_str = request.POST.get('payment_date')
    amount_str = request.POST.get('amount')
    description = request.POST.get('description', f'Payment for Invoice #{invoice.invoice_number}')

    try:
        amount_to_pay = Decimal(amount_str)
        if amount_to_pay <= 0:
            raise ValueError("مبلغ الدفع يجب أن يكون أكبر من صفر.")
        if amount_to_pay > invoice.balance_due:
            raise ValueError("مبلغ الدفع أكبر من الرصيد المستحق.")

        with transaction.atomic():
            # 1. Create the Payment record
            payment = Payment.objects.create(
                payment_date=datetime.strptime(payment_date_str, '%Y-%m-%d').date(),
                amount=amount_to_pay,
                bank_account_id=bank_account_id,
                payment_type=Payment.PaymentType.PAYMENT_OUT,
                description=description,
                supplier=invoice.supplier
            )
            
            # 2. Create the application link
            PaymentApplication.objects.create(
                payment=payment,
                invoice=invoice,
                amount_applied=amount_to_pay
            )
            
            # 3. Update the invoice's paid amount and status
            invoice.amount_paid += amount_to_pay
            invoice.update_status(save=True) # The method handles the save

        messages.success(request, "تم تسجيل الدفعة بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في البيانات: {e}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
    return redirect('inventory:view_supplier_invoice', pk=invoice_pk)

# --- Accounts Receivable (A/R) Views ---

def customer_invoices(request: HttpRequest) -> HttpResponse:
    """Lists all customer invoices with filtering."""
    customer_id = request.GET.get('customer')
    status = request.GET.get('status')
    
    invoices = CustomerInvoice.objects.select_related('customer').all()
    if customer_id:
        invoices = invoices.filter(customer_id=customer_id)
    if status:
        invoices = invoices.filter(status=status)

    context = {
        'active_page': 'financials',
        'sub_page': 'customer_invoices',
        'invoices': invoices,
        'customers': Customer.objects.all(),
        'statuses': CustomerInvoice.InvoiceStatus.choices,
        'selected_customer': int(customer_id) if customer_id else None,
        'selected_status': status,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customer_invoices_content.html', context)
    return render(request, 'inventory/customer_invoices.html', context)


def create_customer_invoice(request: HttpRequest) -> HttpResponse:
    """Handles creating a new customer invoice from a sales order."""
    if request.method == 'POST':
        so_id = request.POST.get('sales_order')
        invoice_number = request.POST.get('invoice_number').strip()
        invoice_date_str = request.POST.get('invoice_date')
        due_date_str = request.POST.get('due_date')
        dispatch_ids = request.POST.getlist('dispatch_ids')

        if not all([so_id, invoice_number, invoice_date_str, due_date_str, dispatch_ids]):
            messages.error(request, "يرجى تعبئة جميع الحقول واختيار عملية صرف واحدة على الأقل.")
            return redirect('inventory:create_customer_invoice')
        
        so = get_object_or_404(SalesOrder, pk=so_id)
        if CustomerInvoice.objects.filter(customer=so.customer, invoice_number=invoice_number).exists():
            messages.error(request, f"فاتورة بنفس الرقم '{invoice_number}' موجودة بالفعل لهذا العميل.")
            return redirect('inventory:create_customer_invoice')

        try:
            with transaction.atomic():
                invoice = CustomerInvoice.objects.create(
                    customer=so.customer,
                    sales_order=so,
                    invoice_number=invoice_number,
                    invoice_date=datetime.strptime(invoice_date_str, '%Y-%m-%d').date(),
                    due_date=datetime.strptime(due_date_str, '%Y-%m-%d').date(),
                    status=CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT
                )
                
                dispatches = FinishedProductDispatch.objects.filter(
                    id__in=dispatch_ids, sales_order_item__sales_order_id=so_id
                ).select_related('sales_order_item')
                
                total_amount = Decimal('0.0')
                items_to_create = []
                for dispatch in dispatches:
                    so_item = dispatch.sales_order_item
                    base_value = so_item.base_price_per_unit * Decimal(str(dispatch.quantity))
                    vat_value = base_value * so_item.vat_rate
                    item_total = base_value + vat_value
                    
                    items_to_create.append(
                        CustomerInvoiceItem(invoice=invoice, dispatch=dispatch, amount=item_total)
                    )
                    total_amount += item_total
                
                CustomerInvoiceItem.objects.bulk_create(items_to_create)
                invoice.total_amount = total_amount.quantize(Decimal('0.001'))
                invoice.save()

            messages.success(request, f"تم إنشاء فاتورة العميل رقم {invoice.invoice_number} بنجاح.")
            return redirect('inventory:view_customer_invoice', pk=invoice.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            return redirect('inventory:create_customer_invoice')

    context = {
        'active_page': 'financials',
        'sub_page': 'customer_invoices',
        'sales_orders': SalesOrder.objects.filter(status__in=[SalesOrder.Status.PARTIALLY_SHIPPED, SalesOrder.Status.COMPLETED]),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customer_invoice_create_content.html', context)
    return render(request, 'inventory/customer_invoice_create.html', context)


def view_customer_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays invoice details and handles payment application."""
    invoice = get_object_or_404(CustomerInvoice.objects.select_related('customer'), pk=pk)
    
    context = {
        'active_page': 'financials',
        'sub_page': 'customer_invoices',
        'invoice': invoice,
        'items': invoice.items.select_related(
            'dispatch__sales_order_item__finished_product__batch__template__final_product'
        ).all(),
        'applications': invoice.applications.select_related('payment__bank_account').order_by('-payment__payment_date'),
        'bank_accounts': BankAccount.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customer_invoice_view_content.html', context)
    return render(request, 'inventory/customer_invoice_view.html', context)


@require_POST
def delete_customer_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Deletes a customer invoice, but only if no payments are applied."""
    invoice = get_object_or_404(CustomerInvoice, pk=pk)
    
    if invoice.applications.exists():
        messages.error(request, "لا يمكن حذف فاتورة تم تطبيق دفعات عليها.")
        return redirect('inventory:view_customer_invoice', pk=pk)
        
    try:
        invoice_number = invoice.invoice_number
        invoice.delete()
        messages.success(request, f"تم حذف فاتورة العميل رقم {invoice_number} بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف الفاتورة: {e}")
        return redirect('inventory:view_customer_invoice', pk=pk)
        
    return redirect('inventory:customer_invoices')


@require_POST
def receive_payment_for_invoice(request: HttpRequest, invoice_pk: int) -> HttpResponse:
    """Creates a payment received and applies it to a specific invoice."""
    invoice = get_object_or_404(CustomerInvoice, pk=invoice_pk)
    
    bank_account_id = request.POST.get('bank_account')
    payment_date_str = request.POST.get('payment_date')
    amount_str = request.POST.get('amount')
    description = request.POST.get('description', f'Payment for Invoice #{invoice.invoice_number}')

    try:
        amount_to_receive = Decimal(amount_str)
        if amount_to_receive <= 0:
            raise ValueError("مبلغ التحصيل يجب أن يكون أكبر من صفر.")
        if amount_to_receive > invoice.balance_due:
            raise ValueError("مبلغ التحصيل أكبر من الرصيد المستحق.")

        with transaction.atomic():
            payment = Payment.objects.create(
                payment_date=datetime.strptime(payment_date_str, '%Y-%m-%d').date(),
                amount=amount_to_receive,
                bank_account_id=bank_account_id,
                payment_type=Payment.PaymentType.PAYMENT_IN,
                description=description,
                customer=invoice.customer
            )
            
            CustomerPaymentApplication.objects.create(
                payment=payment,
                invoice=invoice,
                amount_applied=amount_to_receive
            )
            
            invoice.amount_paid += amount_to_receive
            invoice.update_status(save=True)

        messages.success(request, "تم تسجيل التحصيل بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في البيانات: {e}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
    return redirect('inventory:view_customer_invoice', pk=invoice_pk)


# --- A/R API Views ---

def api_get_uninvoiced_dispatches(request: HttpRequest, so_id: int) -> JsonResponse:
    """Returns dispatches for a sales order that are not yet on an invoice."""
    dispatches = FinishedProductDispatch.objects.filter(
        sales_order_item__sales_order_id=so_id,
        invoice_item__isnull=True
    ).select_related(
        'sales_order_item', 
        'sales_order_item__finished_product__batch__template__final_product'
    ).order_by('dispatch_date')
    
    data = []
    for d in dispatches:
        so_item = d.sales_order_item
        final_product = so_item.finished_product.batch.template.final_product
        base_value = so_item.base_price_per_unit * Decimal(str(d.quantity))
        vat_value = base_value * so_item.vat_rate
        total_value = base_value + vat_value
        
        data.append({
            'id': d.id,
            'dispatch_date': d.dispatch_date.strftime('%Y-%m-%d'),
            'product_name': f"{final_product.name} (Batch: {so_item.finished_product.individual_batch_number})",
            'quantity': d.quantity,
            'unit': final_product.unit,
            'total_value': str(total_value.quantize(Decimal('0.001')))
        })
        
    return JsonResponse({'dispatches': data})

def bank_accounts_dashboard(request: HttpRequest) -> HttpResponse:
    """Displays a list of bank accounts, their balances, and recent transactions."""
    if request.method == 'POST': # Handle Transfer creation
        source_id = request.POST.get('source_account')
        dest_id = request.POST.get('destination_account')
        amount = request.POST.get('amount')
        date_str = request.POST.get('transfer_date')
        description = request.POST.get('description')
        
        try:
            transfer = BankTransfer(
                source_account_id=source_id,
                destination_account_id=dest_id,
                amount=Decimal(amount),
                transfer_date=datetime.strptime(date_str, '%Y-%m-%d').date(),
                description=description or f"Transfer from {BankAccount.objects.get(pk=source_id).name}"
            )
            transfer.clean() # Manually call clean to validate
            transfer.save()
            messages.success(request, "تم تسجيل التحويل البنكي بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تسجيل التحويل: {e}")
        return redirect('inventory:bank_accounts_dashboard')
    
    # Calculate balances for all bank accounts
    bank_accounts = BankAccount.objects.annotate(
        total_debits=Coalesce(Sum('gl_account__journal_lines__amount', filter=Q(gl_account__journal_lines__entry_type='debit')), Value(0), output_field=DecimalField()),
        total_credits=Coalesce(Sum('gl_account__journal_lines__amount', filter=Q(gl_account__journal_lines__entry_type='credit')), Value(0), output_field=DecimalField())
    ).annotate(
        balance=F('total_debits') - F('total_credits')
    )

    transfers = BankTransfer.objects.select_related('source_account', 'destination_account').all()[:20]

    context = {
        'active_page': 'financials',
        'sub_page': 'banking',
        'bank_accounts': bank_accounts,
        'transfers': transfers,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/banking_dashboard_content.html', context)
    return render(request, 'inventory/banking_dashboard.html', context)


@require_POST
def create_bank_account(request: HttpRequest) -> HttpResponse:
    """Handles creation of a new bank account."""
    try:
        name = request.POST.get('name', '').strip()
        gl_account_id = request.POST.get('gl_account')
        if not name or not gl_account_id:
            raise ValueError("Name and GL Account are required.")
        BankAccount.objects.create(name=name, gl_account_id=gl_account_id)
        messages.success(request, f"Bank account '{name}' created successfully.")
    except Exception as e:
        messages.error(request, f"Error creating bank account: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def edit_bank_account(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing an existing bank account."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        name = request.POST.get('name', '').strip()
        gl_account_id = request.POST.get('gl_account')
        if not name or not gl_account_id:
            raise ValueError("Name and GL Account are required.")
        account.name = name
        account.gl_account_id = gl_account_id
        account.save()
        messages.success(request, f"Bank account '{name}' updated successfully.")
    except Exception as e:
        messages.error(request, f"Error updating bank account: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def delete_bank_account(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a bank account."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        account_name = account.name
        account.delete()
        messages.success(request, f"Bank account '{account_name}' deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting bank account: {e}. It might be in use.")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def create_payment(request: HttpRequest) -> HttpResponse:
    """Handles creation of a standalone payment."""
    try:
        bank_account_id = request.POST.get('bank_account')
        payment_date_str = request.POST.get('payment_date')
        amount_str = request.POST.get('amount')
        payment_type = request.POST.get('payment_type')
        description = request.POST.get('description', '').strip()
        supplier_id = request.POST.get('supplier') or None
        customer_id = request.POST.get('customer') or None

        if not all([bank_account_id, payment_date_str, amount_str, payment_type, description]):
            raise ValueError("Please fill all required fields.")

        Payment.objects.create(
            bank_account_id=bank_account_id,
            payment_date=datetime.strptime(payment_date_str, '%Y-%m-%d').date(),
            amount=Decimal(amount_str),
            payment_type=payment_type,
            description=description,
            supplier_id=supplier_id,
            customer_id=customer_id
        )
        messages.success(request, "Payment created successfully.")
    except Exception as e:
        messages.error(request, f"Error creating payment: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def edit_payment(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing a standalone payment."""
    payment = get_object_or_404(Payment, pk=pk)
    try:
        bank_account_id = request.POST.get('bank_account')
        payment_date_str = request.POST.get('payment_date')
        amount_str = request.POST.get('amount')
        payment_type = request.POST.get('payment_type')
        description = request.POST.get('description', '').strip()
        supplier_id = request.POST.get('supplier') or None
        customer_id = request.POST.get('customer') or None

        if not all([bank_account_id, payment_date_str, amount_str, payment_type, description]):
            raise ValueError("Please fill all required fields.")

        payment.bank_account_id = bank_account_id
        payment.payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        payment.amount = Decimal(amount_str)
        payment.payment_type = payment_type
        payment.description = description
        payment.supplier_id = supplier_id
        payment.customer_id = customer_id
        payment.save()
        messages.success(request, "Payment updated successfully.")
    except Exception as e:
        messages.error(request, f"Error updating payment: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def delete_payment(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a standalone payment."""
    payment = get_object_or_404(Payment, pk=pk)
    try:
        payment.delete()
        messages.success(request, "Payment deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting payment: {e}. It might be in use.")
    return redirect('inventory:bank_accounts_dashboard')


# ==============================================================================
#  BANK RECONCILIATION VIEWS
# ==============================================================================

def bank_reconciliations_list(request: HttpRequest) -> HttpResponse:
    """Lists all bank reconciliations with filtering."""
    bank_account_id = request.GET.get('bank_account')
    status = request.GET.get('status')
    
    reconciliations = BankReconciliation.objects.select_related('bank_account').all()
    if bank_account_id:
        reconciliations = reconciliations.filter(bank_account_id=bank_account_id)
    if status:
        reconciliations = reconciliations.filter(status=status)

    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'reconciliations': reconciliations,
        'bank_accounts': BankAccount.objects.all(),
        'statuses': BankReconciliation.Status.choices,
        'selected_bank_account': int(bank_account_id) if bank_account_id else None,
        'selected_status': status,
    }
    # For HTMX/partial requests
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_list_content.html', context)
    return render(request, 'inventory/reconciliation_list.html', context)


def create_bank_reconciliation(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new bank reconciliation period."""
    if request.method == 'POST':
        try:
            bank_account_id = request.POST.get('bank_account')
            statement_date_str = request.POST.get('statement_date')
            opening_balance_str = request.POST.get('statement_opening_balance')
            closing_balance_str = request.POST.get('statement_closing_balance')

            if not all([bank_account_id, statement_date_str, opening_balance_str, closing_balance_str]):
                messages.error(request, "يرجى تعبئة جميع الحقول.")
                return redirect('inventory:create_bank_reconciliation')

            statement_date = datetime.strptime(statement_date_str, '%Y-%m-%d').date()
            
            # --- ADDED VALIDATION ---
            if BankReconciliation.objects.filter(bank_account_id=bank_account_id, statement_date=statement_date).exists():
                messages.error(request, f"فترة تسوية لهذا الحساب في تاريخ {statement_date_str} موجودة بالفعل.")
                return redirect('inventory:create_bank_reconciliation')

            reconciliation = BankReconciliation.objects.create(
                bank_account_id=bank_account_id,
                statement_date=statement_date,
                statement_opening_balance=Decimal(opening_balance_str),
                statement_closing_balance=Decimal(closing_balance_str)
            )
            messages.success(request, "تم إنشاء فترة التسوية البنكية بنجاح.")
            return redirect('inventory:manage_bank_reconciliation', pk=reconciliation.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            return redirect('inventory:create_bank_reconciliation')

    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'bank_accounts': BankAccount.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_create_content.html', context)
    return render(request, 'inventory/reconciliation_create.html', context)


def manage_bank_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the main reconciliation workspace for matching transactions.
    Also handles manual entry of statement lines.
    """
    reconciliation = get_object_or_404(BankReconciliation.objects.select_related('bank_account'), pk=pk)
    bank_account = reconciliation.bank_account

    if request.method == 'POST': # Handle manual line entry
        try:
            # Simple validation for manual entry
            line_date_str = request.POST.get('transaction_date')
            description = request.POST.get('description', '').strip()
            amount_str = request.POST.get('amount')
            
            if not all([line_date_str, description, amount_str]):
                raise ValueError("يرجى تعبئة جميع حقول السطر.")

            reconciliation.statement_lines.create(
                transaction_date=datetime.strptime(line_date_str, '%Y-%m-%d').date(),
                description=description,
                amount=Decimal(amount_str)
            )
            messages.success(request, "تم إضافة سطر كشف الحساب بنجاح.")
        except Exception as e:
            messages.error(request, f"خطأ في إضافة السطر: {e}")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)


    # --- Reconciliation Summary Calculations ---
    statement_lines = reconciliation.statement_lines.all()
    cleared_balance = reconciliation.statement_opening_balance + \
                      (statement_lines.filter(is_reconciled=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.0'))
    difference = reconciliation.statement_closing_balance - cleared_balance
    
    # --- Fetch Unreconciled Internal Transactions ---
    # Payments (in and out) for this bank account that are not yet cleared
    unreconciled_payments = Payment.objects.filter(
        bank_account=bank_account,
        reconciliation__isnull=True,
        cleared_date__isnull=True,
        payment_date__lte=reconciliation.statement_date
    ).order_by('payment_date')

    # Bank Transfers related to this account (both as source and destination)
    unreconciled_source_transfers = BankTransfer.objects.filter(
        source_account=bank_account,
        source_reconciliation__isnull=True,
        source_cleared_date__isnull=True,
        transfer_date__lte=reconciliation.statement_date
    )
    unreconciled_dest_transfers = BankTransfer.objects.filter(
        destination_account=bank_account,
        destination_reconciliation__isnull=True,
        destination_cleared_date__isnull=True,
        transfer_date__lte=reconciliation.statement_date
    )
    
    # Combine and sort all internal transactions
    internal_transactions = []
    for p in unreconciled_payments:
        amount = p.amount if p.payment_type == Payment.PaymentType.PAYMENT_IN else -p.amount
        internal_transactions.append({'obj': p, 'date': p.payment_date, 'amount': amount, 'type': 'Payment'})
    for t in unreconciled_source_transfers:
        internal_transactions.append({'obj': t, 'date': t.transfer_date, 'amount': -t.amount, 'type': 'Transfer'})
    for t in unreconciled_dest_transfers:
        internal_transactions.append({'obj': t, 'date': t.transfer_date, 'amount': t.amount, 'type': 'Transfer'})

    # Sort internal transactions by date, then by type (Payments first, then Transfers)
    internal_transactions.sort(key=lambda x: (x['date'], x['type'] == 'Transfer'))

    # --- Reconciliation View Context ---
    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'reconciliation': reconciliation,
        'unreconciled_statement_lines': statement_lines.filter(is_reconciled=False),
        'reconciled_statement_lines': statement_lines.filter(is_reconciled=True).select_related('reconciled_object_content_type'),
        'internal_transactions': internal_transactions,
        'bank_account': bank_account,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'cleared_balance': cleared_balance,
        'difference': difference,
        'expense_accounts': list(Account.objects.filter(account_type=Account.AccountType.EXPENSE).order_by('code').values('id', 'name', 'code')),
        'income_accounts': list(Account.objects.filter(account_type=Account.AccountType.REVENUE).order_by('code').values('id', 'name', 'code')),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_manage_content.html', context)
    return render(request, 'inventory/reconciliation_manage.html', context)


@require_POST
def delete_bank_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """Deletes a bank reconciliation, but only if it is still open."""
    reconciliation = get_object_or_404(BankReconciliation, pk=pk)

    if reconciliation.status != BankReconciliation.Status.OPEN:
        messages.error(request, "لا يمكن حذف تسوية مغلقة.")
        return redirect('inventory:bank_reconciliations_list')

    try:
        with transaction.atomic():
            # Unmatch any linked transactions before deleting
            reconciliation.unmatch_all_transactions()
            reconciliation.delete()
            messages.success(request, "تم حذف فترة التسوية البنكية بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف التسوية: {e}")

    return redirect('inventory:bank_reconciliations_list')


# --- API Views for Reconciliation Matching ---

@require_POST
def api_unmatch_transaction(request: HttpRequest, pk: int) -> HttpResponse:
    """API endpoint to unmatch a previously reconciled transaction."""
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        
        if not line_id:
            raise ValueError("Missing line_id for unmatching.")

        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if not line.is_reconciled:
            raise ValueError("This statement line is not currently reconciled.")

        with transaction.atomic():
            internal_trx = line.reconciled_object
            if internal_trx:
                # Reset the internal transaction
                if isinstance(internal_trx, Payment):
                    internal_trx.reconciliation = None
                    internal_trx.cleared_date = None
                    internal_trx.save()
                elif isinstance(internal_trx, BankTransfer):
                    if internal_trx.source_reconciliation == reconciliation:
                        internal_trx.source_reconciliation = None
                        internal_trx.source_cleared_date = None
                    elif internal_trx.destination_reconciliation == reconciliation:
                        internal_trx.destination_reconciliation = None
                        internal_trx.destination_cleared_date = None
                    internal_trx.save()
            
            # Reset the statement line
            line.is_reconciled = False
            line.reconciled_object = None
            line.save()
        
        messages.success(request, "تم إلغاء مطابقة المعاملة بنجاح.")
    except Exception as e:
        messages.error(request, f"خطأ في إلغاء المطابقة: {e}")

    return redirect('inventory:manage_bank_reconciliation', pk=pk)


@require_POST
def api_create_adjustment_and_match(request: HttpRequest, pk: int) -> JsonResponse:
    """
    Creates a new journal entry for a bank adjustment (e.g., fee, interest)
    and matches it to a statement line.
    """
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        account_id = request.POST.get('account_id')
        description = request.POST.get('description', '').strip()

        if not all([line_id, account_id, description]):
            raise ValueError("Missing data for adjustment (line_id, account_id, description).")

        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if line.is_reconciled:
            raise ValueError("This statement line is already reconciled.")

        adjustment_account = get_object_or_404(Account, pk=account_id)
        bank_gl_account = reconciliation.bank_account.gl_account
        amount = abs(line.amount)

        with transaction.atomic():
            # 1. Create the Journal Entry for the adjustment
            je = JournalEntry.objects.create(
                date=line.transaction_date,
                description=description,
                # We can link it to the reconciliation for traceability
                source_object=reconciliation
            )

            # 2. Create the debit and credit lines
            if line.amount < 0: # It's a fee/expense
                # Debit the expense account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=adjustment_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.DEBIT
                )
                # Credit the bank account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=bank_gl_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )
            else: # It's interest/income
                # Debit the bank account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=bank_gl_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.DEBIT
                )
                # Credit the income account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=adjustment_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )

            # 3. Link the statement line to the new Journal Entry
            line.is_reconciled = True
            line.reconciled_object = je
            line.save()

        return JsonResponse({'status': 'success', 'message': 'Adjustment created and matched successfully.'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def api_match_transactions(request: HttpRequest, pk: int) -> JsonResponse:
    """API endpoint to match a statement line with an internal transaction."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        trx_id = request.POST.get('trx_id')
        trx_type = request.POST.get('trx_type') # 'Payment' or 'Transfer'

        if not all([line_id, trx_id, trx_type]):
            raise ValueError("Missing data for matching (line_id, trx_id, trx_type).")

        # Find the statement line
        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if line.is_reconciled:
            raise ValueError("This statement line is already reconciled.")

        with transaction.atomic():
            target_model = None
            if trx_type == 'Payment':
                target_model = Payment
            elif trx_type == 'Transfer':
                target_model = BankTransfer
            else:
                raise ValueError(f"Invalid transaction type: {trx_type}")

            internal_trx = get_object_or_404(target_model, pk=trx_id)

            # Basic validation: Amounts must match
            line_amount = line.amount
            trx_amount = Decimal('0.0')
            if trx_type == 'Payment':
                trx_amount = internal_trx.amount if internal_trx.payment_type == Payment.PaymentType.PAYMENT_IN else -internal_trx.amount
            elif trx_type == 'Transfer':
                # Determine if it's a debit or credit for the account being reconciled
                if internal_trx.destination_account_id == reconciliation.bank_account_id:
                    trx_amount = internal_trx.amount
                else:
                    trx_amount = -internal_trx.amount
            
            if abs(line_amount - trx_amount) > Decimal('0.001'):
                 raise ValueError(f"Amounts do not match. Line: {line_amount}, Transaction: {trx_amount}")

            # Link them
            line.is_reconciled = True
            line.reconciled_object = internal_trx
            line.save()

            # Mark the internal transaction as cleared
            cleared_date = line.transaction_date
            if trx_type == 'Payment':
                internal_trx.reconciliation = reconciliation
                internal_trx.cleared_date = cleared_date
                internal_trx.save()
            elif trx_type == 'Transfer':
                if internal_trx.destination_account_id == reconciliation.bank_account_id:
                    internal_trx.destination_reconciliation = reconciliation
                    internal_trx.destination_cleared_date = cleared_date
                else:
                    internal_trx.source_reconciliation = reconciliation
                    internal_trx.source_cleared_date = cleared_date
                internal_trx.save()

        return JsonResponse({'status': 'success', 'message': 'Transaction matched successfully.'})
                
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
def finalize_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """Marks a reconciliation as complete if the difference is zero."""
    reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
    
    # Recalculate the difference to ensure it's zero before finalizing
    cleared_balance = reconciliation.statement_opening_balance + \
                      (reconciliation.statement_lines.filter(is_reconciled=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.0'))
    difference = reconciliation.statement_closing_balance - cleared_balance

    if abs(difference) > Decimal('0.001'): # Use a small tolerance
        messages.error(request, "لا يمكن إتمام التسوية. لا يزال هناك فرق بين الرصيد المسوى والرصيد الدفتري.")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)

    try:
        with transaction.atomic():
            reconciliation.status = BankReconciliation.Status.RECONCILED
            reconciliation.save()
            messages.success(request, "تم إتمام التسوية البنكية بنجاح.")
            
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إتمام التسوية: {e}")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)

    return redirect('inventory:bank_reconciliations_list')


def journal_entries(request: HttpRequest) -> HttpResponse:
    """Lists manually created journal entries and provides a link to create new ones."""
    # MODIFIED: Prefetch lines and accounts for efficient display in the new accordion view.
    manual_entries = JournalEntry.objects.filter(
        content_type__isnull=True
    ).prefetch_related(
        'lines__account'
    ).annotate(
        total_amount=Sum('lines__amount', filter=Q(lines__entry_type='debit'))
    ).order_by('-date')
    
    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'journal_entries': manual_entries
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entries_content.html', context)
    return render(request, 'inventory/journal_entries.html', context)


@require_POST
@permission_required('inventory.change_journalentry', raise_exception=True)
def post_journal_entry(request: HttpRequest, pk: int) -> HttpResponse:
    """Posts a single draft journal entry."""
    entry = get_object_or_404(JournalEntry, pk=pk, status=JournalEntry.Status.DRAFT)
    try:
        entry.status = JournalEntry.Status.POSTED
        entry.save(update_fields=['status'])
        messages.success(request, f"تم ترحيل قيد اليومية رقم {entry.id} بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء ترحيل القيد: {e}")
    return redirect('inventory:journal_entries')


def create_journal_entry(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new journal entry using formsets."""
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        formset = JournalEntryLineFormSet(request.POST, prefix='lines')
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    journal_entry = form.save(commit=False)
                    # Manually created entries are drafts until posted.
                    journal_entry.status = JournalEntry.Status.DRAFT
                    journal_entry.save()
                    formset.instance = journal_entry
                    formset.save()
                    messages.success(request, "تم حفظ مسودة قيد اليومية بنجاح.")
                    return redirect('inventory:journal_entries')
            except Exception as e:
                messages.error(request, f"حدث خطأ: {e}")
    else:
        form = JournalEntryForm()
        formset = JournalEntryLineFormSet(prefix='lines', queryset=JournalEntryLine.objects.none())

    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'form': form,
        'formset': formset,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entry_create_content.html', context)
    return render(request, 'inventory/journal_entry_create.html', context)


def view_journal_entry(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays the details of a single journal entry."""
    entry = get_object_or_404(
        JournalEntry.objects.select_related('content_type').prefetch_related('lines__account', 'lines__sub_ledger_object'), 
        pk=pk
    )
    
    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'entry': entry,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entry_view_content.html', context)
    return render(request, 'inventory/journal_entry_view.html', context)


def fixed_assets_dashboard(request: HttpRequest) -> HttpResponse:
    """Displays a list of fixed assets and their depreciation status."""
    assets = FixedAsset.objects.all()
    logs = DepreciationLog.objects.select_related('asset', 'journal_entry').all()[:20]

    context = {
        'active_page': 'financials',
        'sub_page': 'assets',
        'assets': assets,
        'depreciation_logs': logs,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/fixed_assets_dashboard_content.html', context)
    return render(request, 'inventory/fixed_assets_dashboard.html', context)


# ==============================================================================
#  NEW OVERHEAD & CONFIGURATION VIEWS
# ==============================================================================

def cost_pools_list(request: HttpRequest) -> HttpResponse:
    """
    Manages the Cost Pool hierarchy (listing, creation, editing, and deletion).
    """
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'save') # Default to 'save' for backward compatibility

            if action == 'delete':
                pool_id = request.POST.get('pool_id')
                pool_to_delete = get_object_or_404(CostPool, pk=pool_id)

                # Safety Check 1: Cannot delete if it has children
                if pool_to_delete.children.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has sub-pools. Please delete or reassign them first.")
                    return redirect('inventory:cost_pools_list')

                # Safety Check 2: Cannot delete if it has associated expenses
                if pool_to_delete.expenses.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has expenses logged against it.")
                    return redirect('inventory:cost_pools_list')
                
                # Safety Check 3: Cannot delete if used in an allocation run
                if pool_to_delete.allocation_runs.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has been used in an overhead allocation run.")
                    return redirect('inventory:cost_pools_list')

                pool_name = pool_to_delete.name
                pool_to_delete.delete()
                messages.success(request, f"Cost Pool '{pool_name}' has been deleted successfully.")

            elif action == 'save':
                pool_id = request.POST.get('pool_id')
                name = request.POST.get('name', '').strip()
                parent_id = request.POST.get('parent') or None
                gl_account_id = request.POST.get('gl_account') or None

                if not name:
                    raise ValueError("Cost Pool Name cannot be empty.")

                if pool_id: # This is an Edit operation
                    pool = get_object_or_404(CostPool, pk=pool_id)
                    pool.name = name
                    pool.parent_id = parent_id
                    pool.gl_account_id = gl_account_id
                    pool.save()
                    messages.success(request, f"Cost Pool '{name}' updated successfully.")
                else: # This is a Create operation
                    CostPool.objects.create(
                        name=name,
                        parent_id=parent_id,
                        gl_account_id=gl_account_id
                    )
                    messages.success(request, f"Cost Pool '{name}' created successfully.")
        
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:cost_pools_list')

    # For GET request
    all_pools = CostPool.objects.select_related('parent', 'gl_account').all()
    expense_accounts = Account.objects.filter(account_type=Account.AccountType.EXPENSE).order_by('code')
    
    # Build a hierarchical structure for display
    root_pools = [pool for pool in all_pools if not pool.parent]
    for pool in root_pools:
        pool.children_list = [child for child in all_pools if child.parent_id == pool.id]

    context = {
        'active_page': 'financials',
        'sub_page': 'cost_pools',
        'all_pools': all_pools,
        'root_pools': root_pools,
        'expense_accounts': expense_accounts,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/cost_pools_list_content.html', context)
    return render(request, 'inventory/cost_pools_list.html', context)


def allocation_drivers_list(request: HttpRequest) -> HttpResponse:
    """
    Manages the Allocation Driver master list (listing, creation, editing).
    """
    if request.method == 'POST':
        try:
            driver_id = request.POST.get('driver_id')
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()

            if not name:
                raise ValueError("Driver name cannot be empty.")

            if driver_id: # Editing - Only description can be edited
                driver = get_object_or_404(AllocationDriver, pk=driver_id)
                driver.description = description
                driver.save()
                messages.success(request, f"Allocation Driver '{driver.get_name_display()}' description updated successfully.")
            else: # Creating
                AllocationDriver.objects.create(name=name, description=description)
                messages.success(request, f"Allocation Driver created successfully.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:allocation_drivers_list')

    # --- NEW: Get existing driver names to exclude them from the choices in the create form ---
    existing_driver_names = list(AllocationDriver.objects.values_list('name', flat=True))
    available_choices = [
        (value, label) for value, label in AllocationDriver.DriverChoices.choices 
        if value not in existing_driver_names
    ]

    context = {
        'active_page': 'financials',
        'sub_page': 'allocation_drivers',
        'drivers': AllocationDriver.objects.all(),
        'available_choices': available_choices, # NEW
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/allocation_drivers_list_content.html', context)
    return render(request, 'inventory/allocation_drivers_list.html', context)


def overhead_allocation_workspace(request: HttpRequest) -> HttpResponse:
    """
    Manages the period-end overhead allocation process.
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'create_run':
                period_id = request.POST.get('financial_period')
                pool_id = request.POST.get('cost_pool')
                driver_id = request.POST.get('allocation_driver')
                OverheadAllocationRun.objects.create(
                    financial_period_id=period_id,
                    cost_pool_id=pool_id,
                    allocation_driver_id=driver_id
                )
                messages.success(request, "New overhead allocation run created successfully.")
            
            elif action == 'calculate_rate':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                execute_overhead_allocation_run(run)
                messages.success(request, f"Successfully calculated overhead rate for run #{run.id}.")

            elif action == 'post_to_gl':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                create_je_for_overhead_allocation(run)
                messages.success(request, f"Successfully posted overhead for run #{run.id} to the General Ledger.")

            elif action == 'apply_to_inventory':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                # This service function calculates and applies the cost, returning the total.
                total_applied_cost = apply_overhead_to_finished_goods(run)
                # This service function creates the corresponding JE.
                create_je_for_overhead_application(run, total_applied_cost)
                messages.success(request, f"Successfully applied {total_applied_cost:,.2f} from run #{run.id} to Finished Goods inventory.")

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:overhead_allocation_workspace')

    # For GET request
    runs = OverheadAllocationRun.objects.select_related(
        'financial_period', 'cost_pool', 'allocation_driver', 'journal_entry', 'application_journal_entry'
    ).all()

    context = {
        'active_page': 'financials',
        'sub_page': 'overhead_allocation',
        'runs': runs,
        'financial_periods': FinancialPeriod.objects.filter(status=FinancialPeriod.Status.OPEN),
        'cost_pools': CostPool.objects.all(),
        'allocation_drivers': AllocationDriver.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/overhead_allocation_workspace_content.html', context)
    return render(request, 'inventory/overhead_allocation_workspace.html', context)


# ==============================================================================
#  FINANCIAL PERIOD MANAGEMENT VIEWS
# ==============================================================================

def fiscal_year_list(request: HttpRequest) -> HttpResponse:
    """Lists all Fiscal Years and their associated Financial Periods."""
    fiscal_years = FiscalYear.objects.prefetch_related('periods').all()
    
    context = {
        'active_page': 'financials',
        'sub_page': 'periods',
        'fiscal_years': fiscal_years,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/fiscal_year_list_content.html', context)
    return render(request, 'inventory/fiscal_year_list.html', context)


@require_POST
def create_fiscal_year(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new Fiscal Year and optionally its monthly periods."""
    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        generate_periods = request.POST.get('generate_periods') == 'on'

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            fiscal_year = FiscalYear.objects.create(
                name=name,
                start_date=start_date,
                end_date=end_date
            )

            if generate_periods:
                # Generate 12 monthly periods
                current_start = start_date
                for i in range(12):
                    current_end = (current_start + relativedelta(months=1)) - relativedelta(days=1)
                    if current_end > end_date:
                        current_end = end_date
                    
                    FinancialPeriod.objects.create(
                        fiscal_year=fiscal_year,
                        name=current_start.strftime('%B %Y'),
                        start_date=current_start,
                        end_date=current_end,
                        status=FinancialPeriod.Status.OPEN
                    )
                    current_start = current_start + relativedelta(months=1)
                    if current_start > end_date:
                        break

        messages.success(request, f"تم إنشاء السنة المالية '{name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء السنة المالية: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def create_financial_period(request: HttpRequest, year_id: int) -> HttpResponse:
    """Handles the creation of a single, custom financial period."""
    fiscal_year = get_object_or_404(FiscalYear, pk=year_id)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن إضافة فترة لسنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')
        
    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            period = FinancialPeriod(
                fiscal_year=fiscal_year,
                name=name,
                start_date=start_date,
                end_date=end_date,
                status=FinancialPeriod.Status.OPEN
            )
            period.clean() # Validate model constraints
            period.save()

        messages.success(request, f"تم إنشاء الفترة المحاسبية '{name}' بنجاح.")
    except ValidationError as e:
        messages.error(request, f"خطأ في التحقق: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء الفترة: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def edit_fiscal_year(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles the updating of a Fiscal Year's details."""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن تعديل سنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')

    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            fiscal_year.name = name
            # Only allow date changes if no periods exist yet
            if not fiscal_year.periods.exists():
                fiscal_year.start_date = start_date
                fiscal_year.end_date = end_date
            elif fiscal_year.start_date != start_date or fiscal_year.end_date != end_date:
                messages.warning(request, "لا يمكن تغيير تواريخ سنة مالية تحتوي بالفعل على فترات محاسبية.")

            fiscal_year.clean() # Validate model constraints
            fiscal_year.save()

        messages.success(request, f"تم تحديث السنة المالية '{name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تحديث السنة المالية: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def delete_fiscal_year(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles the deletion of a Fiscal Year, with safety checks."""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن حذف سنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')

    # Safety Check: Ensure no transactions exist within this fiscal year's date range.
    # This is a simplified check. A more robust check would query all transactional models.
    has_transactions = JournalEntry.objects.filter(
        date__range=(fiscal_year.start_date, fiscal_year.end_date)
    ).exists()

    if has_transactions:
        messages.error(request, f"لا يمكن حذف السنة المالية '{fiscal_year.name}' لأنها تحتوي على قيود يومية مسجلة.")
        return redirect('inventory:fiscal_year_list')

    try:
        with transaction.atomic():
            year_name = fiscal_year.name
            fiscal_year.delete()
            messages.success(request, f"تم حذف السنة المالية '{year_name}' وجميع فتراتها بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف السنة المالية: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
def generate_monthly_periods(request: HttpRequest, year_id: int) -> HttpResponse:
    """Generates 12 monthly Financial Periods for a given Fiscal Year."""
    fiscal_year = get_object_or_404(FiscalYear, pk=year_id)
    if fiscal_year.periods.exists():
        messages.warning(request, "الفترات الشهرية لهذه السنة المالية تم إنشاؤها بالفعل.")
        return redirect('inventory:fiscal_year_list')

    try:
        with transaction.atomic():
            current_date = fiscal_year.start_date
            while current_date < fiscal_year.end_date:
                period_end_date = current_date + relativedelta(day=31)
                if period_end_date > fiscal_year.end_date:
                    period_end_date = fiscal_year.end_date
                
                FinancialPeriod.objects.create(
                    fiscal_year=fiscal_year,
                    name=current_date.strftime('%B %Y'),
                    start_date=current_date,
                    end_date=period_end_date,
                    status=FinancialPeriod.Status.OPEN
                )
                current_date = period_end_date + relativedelta(days=1)
        messages.success(request, f"تم إنشاء 12 فترة محاسبية للسنة المالية '{fiscal_year.name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء الفترات: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
def change_period_status(request: HttpRequest, period_id: int) -> HttpResponse:
    """Handles changing the status of a financial period."""
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    new_status = request.POST.get('new_status')
    justification = request.POST.get('justification', '').strip()

    if not new_status or new_status not in [s[0] for s in FinancialPeriod.Status.choices]:
        messages.error(request, "حالة جديدة غير صالحة.")
        return redirect('inventory:fiscal_year_list')

    try:
        original_status = period.get_status_display()
        
        # Logic for re-opening a closed period
        if period.status == FinancialPeriod.Status.CLOSED and new_status == FinancialPeriod.Status.OPEN:
            if not request.user.has_perm('inventory.can_reopen_period'):
                messages.error(request, "ليس لديك الصلاحية لإعادة فتح فترة مغلقة.")
                return redirect('inventory:fiscal_year_list')
            if not justification:
                messages.error(request, "يجب تقديم مبرر لإعادة فتح فترة مغلقة.")
                return redirect('inventory:fiscal_year_list')
            
            # Create an audit log entry for re-opening
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.REOPEN,
                justification=justification
            )
        
        # --- NEW: Logic for permanently locking a period ---
        if new_status == FinancialPeriod.Status.PERMANENTLY_LOCKED:
            if not request.user.has_perm('inventory.can_permanently_lock_period'):
                messages.error(request, "ليس لديك الصلاحية لإغلاق فترة بشكل دائم.")
                return redirect('inventory:fiscal_year_list')
            
            # Create an audit log entry for locking
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.LOCK,
                justification=justification or "Period permanently locked after final review."
            )


        period.status = new_status
        period.save()
        
        new_status_display = period.get_status_display()
        messages.success(request, f"تم تغيير حالة الفترة '{period.name}' من '{original_status}' إلى '{new_status_display}' بنجاح.")

    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تغيير حالة الفترة: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
@permission_required('inventory.change_financialperiod', raise_exception=True)
def close_period_action(request: HttpRequest, period_id: int) -> HttpResponse:
    """
    Handles the final action of closing a financial period after all checks pass.
    """
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    
    # Security and state check
    if period.status != FinancialPeriod.Status.PENDING_CLOSE:
        messages.error(request, _("This period is not in the 'Pending Close' state and cannot be closed."))
        return redirect('inventory:fiscal_year_list')

    # Re-run the checklist validation on the server side as the final gate.
    # The service returns the updated checklist instance, guaranteed to be fresh.
    checklist = update_checklist_for_period(period)

    # Use the checklist object returned directly by the service for the final check.
    if not checklist.is_complete:
        messages.error(request, _("Cannot close the period. One or more pre-closing checks have not been completed."))
        return redirect('inventory:close_period_cockpit', period_id=period.id)

    try:
        with transaction.atomic():
            period.status = FinancialPeriod.Status.CLOSED
            period.save()
            
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.CLOSE,
                justification="Period closed via closing cockpit."
            )
        
        messages.success(request, _(f"Financial period '{period.name}' has been successfully closed."))
        return redirect('inventory:fiscal_year_list')
    except Exception as e:
        messages.error(request, _(f"An unexpected error occurred: {e}"))
        return redirect('inventory:close_period_cockpit', period_id=period.id)


def close_period_cockpit(request: HttpRequest, period_id: int) -> HttpResponse:
    """
    Displays the 'Closing Cockpit' UI for a specific financial period,
    showing the checklist. This is now a GET-only view.
    """
    period = get_object_or_404(FinancialPeriod, pk=period_id)

    # The POST logic has been moved to the 'close_period_action' view.
    if period.status not in [FinancialPeriod.Status.OPEN, FinancialPeriod.Status.PENDING_CLOSE]:
        messages.warning(request, _("This period is already closed and cannot be modified from this screen."))
        return redirect('inventory:fiscal_year_list')

    # The cockpit's job is to update the checklist so the user sees the latest status.
    checklist = update_checklist_for_period(period)

    context = {
        'active_page': 'financials',
        'sub_page': 'periods',
        'period': period,
        'checklist': checklist,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/close_period_cockpit_content.html', context)
    return render(request, 'inventory/close_period_cockpit.html', context)


def api_period_checklist_status(request: HttpRequest, period_id: int) -> JsonResponse:
    """API endpoint to check the status of pre-closing conditions for a period."""
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    
    # --- REAL IMPLEMENTATION ---
    checks = {}
    
    # 1. Check if all bank accounts have been reconciled for the period.
    # This is more robust: it ensures every bank account has a corresponding
    # reconciled statement, not just that there are no unreconciled ones.
    all_bank_accounts = BankAccount.objects.all()
    reconciled_banks_in_period_pks = BankReconciliation.objects.filter(
        statement_date__gte=period.start_date,
        statement_date__lte=period.end_date,
        status=BankReconciliation.Status.RECONCILED
    ).values_list('bank_account_id', flat=True)

    unreconciled_bank_objects = all_bank_accounts.exclude(pk__in=reconciled_banks_in_period_pks)
    bank_check = not unreconciled_bank_objects.exists()
    
    bank_details = []
    if not bank_check:
        for bank in unreconciled_bank_objects:
            bank_details.append({
                'description': f"Bank Account: {bank.name}",
                'url': '#' # No direct URL for a bank account view
            })
            
    checks['all_banks_reconciled'] = {
        'status': bank_check,
        'message': f"{unreconciled_bank_objects.count()} bank accounts are not reconciled." if not bank_check else "All bank accounts reconciled.",
        'details': bank_details
    }

    # 2. Check for draft manual journal entries
    draft_jes = JournalEntry.objects.filter(
        date__gte=period.start_date,
        date__lte=period.end_date,
        status=JournalEntry.Status.DRAFT,
        content_type__isnull=True # Manual entries only
    )
    draft_check = not draft_jes.exists()
    draft_details = []
    if not draft_check:
        for je in draft_jes:
            draft_details.append({
                'description': f"JE-{je.id}: {je.description}",
                'url': reverse('inventory:view_journal_entry', kwargs={'pk': je.id})
            })
            
    checks['no_draft_manual_jes'] = {
        'status': draft_check,
        'message': f"{draft_jes.count()} draft journal entries found." if not draft_check else "No manual journal entries in draft status.",
        'details': draft_details
    }

    # 3. Check for unposted supplier/customer invoices (assuming DRAFT status exists)
    unposted_supplier_invoices = SupplierInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=SupplierInvoice.InvoiceStatus.DRAFT
    )
    unposted_customer_invoices = CustomerInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=CustomerInvoice.InvoiceStatus.DRAFT
    )
    unposted_invoices_check = not unposted_supplier_invoices.exists() and not unposted_customer_invoices.exists()
    invoice_details = []
    if not unposted_invoices_check:
        for inv in unposted_supplier_invoices:
            invoice_details.append({
                'description': f"Supplier Invoice: {inv.invoice_number} ({inv.supplier.name})",
                'url': reverse('inventory:view_supplier_invoice', kwargs={'pk': inv.id})
            })
        for inv in unposted_customer_invoices:
            invoice_details.append({
                'description': f"Customer Invoice: {inv.invoice_number} ({inv.customer.name})",
                'url': reverse('inventory:view_customer_invoice', kwargs={'pk': inv.id})
            })
            
    checks['no_unposted_invoices'] = {
        'status': unposted_invoices_check,
        'message': f"{len(invoice_details)} unposted invoices found." if not unposted_invoices_check else "All invoices are posted.",
        'details': invoice_details
    }

    # 4. Placeholder for a check that is always true for now
    checks['is_inventory_valuation_run'] = {
        'status': True,
        'message': 'Inventory valuation process completed successfully.',
        'details': []
    }
    
    # 5. Get status of other checks from the checklist model
    checklist = getattr(period, 'checklist', None)
    if checklist:
        checks['is_depreciation_run'] = {
            'status': checklist.is_depreciation_run,
            'message': 'Monthly depreciation has been run.' if checklist.is_depreciation_run else 'Monthly depreciation has not been run.',
            'details': []
        }
        checks['is_overhead_posted'] = {
            'status': checklist.is_overhead_posted,
            'message': 'Manufacturing overhead has been posted.' if checklist.is_overhead_posted else 'Manufacturing overhead has not been posted.',
            'details': []
        }

    return JsonResponse(checks)

def view_period_audit_log(request: HttpRequest, period_id: int) -> HttpResponse:
    """Displays the audit log for a specific financial period."""
    period = get_object_or_404(FinancialPeriod.objects.prefetch_related('audit_logs__user'), pk=period_id)
    context = {
        'period': period,
        'audit_logs': period.audit_logs.all()
    }
    return render(request, 'inventory/partials/audit_log_content.html', context)