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

from ..models import Customer, SalesOrder, SalesOrderItem, FinishedProductReceipt, FinishedProductDispatch


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
        
        receipt_ids = request.POST.getlist('receipt_id')
        quantities = request.POST.getlist('quantity')
        unit_prices = request.POST.getlist('unit_price')

        if not all([customer_id, order_date_str, so_number, receipt_ids, quantities, unit_prices]):
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
                for receipt_id, qty, price in zip(receipt_ids, quantities, unit_prices):
                    if receipt_id and qty and price:
                        items_to_create.append(
                            SalesOrderItem(
                                sales_order=so,
                                finished_product_id=receipt_id,
                                quantity_ordered=float(qty),
                                unit_price=Decimal(price)
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

    # Calculate remaining quantities and overall status
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
def dispatch_from_sales_order(request: HttpRequest, pk: int) -> HttpResponse:
    """The core transaction view for shipping items from an SO."""
    so = get_object_or_404(SalesOrder, pk=pk)
    item_ids = request.POST.getlist('item_id')
    dispatch_quantities = request.POST.getlist('dispatch_quantity')
    dispatch_date_str = request.POST.get('dispatch_date')

    if not dispatch_date_str:
        messages.error(request, "الرجاء تحديد تاريخ الصرف.")
        return redirect('inventory:view_sales_order', pk=pk)

    try:
        dispatch_datetime = timezone.make_aware(datetime.strptime(dispatch_date_str, '%Y-%m-%d'))
        
        with transaction.atomic():
            dispatches_to_create = []
            so_items = {
                str(item.id): item for item in SalesOrderItem.objects.filter(sales_order=so)
                .annotate(total_dispatched=Coalesce(Sum('dispatches__quantity'), 0.0))
            }

            for item_id, qty_str in zip(item_ids, dispatch_quantities):
                if not qty_str or float(qty_str) <= 0:
                    continue

                item = so_items.get(item_id)
                if not item:
                    raise ValueError(f"لم يتم العثور على البند رقم {item_id} في أمر البيع.")
                
                qty_to_dispatch = float(qty_str)
                qty_remaining = item.quantity_ordered - item.total_dispatched
                
                if qty_to_dispatch > qty_remaining + 0.001:
                    raise ValueError(f"كمية الصرف ({qty_to_dispatch}) أكبر من الكمية المتبقية ({qty_remaining}) للمنتج.")
                
                receipt = get_object_or_404(FinishedProductReceipt, pk=item.finished_product_id)
                unit_cost = (receipt.total_cost / Decimal(str(receipt.total_quantity_produced))) if receipt.total_quantity_produced > 0 else Decimal('0.0')

                dispatches_to_create.append(
                    FinishedProductDispatch(
                        sales_order_item=item,
                        quantity=qty_to_dispatch,
                        dispatch_date=dispatch_datetime,
                        cost_at_dispatch=unit_cost * Decimal(str(qty_to_dispatch))
                    )
                )

            if not dispatches_to_create:
                messages.warning(request, "لم يتم تحديد كميات للصرف.")
                return redirect('inventory:view_sales_order', pk=pk)

            FinishedProductDispatch.objects.bulk_create(dispatches_to_create)

            # Update SO status
            total_ordered = sum(i.quantity_ordered for i in so.items.all())
            total_dispatched_after = sum(d.quantity for d in FinishedProductDispatch.objects.filter(sales_order_item__sales_order=so))
            
            if abs(total_dispatched_after - total_ordered) < 0.001:
                so.status = SalesOrder.Status.COMPLETED
            else:
                so.status = SalesOrder.Status.PARTIALLY_SHIPPED
            so.save()

        messages.success(request, "تم تسجيل عملية الصرف بنجاح.")
    except (ValueError, TypeError) as e:
        messages.error(request, f"حدث خطأ: {e}")
    
    return redirect('inventory:view_sales_order', pk=pk)

# --- Sales API Views ---

def api_get_sellable_stock(request: HttpRequest) -> JsonResponse:
    """API endpoint to get released, in-stock finished product batches."""
    sellable_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).select_related(
        'batch__template__final_product'
    ).annotate(
        total_dispatched=Coalesce(Sum('sales_items__dispatches__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        quantity_available=F('total_quantity_produced') - F('total_dispatched')
    ).filter(
        quantity_available__gt=0.001
    )

    data = [
        {
            'id': receipt.id,
            'product_name': receipt.batch.template.final_product.name,
            'batch_number': receipt.individual_batch_number,
            'available_qty': receipt.quantity_available,
            'unit': receipt.batch.template.final_product.unit
        } for receipt in sellable_receipts
    ]
    return JsonResponse(data, safe=False)