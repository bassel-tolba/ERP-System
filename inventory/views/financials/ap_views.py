# gipcco_project/inventory/views/financials/ap_views.py

from datetime import datetime
from decimal import Decimal
from django.utils.translation import gettext_lazy as _

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum, F, DecimalField
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
import logging

from ...models import (
    Company, SupplierInvoice, SupplierInvoiceItem, InventoryLog,
    Payment, PaymentApplication, BankAccount, LandedCostType, LandedCostInvoice, PurchaseOrder, ExpenseLog,
    LandedCostInvoiceItem
)
from ...services import accounting_service, purchasing_service

logger = logging.getLogger(__name__)

# --- Landed Cost Invoice Views ---

def landed_cost_invoices(request: HttpRequest) -> HttpResponse:
    """Lists all landed cost invoices with filtering."""
    vendor_id = request.GET.get('vendor')
    status = request.GET.get('status')
    
    invoices = LandedCostInvoice.objects.select_related('vendor').all()
    if vendor_id:
        invoices = invoices.filter(vendor_id=vendor_id)
    if status:
        invoices = invoices.filter(status=status)

    context = {
        'active_page': 'financials',
        'sub_page': 'landed_cost_invoices',
        'invoices': invoices,
        'vendors': Company.objects.all(), # Assuming vendors are also Companies
        'statuses': LandedCostInvoice.Status.choices,
        'selected_vendor': int(vendor_id) if vendor_id else None,
        'selected_status': status,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/landed_cost_invoices_content.html', context)
    return render(request, 'inventory/landed_cost_invoices.html', context)


def create_landed_cost_invoice(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new DRAFT landed cost invoice."""
    if request.method == 'POST':
        try:
            vendor_id = request.POST.get('vendor_id')
            invoice_number = request.POST.get('invoice_number')
            invoice_date = request.POST.get('invoice_date')
            po_id = request.POST.get('purchase_order_id')

            if not all([vendor_id, invoice_number, invoice_date]):
                raise ValidationError(_("Vendor, Invoice Number, and Date are required."))

            with transaction.atomic():
                invoice = LandedCostInvoice.objects.create(
                    vendor_id=vendor_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    total_amount=Decimal('0.000'), # Start with zero
                    purchase_order_id=po_id if po_id else None,
                    status=LandedCostInvoice.Status.DRAFT
                )
                messages.success(request, f"Landed Cost Invoice {invoice.invoice_number} created. Please add line items.")
                return redirect('inventory:view_landed_cost_invoice', pk=invoice.pk)

        except (ValidationError, ValueError) as e:
            messages.error(request, f"Data Error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating landed cost invoice: {e}", exc_info=True)
            messages.error(request, f"An unexpected error occurred: {e}")
            return redirect('inventory:create_landed_cost_invoice')

    today = timezone.now().date()
    context = {
        'active_page': 'financials',
        'sub_page': 'landed_cost_invoices',
        'vendors': Company.objects.all(),
        'purchase_orders': PurchaseOrder.objects.filter(status__in=['partially_received', 'completed']).order_by('-order_date'),
        'today_date': today.strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/landed_cost_invoice_create_content.html', context)
    return render(request, 'inventory/landed_cost_invoice_create.html', context)


def view_landed_cost_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays landed cost invoice details and allows adding items."""
    invoice = get_object_or_404(LandedCostInvoice.objects.select_related('vendor', 'purchase_order'), pk=pk)
    
    context = {
        'active_page': 'financials',
        'sub_page': 'landed_cost_invoices',
        'invoice': invoice,
        'items': invoice.items.select_related('cost_type').all(),
        'bank_accounts': BankAccount.objects.all(),
        'cost_types': LandedCostType.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/landed_cost_invoice_view_content.html', context)
    return render(request, 'inventory/landed_cost_invoice_view.html', context)


@require_POST
@permission_required('inventory.add_landedcostinvoiceitem', raise_exception=True)
def add_landed_cost_invoice_item(request: HttpRequest, pk: int) -> HttpResponse:
    """Adds a line item to a draft landed cost invoice."""
    invoice = get_object_or_404(LandedCostInvoice, pk=pk, status=LandedCostInvoice.Status.DRAFT)
    try:
        cost_type_id = request.POST.get('cost_type_id')
        amount_str = request.POST.get('amount')

        if not all([cost_type_id, amount_str]):
            raise ValueError(_("Cost Type and Amount are required."))

        with transaction.atomic():
            LandedCostInvoiceItem.objects.create(
                landed_cost_invoice=invoice,
                cost_type_id=cost_type_id,
                amount=Decimal(amount_str)
            )
            # Recalculate the total amount on the invoice header
            invoice.total_amount = invoice.items.aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
            invoice.save()
            messages.success(request, "Landed cost item added successfully.")

    except Exception as e:
        logger.exception(f"Error adding item to landed cost invoice ID {pk}")
        messages.error(request, f"An error occurred: {e}")
    
    return redirect('inventory:view_landed_cost_invoice', pk=pk)


@require_POST
@permission_required('inventory.change_landedcostinvoice', raise_exception=True)
def post_landed_cost_invoice_view(request: HttpRequest, pk: int) -> HttpResponse:
    """View to handle the action of posting a single draft landed cost invoice."""
    invoice = get_object_or_404(LandedCostInvoice, pk=pk)
    try:
        purchasing_service.post_landed_cost_invoice(invoice, request.user)
        messages.success(request, f"Landed Cost Invoice {invoice.invoice_number} posted successfully.")
    except Exception as e:
        logger.exception(f"Error posting landed cost invoice ID {pk}")
        messages.error(request, f"An error occurred while posting: {e}")
    
    return redirect('inventory:view_landed_cost_invoice', pk=pk)


@permission_required('inventory.change_landedcostinvoice', raise_exception=True)
def allocate_landed_cost_invoice_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    The "Wizard" to allocate the variance from a posted Landed Cost Invoice
    to the original receipts.
    """
    invoice = get_object_or_404(LandedCostInvoice, pk=pk)

    # Guard: Can only allocate if status is correct
    if invoice.status != LandedCostInvoice.Status.AWAITING_ALLOCATION:
        messages.error(request, _("This invoice is not awaiting allocation."))
        return redirect('inventory:view_landed_cost_invoice', pk=pk)

    if request.method == 'POST':
        try:
            # Parse the form data: list of {receipt_id, amount}
            allocation_data = []
            receipt_ids = request.POST.getlist('receipt_id')
            amounts = request.POST.getlist('allocation_amount')

            total_allocated = Decimal('0.0')
            
            for r_id, amt in zip(receipt_ids, amounts):
                if amt and Decimal(amt) != 0:
                    allocation_data.append({
                        'receipt_log_id': int(r_id),
                        'amount': Decimal(amt)
                    })
                    total_allocated += Decimal(amt)

            # Call the service
            purchasing_service.allocate_landed_costs_from_invoice(
                landed_cost_invoice_id=invoice.pk,
                allocation_data=allocation_data,
                user=request.user
            )
            messages.success(request, _("Landed costs allocated successfully."))
            return redirect('inventory:view_landed_cost_invoice', pk=pk)

        except ValidationError as e:
            messages.error(request, str(e))
        except Exception as e:
            logger.exception(f"Error allocating invoice {pk}")
            messages.error(request, _("An unexpected error occurred."))

    # --- GET: Prepare the Context for the Wizard ---
    # Find eligible receipts (Logs linked to the PO)
    related_receipts = InventoryLog.objects.filter(
        po_item__purchase_order=invoice.purchase_order,
        status=InventoryLog.Status.RELEASED
    ).annotate(
        total_value=F('quantity') * F('costing_unit_price')
    )

    # Calculate the balance sitting in the clearing account
    # This is (Invoice Total - Total Originally Accrued on Receipts)
    all_po_receipts = InventoryLog.objects.filter(po_item__purchase_order=invoice.purchase_order)
    total_accrued = all_po_receipts.aggregate(
        total=Sum(F('landed_cost_component') * F('quantity'), output_field=DecimalField())
    )['total'] or Decimal('0.0')
    
    clearing_balance = invoice.total_amount - total_accrued

    context = {
        'invoice': invoice,
        'receipts': related_receipts,
        'clearing_balance': clearing_balance,
    }
    return render(request, 'inventory/landed_cost_allocation.html', context)


@require_POST
@permission_required('inventory.add_payment', raise_exception=True)
def apply_payment_to_landed_cost_invoice_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles applying a payment to a landed cost invoice."""
    try:
        bank_account_id = request.POST.get('bank_account')
        amount_str = request.POST.get('amount')
        payment_date = request.POST.get('payment_date')
        description = request.POST.get('description')

        if not all([bank_account_id, amount_str, payment_date]):
            raise ValueError(_("Bank account, amount, and date are required."))

        purchasing_service.apply_payment_to_landed_cost_invoice(
            user=request.user,
            invoice_id=pk,
            bank_account_id=int(bank_account_id),
            amount=Decimal(amount_str),
            payment_date=datetime.strptime(payment_date, '%Y-%m-%d').date(),
            description=description
        )
        messages.success(request, _("Payment applied successfully."))
    except Exception as e:
        logger.exception(f"Error paying LC invoice {pk}")
        messages.error(request, str(e))
    
    return redirect('inventory:view_landed_cost_invoice', pk=pk)


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
    Handles the creation of a new DRAFT supplier invoice from unbilled receipts.
    The invoice is saved in a draft state and must be posted separately to affect the GL.
    """
    if request.method == 'POST':
        try:
            supplier_id = request.POST.get('supplier')
            invoice_number = request.POST.get('invoice_number').strip()
            invoice_date_str = request.POST.get('invoice_date')
            due_date_str = request.POST.get('due_date')
            
            # --- NEW: Get actual invoice amounts from user input ---
            actual_subtotal_str = request.POST.get('actual_subtotal')
            actual_vat_str = request.POST.get('actual_vat')
            
            source_type = request.POST.get('source_type', 'receipts')

            if not all([supplier_id, invoice_number, invoice_date_str, due_date_str, actual_subtotal_str, actual_vat_str]):
                messages.error(request, "يرجى تعبئة جميع الحقول الأساسية، بما في ذلك الإجمالي الفرعي والضريبة الفعلية من الفاتورة.")
                return redirect('inventory:create_supplier_invoice')

            if SupplierInvoice.objects.filter(supplier_id=supplier_id, invoice_number=invoice_number).exists():
                messages.error(request, f"فاتورة بنفس الرقم '{invoice_number}' موجودة بالفعل لهذا المورد.")
                return redirect('inventory:create_supplier_invoice')

            invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date()
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            actual_subtotal = Decimal(actual_subtotal_str)
            actual_vat = Decimal(actual_vat_str)

            # The expense service workflow is complex and will be adapted in a future step.
            if source_type == 'expenses':
                messages.error(request, "إنشاء الفواتير من المصروفات قيد التطوير حاليًا.")
                return redirect('inventory:create_supplier_invoice')
            
            receipt_ids = request.POST.getlist('item_ids')
            if not receipt_ids:
                messages.error(request, "يرجى اختيار فاتورة استلام واحدة على الأقل.")
                return redirect('inventory:create_supplier_invoice')

            with transaction.atomic():
                # --- MODIFIED: Create a DRAFT invoice with actual values ---
                invoice = SupplierInvoice.objects.create(
                    supplier_id=supplier_id,
                    invoice_number=invoice_number,
                    invoice_date=invoice_date,
                    due_date=due_date,
                    actual_subtotal=actual_subtotal,
                    actual_vat=actual_vat,
                    status=SupplierInvoice.InvoiceStatus.DRAFT
                )
                
                receipts = InventoryLog.objects.filter(id__in=receipt_ids, company_id=supplier_id)
                total_receipt_amount = Decimal('0.0')
                
                items_to_create = []
                for receipt in receipts:
                    receipt_total = (receipt.base_unit_price * Decimal(str(receipt.quantity))) + receipt.vat_amount
                    items_to_create.append(
                        SupplierInvoiceItem(invoice=invoice, receipt=receipt, amount=receipt_total)
                    )
                    total_receipt_amount += receipt_total
                
                SupplierInvoiceItem.objects.bulk_create(items_to_create)
                
                # Set the total_amount to the sum of receipts for reference while in draft
                invoice.total_amount = total_receipt_amount
                invoice.save()

            messages.success(request, f"تم إنشاء مسودة فاتورة المورد رقم {invoice.invoice_number} بنجاح. يجب ترحيلها لتؤثر على الحسابات.")
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
        'landed_cost_types': LandedCostType.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/supplier_invoice_view_content.html', context)
    return render(request, 'inventory/supplier_invoice_view.html', context)


@require_POST
@permission_required('inventory.change_supplierinvoice', raise_exception=True)
def post_supplier_invoice_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    View to handle the action of posting a single draft supplier invoice.
    """
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    try:
        # The service function contains all the business logic
        accounting_service.post_supplier_invoice(invoice)
        messages.success(request, f"تم ترحيل فاتورة المورد رقم {invoice.invoice_number} إلى الحسابات بنجاح.")
    except Exception as e:
        logger.exception(f"Error posting supplier invoice ID {pk}")
        messages.error(request, f"حدث خطأ أثناء ترحيل الفاتورة: {e}")
    
    return redirect('inventory:view_supplier_invoice', pk=pk)


@require_POST
@permission_required('inventory.change_supplierinvoice', raise_exception=True)
def allocate_landed_costs_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    View to handle adding a landed cost item and then triggering the allocation service.
    """
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    try:
        cost_type_id = request.POST.get('cost_type')
        amount_str = request.POST.get('amount')

        if not all([cost_type_id, amount_str]):
            raise ValueError(_("Cost Type and Amount are required."))

        # 1. Create the Landed Cost object
        amount = Decimal(amount_str)
        invoice.landed_costs.create(cost_type_id=cost_type_id, amount=amount)
        messages.success(request, f"Landed cost item added successfully. Allocating costs...")

        # 2. Trigger the allocation service
        accounting_service.allocate_landed_costs(invoice)
        messages.success(request, "Landed costs allocated to receipt items successfully.")

    except Exception as e:
        logger.exception(f"Error allocating landed costs for invoice ID {pk}")
        messages.error(request, f"An error occurred: {e}")
    
    return redirect('inventory:view_supplier_invoice', pk=pk)


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
    ).order_by('-release_timestamp')

    data = {
        'receipts': [
            {
                'id': r.id,
                'release_date': r.release_timestamp.strftime('%Y-%m-%d'),
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
