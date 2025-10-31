# gipcco_project/inventory/views/financials/ar_views.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ...models import (
    BankAccount, Customer, CustomerInvoice, FinishedProductDispatch, CustomerInvoiceItem, CustomerPaymentApplication, SalesOrder, Payment
)

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
