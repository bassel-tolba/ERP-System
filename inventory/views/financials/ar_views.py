# gipcco_project/inventory/views/financials/ar_views.py

import json
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, F, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.template.loader import render_to_string
from weasyprint import HTML
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from ...models import (
    BankAccount, Customer, CustomerInvoice, FinishedProductDispatch, CustomerInvoiceItem, CustomerPaymentApplication, SalesOrder, Payment, CustomerCreditMemo
    
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
    """Handles creating a new customer invoice from uninvoiced dispatches for a customer."""
    if request.method == 'POST':
        customer_id = request.POST.get('customer')
        invoice_number = request.POST.get('invoice_number').strip()
        invoice_date_str = request.POST.get('invoice_date')
        due_date_str = request.POST.get('due_date')
        dispatch_ids = request.POST.getlist('dispatch_ids')

        if not all([customer_id, invoice_number, invoice_date_str, due_date_str, dispatch_ids]):
            messages.error(request, "يرجى تعبئة جميع الحقول واختيار عملية صرف واحدة على الأقل.")
            return redirect('inventory:create_customer_invoice')

        customer = get_object_or_404(Customer, pk=customer_id)
        if CustomerInvoice.objects.filter(customer=customer, invoice_number=invoice_number).exists():
            messages.error(request, f"فاتورة بنفس الرقم '{invoice_number}' موجودة بالفعل لهذا العميل.")
            return redirect('inventory:create_customer_invoice')

        try:
            with transaction.atomic():
                dispatches = FinishedProductDispatch.objects.filter(
                    id__in=dispatch_ids, sales_order_item__sales_order__customer_id=customer_id
                ).select_related('sales_order_item__sales_order')

                if len(dispatch_ids) != dispatches.count():
                    raise ValueError("One or more selected dispatches could not be found or do not belong to the selected customer.")

                # Determine if all dispatches are from the same sales order to link it
                sales_order_ids = {d.sales_order_item.sales_order.id for d in dispatches}
                linked_sales_order = dispatches[0].sales_order_item.sales_order if len(sales_order_ids) == 1 else None

                invoice = CustomerInvoice.objects.create(
                    customer=customer,
                    sales_order=linked_sales_order,
                    invoice_number=invoice_number,
                    invoice_date=datetime.strptime(invoice_date_str, '%Y-%m-%d').date(),
                    due_date=datetime.strptime(due_date_str, '%Y-%m-%d').date(),
                    status=CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT
                )

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
        'customers': Customer.objects.all(),
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


# --- NEW: Customer Payment Views ---

def customer_payments_list(request: HttpRequest) -> HttpResponse:
    """Lists all incoming customer payments with filtering."""
    customer_id = request.GET.get('customer')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    payments = Payment.objects.filter(payment_type=Payment.PaymentType.PAYMENT_IN).select_related('customer', 'bank_account')

    if customer_id:
        payments = payments.filter(customer_id=customer_id)
    if start_date_str and end_date_str:
        payments = payments.filter(payment_date__range=[start_date_str, end_date_str])

    context = {
        'active_page': 'financials',
        'sub_page': 'customer_payments',
        'payments': payments,
        'customers': Customer.objects.all(),
        'selected_customer': int(customer_id) if customer_id else None,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customer_payments_list_content.html', context)
    return render(request, 'inventory/customer_payments_list.html', context)


def view_customer_payment(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays the details of a single customer payment and its applications."""
    payment = get_object_or_404(
        Payment.objects.select_related('customer', 'bank_account'),
        pk=pk,
        payment_type=Payment.PaymentType.PAYMENT_IN
    )
    applications = payment.customer_applications.select_related('invoice').all()

    context = {
        'active_page': 'financials',
        'sub_page': 'customer_payments',
        'payment': payment,
        'applications': applications,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customer_payment_view_content.html', context)
    return render(request, 'inventory/customer_payment_view.html', context)


def view_customer_payment_pdf(request: HttpRequest, pk: int) -> HttpResponse:
    """Generates a PDF receipt voucher for a customer payment."""
    payment = get_object_or_404(
        Payment.objects.select_related('customer', 'bank_account'),
        pk=pk,
        payment_type=Payment.PaymentType.PAYMENT_IN
    )
    applications = payment.customer_applications.select_related('invoice').all()

    context = {
        'payment': payment,
        'applications': applications,
    }

    html_string = render_to_string('inventory/pdfs/customer_payment_voucher_pdf.html', context)
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    customer_name = payment.customer.name.replace(" ", "_")
    filename = f"Receipt_Voucher_{payment.pk}_{customer_name}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    return response


# --- A/R API Views ---

def api_get_uninvoiced_dispatches(request: HttpRequest, customer_id: int) -> JsonResponse:
    """Returns dispatches for a customer that are not yet on an invoice."""
    dispatches = FinishedProductDispatch.objects.filter(
        sales_order_item__sales_order__customer_id=customer_id,
        invoice_item__isnull=True
    ).select_related(
        'sales_order_item__sales_order',
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
            'product_name': f"{final_product.name} (SO: {so_item.sales_order.so_number})",
            'quantity': d.quantity,
            'unit': final_product.unit,
            'total_value': str(total_value.quantize(Decimal('0.001')))
        })

    return JsonResponse({'dispatches': data})



# --- NEW: A/R Workbench ---

@login_required
def ar_cash_application_workbench(request: HttpRequest) -> HttpResponse:
    """
    Provides a UI to apply unapplied payments and credit memos to open invoices
    for a specific customer.
    """
    from ...services import ar_service

    if request.method == 'POST':
        try:
            customer_id = request.POST.get('customer_id')
            application_date_str = request.POST.get('application_date')
            applications_json = request.POST.get('applications_json')

            if not all([customer_id, application_date_str, applications_json]):
                raise ValueError("Missing required data for application.")

            customer = get_object_or_404(Customer, pk=customer_id)
            application_date = datetime.strptime(application_date_str, '%Y-%m-%d').date()
            
            raw_applications = json.loads(applications_json)
            # Convert amounts back to Decimal
            applications = [
                {**app, 'amount': Decimal(app['amount'])}
                for app in raw_applications
            ]

            ar_service.apply_customer_payments_and_credits(
                customer=customer,
                application_date=application_date,
                applications=applications
            )
            messages.success(request, "تم تطبيق الدفعات والخصومات بنجاح.")
            return redirect('inventory:ar_cash_application_workbench')

        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            return redirect('inventory:ar_cash_application_workbench')

    context = {
        'active_page': 'financials',
        'sub_page': 'ar_workbench',
        'customers': Customer.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/ar_workbench_content.html', context)
    return render(request, 'inventory/ar_workbench.html', context)


@login_required
def api_get_customer_open_items(request: HttpRequest, customer_id: int) -> JsonResponse:
    """
    Returns all open credit items (unapplied payments, credit memos) and
    open debit items (invoices with a balance due) for a customer.
    """
    customer = get_object_or_404(Customer, pk=customer_id)

    # Available Credits (Sources)
    unapplied_payments = Payment.objects.filter(
        customer=customer, payment_type=Payment.PaymentType.PAYMENT_IN
    ).annotate(
        total_applied=Coalesce(Sum('customer_applications__amount_applied'), Value(Decimal('0.0')), output_field=DecimalField())
    ).filter(
        amount__gt=F('total_applied')
    )
    unapplied_memos = CustomerCreditMemo.objects.filter(customer=customer).exclude(status='applied')

    credits = [
        {'type': 'payment', 'id': p.id, 'date': p.payment_date, 'description': f"Payment #{p.id}", 'unapplied': p.unapplied_amount}
        for p in unapplied_payments
    ]
    credits.extend([
        {'type': 'memo', 'id': m.id, 'date': m.memo_date, 'description': f"Credit Memo #{m.memo_number}", 'unapplied': m.unapplied_amount}
        for m in unapplied_memos if m.unapplied_amount > 0
    ])

    # Open Invoices (Targets)
    open_invoices = CustomerInvoice.objects.filter(customer=customer).exclude(Q(status='paid') | Q(status='cancelled'))
    invoices = [
        {'id': i.id, 'number': i.invoice_number, 'date': i.invoice_date, 'due_date': i.due_date, 'total': i.total_amount, 'balance': i.balance_due}
        for i in open_invoices if i.balance_due > 0
    ]

    return JsonResponse({'credits': credits, 'invoices': invoices})