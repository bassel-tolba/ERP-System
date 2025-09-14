# gipcco_project/inventory/views/financials.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import (
    Company, SupplierInvoice, SupplierInvoiceItem, InventoryLog, 
    Payment, PaymentApplication, BankAccount, Customer, CustomerInvoice, FinishedProductDispatch, CustomerInvoiceItem, CustomerPaymentApplication, SalesOrder, BankTransfer, JournalEntry, FixedAsset, DepreciationLog
)
from ..forms import JournalEntryForm, JournalEntryLineFormSet

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
    """Handles the creation of a new supplier invoice from unbilled receipts."""
    if request.method == 'POST':
        supplier_id = request.POST.get('supplier')
        invoice_number = request.POST.get('invoice_number').strip()
        invoice_date_str = request.POST.get('invoice_date')
        due_date_str = request.POST.get('due_date')
        receipt_ids = request.POST.getlist('receipt_ids')

        if not all([supplier_id, invoice_number, invoice_date_str, due_date_str, receipt_ids]):
            messages.error(request, "يرجى تعبئة جميع الحقول واختيار فاتورة استلام واحدة على الأقل.")
            return redirect('inventory:create_supplier_invoice')

        if SupplierInvoice.objects.filter(supplier_id=supplier_id, invoice_number=invoice_number).exists():
            messages.error(request, f"فاتورة بنفس الرقم '{invoice_number}' موجودة بالفعل لهذا المورد.")
            return redirect('inventory:create_supplier_invoice')

        try:
            with transaction.atomic():
                invoice = SupplierInvoice.objects.create(
                    supplier_id=supplier_id,
                    invoice_number=invoice_number,
                    invoice_date=datetime.strptime(invoice_date_str, '%Y-%m-%d').date(),
                    due_date=datetime.strptime(due_date_str, '%Y-%m-%d').date(),
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
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            return redirect('inventory:create_supplier_invoice')

    context = {
        'active_page': 'financials',
        'sub_page': 'supplier_invoices',
        'suppliers': Company.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
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
def apply_payment_to_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Creates a payment and applies it to a specific invoice."""
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    
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
        
    return redirect('inventory:view_supplier_invoice', pk=pk)

# --- A/P API Views ---

def api_get_uninvoiced_receipts(request: HttpRequest, supplier_id: int) -> JsonResponse:
    """Returns a JSON list of released receipts that are not yet on an invoice."""
    receipts = InventoryLog.objects.filter(
        company_id=supplier_id,
        status=InventoryLog.Status.RELEASED,
        invoice_item__isnull=True  # The crucial filter
    ).select_related('product').order_by('-release_timestamp')
    
    data = [
        {
            'id': r.id,
            'qc_no': r.qc_no,
            'release_date': r.release_timestamp.strftime('%Y-%m-%d'),
            'product_name': r.product.name,
            'quantity': r.quantity,
            'unit': r.product.unit,
            'total_value': str(((r.base_unit_price * Decimal(str(r.quantity))) + r.vat_amount).quantize(Decimal('0.001')))
        }
        for r in receipts
    ]
    return JsonResponse({'receipts': data})



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
def receive_payment_for_invoice(request: HttpRequest, pk: int) -> HttpResponse:
    """Creates a payment received and applies it to a specific invoice."""
    invoice = get_object_or_404(CustomerInvoice, pk=pk)
    
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
        
    return redirect('inventory:view_customer_invoice', pk=pk)


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
        'sub_page': 'journal',
        'journal_entries': manual_entries
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entries_content.html', context)
    return render(request, 'inventory/journal_entries.html', context)


def create_journal_entry(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a manual journal entry with its lines."""
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        # IMPORTANT: Added prefix to the formset call to match the template
        formset = JournalEntryLineFormSet(request.POST, prefix='lines')
        
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    journal_entry = form.save(commit=False)
                    journal_entry.source_object = None
                    journal_entry.save()
                    
                    formset.instance = journal_entry
                    formset.save()
                messages.success(request, "تم إنشاء قيد اليومية بنجاح.")
                return redirect('inventory:journal_entries')
            except Exception as e:
                 messages.error(request, f"حدث خطأ أثناء الحفظ: {e}")

        else:
            error_list = []
            for field, errors in form.errors.items():
                error_list.append(f"{field}: {', '.join(errors)}")
            if formset.non_form_errors():
                error_list.append(formset.non_form_errors().as_text())
            for form_errors in formset.errors:
                 for field, errors in form_errors.items():
                     if errors:
                        error_list.append(f"{field}: {', '.join(errors)}")
            messages.error(request, f"يرجى تصحيح الأخطاء التالية: {'; '.join(error_list)}")


    else:
        form = JournalEntryForm(initial={'date': timezone.now()})
        # IMPORTANT: Added prefix here as well for consistency
        formset = JournalEntryLineFormSet(prefix='lines')

    context = {
        'active_page': 'financials',
        'sub_page': 'journal',
        'form': form,
        'formset': formset,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entry_create_content.html', context)
    return render(request, 'inventory/journal_entry_create.html', context)

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