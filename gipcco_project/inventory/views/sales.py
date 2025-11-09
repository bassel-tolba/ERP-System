# gipcco_project/inventory/views/sales.py

import json
from decimal import Decimal
from datetime import datetime

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string
from weasyprint import HTML


from ..models import (
    Customer, SalesOrder, SalesOrderItem, FinishedProductReceipt,
    FinishedProductDispatch, Product, SalesReturn, SalesReturnItem, CustomerCreditMemo
)
from ..services import sales_service, sales_return_service


# --- Customer CRUD Views ---

def customers(request: HttpRequest) -> HttpResponse:
    """Manages customers (listing and creation)."""
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            _, created = Customer.objects.get_or_create(name=name.strip())
            if created:
                messages.success(request, f'تمت إضافة العميل "{name}" بنجاح.')
            else:
                messages.warning(request, f'العميل "{name}" موجود بالفعل.')
        return redirect('inventory:customers')

    context = {
        'active_page': 'sales',
        'customers': Customer.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/customers_content.html', context)
    return render(request, 'inventory/customers.html', context)


@require_POST
def edit_customer(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing a customer's details."""
    customer = get_object_or_404(Customer, pk=pk)
    name = request.POST.get('name', '').strip()
    if name:
        if Customer.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, "اسم العميل هذا مستخدم بالفعل.")
        else:
            customer.name = name
            customer.address = request.POST.get('address', '')
            customer.contact_info = request.POST.get('contact_info', '')
            customer.save()
            messages.success(request, "تم تعديل بيانات العميل بنجاح.")
    return redirect('inventory:customers')


@require_POST
def delete_customer(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a customer."""
    customer = get_object_or_404(Customer, pk=pk)
    customer.delete()
    messages.info(request, 'تم حذف العميل بنجاح.')
    return redirect('inventory:customers')


# --- Sales Order Views ---

def sales_orders(request: HttpRequest) -> HttpResponse:
    """Displays a list of all sales orders."""
    search_query = request.GET.get('q', '').strip()
    so_list = SalesOrder.objects.select_related('customer').all()

    if search_query:
        so_list = so_list.filter(
            Q(so_number__icontains=search_query) |
            Q(customer__name__icontains=search_query)
        )

    context = {
        'active_page': 'sales',
        'sales_orders': so_list,
        'search_query': search_query,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_orders_content.html', context)
    return render(request, 'inventory/sales_orders.html', context)


def create_sales_order(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new Sales Order."""
    if request.method == 'POST':
        customer_id = request.POST.get('customer_id')
        order_date_str = request.POST.get('order_date')
        so_number = request.POST.get('so_number')
        
        # --- Use new field names from the corrected form ---
        receipt_ids = request.POST.getlist('receipt_id')
        quantities = request.POST.getlist('quantity')
        base_prices = request.POST.getlist('base_price_per_unit')
        vat_rates = request.POST.getlist('vat_rate')

        if not all([customer_id, order_date_str, so_number, receipt_ids, quantities, base_prices, vat_rates]):
            messages.error(request, "الرجاء تعبئة جميع الحقول لإنشاء أمر البيع.")
            return redirect('inventory:create_sales_order')

        if SalesOrder.objects.filter(so_number=so_number).exists():
            messages.error(request, f"رقم أمر البيع '{so_number}' موجود بالفعل.")
            return redirect('inventory:create_sales_order')

        try:
            with transaction.atomic():
                so = SalesOrder.objects.create(
                    customer_id=customer_id,
                    order_date=datetime.strptime(order_date_str, '%Y-%m-%d').date(),
                    so_number=so_number
                )
                
                items_to_create = []
                # --- Loop through new form fields ---
                for receipt_id, qty, price, vat in zip(receipt_ids, quantities, base_prices, vat_rates):
                    if receipt_id and qty and price and vat is not None:
                        items_to_create.append(
                            SalesOrderItem(
                                sales_order=so,
                                finished_product_id=receipt_id,
                                quantity_ordered=float(qty),
                                base_price_per_unit=Decimal(price),
                                vat_rate=Decimal(vat) / 100 # Convert from percentage
                            )
                        )
                SalesOrderItem.objects.bulk_create(items_to_create)
            
            messages.success(request, "تم إنشاء أمر البيع بنجاح.")
            return redirect('inventory:view_sales_order', pk=so.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء أمر البيع: {e}")
            return redirect('inventory:create_sales_order')

    context = {
        'active_page': 'sales',
        'customers': Customer.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_order_create_content.html', context)
    return render(request, 'inventory/sales_order_create.html', context)


def view_sales_order(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays the details of a single sales order and handles dispatching."""
    so = get_object_or_404(SalesOrder.objects.select_related('customer'), pk=pk)
    
    so_items = so.items.select_related(
        'finished_product__batch__template__final_product'
    ).annotate(
        total_dispatched=Coalesce(Sum('dispatches__quantity'), 0.0, output_field=FloatField())
    )

    total_remaining = 0
    for item in so_items:
        item.quantity_remaining = item.quantity_ordered - item.total_dispatched
        total_remaining += item.quantity_remaining

    is_fully_dispatched = total_remaining < 0.001

    context = {
        'active_page': 'sales',
        'so': so,
        'so_items': so_items,
        'is_fully_dispatched': is_fully_dispatched,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_order_view_content.html', context)
    return render(request, 'inventory/sales_order_view.html', context)


@require_POST
def delete_sales_order(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a Sales Order."""
    so = get_object_or_404(SalesOrder, pk=pk)
    
    # Check if any item in the sales order has been dispatched
    if so.items.filter(dispatches__isnull=False).exists():
        messages.error(request, 'لا يمكن حذف أمر البيع هذا لأنه تم صرف بعض البنود بالفعل.')
        return redirect('inventory:view_sales_order', pk=pk)
    
    so_number = so.so_number
    so.delete()
    messages.info(request, f"تم حذف أمر البيع '{so_number}' بنجاح.")
    return redirect('inventory:sales_orders')


@require_POST
def edit_sales_order_item(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing a sales order item (e.g., from a modal)."""
    item = get_object_or_404(SalesOrderItem.objects.select_related('sales_order'), pk=pk)
    so_pk = item.sales_order.pk

    if item.dispatches.exists():
        messages.error(request, "لا يمكن تعديل هذا البند لأنه تم صرف كميات منه بالفعل.")
        return redirect('inventory:view_sales_order', pk=so_pk)

    quantity = request.POST.get('quantity_ordered')
    price = request.POST.get('base_price_per_unit')
    vat_rate = request.POST.get('vat_rate')

    try:
        item.quantity_ordered = float(quantity)
        item.base_price_per_unit = Decimal(price)
        item.vat_rate = Decimal(vat_rate) / 100
        item.save()
        messages.success(request, "تم تعديل بند أمر البيع بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"بيانات غير صالحة: {e}")

    return redirect('inventory:view_sales_order', pk=so_pk)


@require_POST
def delete_sales_order_item(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a sales order item."""
    item = get_object_or_404(SalesOrderItem.objects.select_related('sales_order'), pk=pk)
    so_pk = item.sales_order.pk

    if item.dispatches.exists():
        messages.error(request, "لا يمكن حذف هذا البند لأنه تم صرف كميات منه بالفعل.")
        return redirect('inventory:view_sales_order', pk=so_pk)

    item.delete()
    messages.success(request, "تم حذف بند أمر البيع بنجاح.")
    return redirect('inventory:view_sales_order', pk=so_pk)


# --- Dispatch Views ---

@require_POST
def create_dispatch(request: HttpRequest, so_item_pk: int) -> HttpResponse:
    """Creates a dispatch for a single sales order item."""
    so_item = get_object_or_404(
        SalesOrderItem.objects.select_related('sales_order', 'finished_product')
        .annotate(total_dispatched=Coalesce(Sum('dispatches__quantity'), 0.0)),
        pk=so_item_pk
    )
    so = so_item.sales_order
    
    quantity_str = request.POST.get('quantity')
    dispatch_date_str = request.POST.get('dispatch_date')

    if not quantity_str or not dispatch_date_str:
        messages.error(request, "الرجاء تحديد الكمية وتاريخ الصرف.")
        return redirect('inventory:view_sales_order', pk=so.pk)

    try:
        quantity = float(quantity_str)
        dispatch_date = timezone.make_aware(datetime.strptime(dispatch_date_str, '%Y-%m-%d'))

        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر.")

        quantity_remaining = so_item.quantity_ordered - so_item.total_dispatched
        if quantity > quantity_remaining + 0.001:
            raise ValueError(f"كمية الصرف ({quantity}) أكبر من الكمية المتبقية ({quantity_remaining}).")

        receipt = so_item.finished_product
        unit_cost = (receipt.total_cost / Decimal(str(receipt.total_quantity_produced))) if receipt.total_quantity_produced > 0 else Decimal('0.0')
        cost_at_dispatch = unit_cost * Decimal(str(quantity))

        with transaction.atomic():
            FinishedProductDispatch.objects.create(
                sales_order_item=so_item,
                finished_product=so_item.finished_product,
                quantity=quantity,
                dispatch_date=dispatch_date,
                cost_at_dispatch=cost_at_dispatch
            )
            # Update SO status
            total_ordered = sum(i.quantity_ordered for i in so.items.all())
            total_dispatched_after = sum(d.quantity for d in FinishedProductDispatch.objects.filter(sales_order_item__sales_order=so))
            
            if abs(total_dispatched_after - total_ordered) < 0.001:
                so.status = SalesOrder.Status.COMPLETED
            else:
                so.status = SalesOrder.Status.PARTIALLY_SHIPPED
            so.save(update_fields=['status'])

        messages.success(request, "تم إنشاء الصرف بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في إنشاء الصرف: {e}")

    return redirect('inventory:view_sales_order', pk=so.pk)


@require_POST
def edit_dispatch(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing an existing dispatch."""
    dispatch = get_object_or_404(
        FinishedProductDispatch.objects.select_related(
            'sales_order_item__sales_order',
            'sales_order_item__finished_product'
        ), 
        pk=pk
    )
    so_item = dispatch.sales_order_item
    so = so_item.sales_order

    quantity_str = request.POST.get('quantity')
    dispatch_date_str = request.POST.get('dispatch_date')

    try:
        new_quantity = float(quantity_str)
        new_date = timezone.make_aware(datetime.strptime(dispatch_date_str, '%Y-%m-%d'))

        with transaction.atomic():
            # Calculate available quantity for this item, EXCLUDING the current dispatch
            total_dispatched_for_item = so_item.dispatches.exclude(pk=pk).aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
            quantity_remaining = so_item.quantity_ordered - total_dispatched_for_item

            if new_quantity > quantity_remaining + 0.001:
                raise ValueError("الكمية الجديدة تتجاوز الكمية المتاحة في أمر البيع.")

            receipt = so_item.finished_product
            unit_cost = (receipt.total_cost / Decimal(str(receipt.total_quantity_produced))) if receipt.total_quantity_produced > 0 else Decimal('0.0')
            
            dispatch.quantity = new_quantity
            dispatch.dispatch_date = new_date
            dispatch.cost_at_dispatch = unit_cost * Decimal(str(new_quantity))
            dispatch.save()

            # Update SO status
            total_ordered = sum(i.quantity_ordered for i in so.items.all())
            total_dispatched_after = sum(d.quantity for d in FinishedProductDispatch.objects.filter(sales_order_item__sales_order=so))
            
            if abs(total_dispatched_after - total_ordered) < 0.001:
                so.status = SalesOrder.Status.COMPLETED
            elif total_dispatched_after > 0:
                so.status = SalesOrder.Status.PARTIALLY_SHIPPED
            else:
                so.status = SalesOrder.Status.PENDING
            so.save(update_fields=['status'])

        messages.success(request, "تم تعديل الصرف بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في تعديل الصرف: {e}")

    return redirect('inventory:view_sales_order', pk=so.pk)


@require_POST
def cancel_dispatch_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles cancelling a dispatch non-destructively by calling the sales service.
    """
    dispatch = get_object_or_404(FinishedProductDispatch.objects.select_related('sales_order_item__sales_order'), pk=pk)
    so = dispatch.sales_order_item.sales_order
    justification = request.POST.get('justification', '')

    if not justification:
        messages.error(request, "سبب الإلغاء مطلوب.")
        return redirect('inventory:view_sales_order', pk=so.pk)

    try:
        with transaction.atomic():
            # Call the service to cancel the dispatch and reverse its JE
            sales_service.cancel_dispatch(
                dispatch=dispatch,
                user=request.user,
                justification=justification
            )

            # Update SO status after cancellation
            total_ordered = sum(i.quantity_ordered for i in so.items.all())
            # IMPORTANT: Exclude cancelled dispatches from the sum
            total_dispatched_after = sum(
                d.quantity for d in FinishedProductDispatch.objects.filter(
                    sales_order_item__sales_order=so
                ).exclude(status='CANCELLED')
            )
            
            if abs(total_dispatched_after - total_ordered) < 0.001:
                so.status = SalesOrder.Status.COMPLETED
            elif total_dispatched_after > 0:
                so.status = SalesOrder.Status.PARTIALLY_SHIPPED
            else:
                so.status = SalesOrder.Status.PENDING
            so.save(update_fields=['status'])

        messages.success(request, "تم إلغاء الصرف بنجاح.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"خطأ في إلغاء الصرف: {e}")

    return redirect('inventory:view_sales_order', pk=so.pk)


@require_POST
def dispatch_from_sales_order(request: HttpRequest, so_pk: int) -> HttpResponse:
    """
    Handles the creation of FinishedProductDispatch records by calling the sales service.
    """
    sales_order = get_object_or_404(SalesOrder, pk=so_pk)
    dispatch_date_str = request.POST.get('dispatch_date')

    if not dispatch_date_str:
        messages.error(request, "الرجاء تحديد تاريخ الصرف.")
        return redirect('inventory:view_sales_order', pk=so_pk)

    try:
        dispatch_date = timezone.make_aware(datetime.strptime(dispatch_date_str, '%Y-%m-%d'))
        
        dispatches_to_create = []
        for key, quantity_str in request.POST.items():
            if key.startswith('quantity_') and quantity_str and float(quantity_str) > 0:
                so_item_id = key.split('_')[1]
                quantity_to_dispatch = float(quantity_str)
                
                dispatches_to_create.append({
                    'sales_order_item_id': int(so_item_id),
                    'quantity': quantity_to_dispatch
                })

        if not dispatches_to_create:
            messages.warning(request, "No quantities were entered to dispatch.")
            return redirect('inventory:view_sales_order', pk=so_pk)

        # Call the service to handle the logic
        sales_service.dispatch_from_sales_order(
            sales_order_id=so_pk,
            dispatch_date=dispatch_date,
            dispatches=dispatches_to_create
        )
        
        messages.success(request, f"Successfully created {len(dispatches_to_create)} dispatch(es).")

    except ValidationError as e:
        # The service layer raises ValidationError for business rule violations
        messages.error(request, f"Validation Error: {e.message}")
    except (ValueError, TypeError) as e:
        messages.error(request, f"Invalid data provided: {e}")
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {e}")

    return redirect('inventory:view_sales_order', pk=so_pk)


# --- Sales API Views (REMOVED REDUNDANT FUNCTION) ---

# This function is now defined only in api.py to avoid duplication.

# --- NEW: Sales Return Views ---

def create_sales_return(request: HttpRequest, so_pk: int) -> HttpResponse:
    """
    Handles the creation of a new Sales Return for a specific Sales Order.
    """
    sales_order = get_object_or_404(SalesOrder.objects.select_related('customer'), pk=so_pk)

    if request.method == 'POST':
        return_date_str = request.POST.get('return_date')
        if not return_date_str:
            messages.error(request, "الرجاء تحديد تاريخ الإرجاع.")
            return redirect('inventory:create_sales_return', so_pk=so_pk)

        try:
            with transaction.atomic():
                sales_return = SalesReturn.objects.create(
                    customer=sales_order.customer,
                    return_date=return_date_str,
                    sales_order=sales_order,
                    status=SalesReturn.Status.PENDING_INSPECTION
                )
                
                items_returned = 0
                for key, quantity_str in request.POST.items():
                    if key.startswith('quantity_') and quantity_str and float(quantity_str) > 0:
                        dispatch_id = key.split('_')[1]
                        quantity_returned = float(quantity_str)
                        
                        dispatch = get_object_or_404(FinishedProductDispatch, pk=dispatch_id)
                        
                        # --- NEW: Correct validation for multiple returns ---
                        already_returned_qty = dispatch.return_items.aggregate(
                            total=Coalesce(Sum('quantity_returned'), 0.0)
                        )['total']
                        remaining_to_return = dispatch.quantity - already_returned_qty

                        if quantity_returned > remaining_to_return:
                            raise ValidationError(f"لا يمكن إرجاع كمية {quantity_returned}. المتاح للإرجاع من هذه الشحنة هو {remaining_to_return} فقط.")

                        SalesReturnItem.objects.create(
                            sales_return=sales_return,
                            original_dispatch=dispatch,
                            quantity_returned=quantity_returned
                        )
                        items_returned += 1
                
                if items_returned == 0:
                    raise ValidationError("يجب إرجاع بند واحد على الأقل.")

            messages.success(request, "تم تسجيل مرتجع المبيعات بنجاح.")
            return redirect('inventory:view_sales_return', pk=sales_return.pk)
        except ValidationError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
        return redirect('inventory:create_sales_return', so_pk=so_pk)

    # GET request: Prepare data for the form
    dispatched_items = FinishedProductDispatch.objects.filter(
        sales_order_item__sales_order=sales_order
    ).select_related(
        'sales_order_item__finished_product__batch__template__final_product'
    ).annotate(
        total_returned=Coalesce(Sum('return_items__quantity_returned'), 0.0)
    )

    context = {
        'active_page': 'sales',
        'sales_order': sales_order,
        'dispatched_items': dispatched_items,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_return_create_content.html', context)
    return render(request, 'inventory/sales_return_create.html', context)


def sales_returns_list(request: HttpRequest) -> HttpResponse:
    """Displays a list of all sales returns."""
    returns = SalesReturn.objects.select_related('customer', 'sales_order').all()
    context = {
        'active_page': 'sales',
        'returns': returns,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_returns_list_content.html', context)
    return render(request, 'inventory/sales_returns_list.html', context)


def view_sales_return(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single sales return and handles the setting of
    dispositions for each item.
    """
    sales_return = get_object_or_404(
        SalesReturn.objects.select_related('customer', 'sales_order'), pk=pk
    )

    if request.method == 'POST':
        # This part handles setting the dispositions for the items
        try:
            with transaction.atomic():
                all_items_have_disposition = True
                for item in sales_return.items.all():
                    disposition = request.POST.get(f'disposition_{item.pk}')
                    if disposition:
                        item.disposition = disposition
                        item.save(update_fields=['disposition'])
                    else:
                        all_items_have_disposition = False
                
                # If all items now have a disposition, update the return status
                if all_items_have_disposition:
                    if sales_return.status == SalesReturn.Status.PENDING_INSPECTION:
                        sales_return.status = SalesReturn.Status.PENDING_PROCESSING
                        sales_return.save(update_fields=['status'])
                        messages.success(request, "تم تحديد قرار الفحص لجميع البنود. المرتجع جاهز للمعالجة.")
                else:
                    messages.warning(request, "يرجى تحديد قرار الفحص لجميع البنود.")

        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء حفظ القرارات: {e}")
        
        return redirect('inventory:view_sales_return', pk=pk)


    return_items = sales_return.items.select_related(
        'original_dispatch__sales_order_item__finished_product__batch__template__final_product',
        'inventory_adjustment' # Eager load the related adjustment
    ).all()

    # Check if a credit memo has already been created for this return
    credit_memo = CustomerCreditMemo.objects.filter(
        content_type=ContentType.objects.get_for_model(SalesReturn),
        object_id=sales_return.id
    ).first()

    context = {
        'active_page': 'sales',
        'sales_return': sales_return,
        'return_items': return_items,
        'credit_memo': credit_memo,
        'disposition_choices': SalesReturnItem.Disposition.choices,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/sales_return_view_content.html', context)
    return render(request, 'inventory/sales_return_view.html', context)


@require_POST
def process_inspected_return_view(request: HttpRequest, return_pk: int) -> HttpResponse:
    """
    View function to trigger the processing of an inspected sales return.
    """
    sales_return = get_object_or_404(SalesReturn, pk=return_pk)
    try:
        sales_return_service.process_inspected_return(sales_return)
        messages.success(request, "تمت معالجة المرتجع بنجاح. تم إنشاء قيود التسوية اللازمة.")
    except ValidationError as e:
        messages.error(request, f"خطأ في المعالجة: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
    
    return redirect('inventory:view_sales_return', pk=return_pk)


@require_POST
def create_credit_memo_from_return_view(request: HttpRequest, return_pk: int) -> HttpResponse:
    """Handles the form submission to create a credit memo from a sales return."""
    sales_return = get_object_or_404(SalesReturn, pk=return_pk)
    memo_number = request.POST.get('memo_number')
    memo_date = request.POST.get('memo_date')

    if not memo_number or not memo_date:
        messages.error(request, "الرجاء إدخال رقم وتاريخ إشعار الدائن.")
        return redirect('inventory:view_sales_return', pk=return_pk)

    try:
        with transaction.atomic():
            # The service function handles all logic, including validation
            sales_return_service.create_credit_memo_from_return(
                sales_return=sales_return,
                memo_number=memo_number,
                memo_date=memo_date
            )
            messages.success(request, f"تم إنشاء إشعار الدائن '{memo_number}' بنجاح.")
    except ValidationError as e:
        messages.error(request, f"خطأ في التحقق: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")

    return redirect('inventory:view_sales_return', pk=return_pk)


def view_credit_memo_pdf(request: HttpRequest, memo_pk: int) -> HttpResponse:
    """
    Generates a PDF document for a specific CustomerCreditMemo.
    """
    credit_memo = get_object_or_404(
        CustomerCreditMemo.objects.select_related('customer'), pk=memo_pk
    )
    sales_return = credit_memo.source_object
    items_data = []

    if sales_return and isinstance(sales_return, SalesReturn):
        return_items = sales_return.items.select_related(
            'original_dispatch__sales_order_item__finished_product__batch__template__final_product'
        ).all()

        for item in return_items:
            so_item = item.original_dispatch.sales_order_item
            quantity_returned = Decimal(str(item.quantity_returned))
            base_price = so_item.base_price_per_unit
            
            items_data.append({
                'product_name': so_item.finished_product.batch.template.final_product.name,
                'quantity': quantity_returned,
                'unit_price': base_price,
                'total_price': (quantity_returned * base_price).quantize(Decimal('0.001'))
            })

    context = {
        'credit_memo': credit_memo,
        'customer': credit_memo.customer,
        'sales_return': sales_return,
        'items_data': items_data,
    }

    html_string = render_to_string('inventory/pdfs/credit_memo_pdf.html', context)
    
    html = HTML(string=html_string, base_url=request.build_absolute_uri())
    pdf = html.write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    customer_name = credit_memo.customer.name.replace(" ", "_")
    filename = f"Credit_Memo_{credit_memo.memo_number}_{customer_name}.pdf"
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    
    return response