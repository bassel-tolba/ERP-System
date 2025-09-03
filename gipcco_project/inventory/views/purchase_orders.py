# gipcco_project/inventory/views/purchase_orders.py
import json
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST


from ..models import Company, Product, PurchaseOrder, PurchaseOrderItem


def purchase_orders(request: HttpRequest) -> HttpResponse:
    """
    Displays a list of all purchase orders, with search functionality.
    """
    search_query = request.GET.get('q', '').strip()
    po_list = PurchaseOrder.objects.select_related('supplier').all()

    if search_query:
        po_list = po_list.filter(
            Q(po_number__icontains=search_query) |
            Q(supplier__name__icontains=search_query)
        )

    context = {
        'active_page': 'purchasing',
        'purchase_orders': po_list,
        'search_query': search_query,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_orders_content.html', context)
    return render(request, 'inventory/purchase_orders.html', context)



def create_purchase_order(request: HttpRequest) -> HttpResponse:
    """
    Handles the creation of a new Purchase Order.
    """
    if request.method == 'POST':
        po_number = request.POST.get('po_number')
        supplier_id = request.POST.get('supplier_id')
        order_date_str = request.POST.get('order_date')
        
        product_ids = request.POST.getlist('product_id')
        quantities = request.POST.getlist('quantity')
        total_prices = request.POST.getlist('total_price')

        if not all([po_number, supplier_id, order_date_str, product_ids, quantities, total_prices]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لإنشاء أمر الشراء.")
            return redirect('inventory:create_purchase_order')
        
        if PurchaseOrder.objects.filter(po_number=po_number).exists():
            messages.error(request, f"رقم أمر الشراء '{po_number}' موجود بالفعل.")
            return redirect('inventory:create_purchase_order')

        try:
            with transaction.atomic():
                order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date()
                po = PurchaseOrder.objects.create(
                    po_number=po_number,
                    supplier_id=supplier_id,
                    order_date=order_date
                )
                
                items_to_create = []
                for pid, qty, price in zip(product_ids, quantities, total_prices):
                    if pid and qty and price:
                        items_to_create.append(
                            PurchaseOrderItem(
                                purchase_order=po,
                                product_id=pid,
                                quantity_ordered=float(qty),
                                total_price=Decimal(price)
                            )
                        )
                PurchaseOrderItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم إنشاء أمر الشراء بنجاح.")
            return redirect('inventory:purchase_orders')
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء أمر الشراء: {e}")
            return redirect('inventory:create_purchase_order')

    primitive_products_qs = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))

    context = {
        'active_page': 'purchasing',
        'suppliers': Company.objects.all(),
        'products': list(primitive_products_qs.values('id', 'name', 'code')),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_create_content.html', context)
    return render(request, 'inventory/purchase_order_create.html', context)


def view_purchase_order(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single purchase order.
    """
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier')
        .prefetch_related('items__product', 'items__receipts'),
        pk=pk
    )
    
    # Calculate totals and check for receipts in the view to keep the template clean
    has_any_receipts = False
    for item in po.items.all():
        item.total_received = sum(r.quantity for r in item.receipts.all())
        if item.total_received > 0:
            has_any_receipts = True
        item.is_completed = item.total_received >= item.quantity_ordered
        item.quantity_remaining = item.quantity_ordered - item.total_received

    context = {
        'active_page': 'purchasing',
        'po': po,
        'has_any_receipts': has_any_receipts,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_view_content.html', context)
    return render(request, 'inventory/purchase_order_view.html', context)


# --- NEW VIEW ---
def edit_purchase_order(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing Purchase Order.
    Editing is blocked if any item has been received.
    """
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__product'), pk=pk)

    # Check if any item has a receipt. If so, block editing.
    if PurchaseOrderItem.objects.filter(purchase_order=po, receipts__isnull=False).exists():
        messages.error(request, "لا يمكن تعديل أمر الشراء هذا لأنه تم استلام بعض البنود بالفعل.")
        return redirect('inventory:view_purchase_order', pk=pk)

    if request.method == 'POST':
        po_number = request.POST.get('po_number')
        supplier_id = request.POST.get('supplier_id')
        order_date_str = request.POST.get('order_date')
        
        product_ids = request.POST.getlist('product_id')
        quantities = request.POST.getlist('quantity')
        total_prices = request.POST.getlist('total_price')

        if not all([po_number, supplier_id, order_date_str, product_ids, quantities, total_prices]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لتعديل أمر الشراء.")
            return redirect('inventory:edit_purchase_order', pk=pk)
        
        # Check for unique PO number, excluding the current PO
        if PurchaseOrder.objects.filter(po_number=po_number).exclude(pk=pk).exists():
            messages.error(request, f"رقم أمر الشراء '{po_number}' موجود بالفعل.")
            return redirect('inventory:edit_purchase_order', pk=pk)

        try:
            with transaction.atomic():
                po.po_number = po_number
                po.supplier_id = supplier_id
                po.order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date()
                po.save()
                
                # Simple strategy: Delete old items and create new ones
                po.items.all().delete()
                
                items_to_create = []
                for pid, qty, price in zip(product_ids, quantities, total_prices):
                    if pid and qty and price:
                        items_to_create.append(
                            PurchaseOrderItem(
                                purchase_order=po,
                                product_id=pid,
                                quantity_ordered=float(qty),
                                total_price=Decimal(price)
                            )
                        )
                PurchaseOrderItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم تعديل أمر الشراء بنجاح.")
            return redirect('inventory:view_purchase_order', pk=po.id)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تعديل أمر الشراء: {e}")
            return redirect('inventory:edit_purchase_order', pk=pk)

    primitive_products_qs = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
    
    # Prepare items data for JavaScript on the template
    po_items_data = [
        {
            'product_id': item.product_id,
            'quantity': item.quantity_ordered,
            'total_price': str(item.total_price)
        } for item in po.items.all()
    ]

    context = {
        'active_page': 'purchasing',
        'po': po,
        'suppliers': Company.objects.all(),
        'products': list(primitive_products_qs.values('id', 'name', 'code')),
        'po_items_json': json.dumps(po_items_data),
    }
    
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_edit_content.html', context)
    return render(request, 'inventory/purchase_order_edit.html', context)


# --- NEW VIEW ---
@require_POST
def delete_purchase_order(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a Purchase Order.
    Deletion is blocked if any item has been received.
    """
    po = get_object_or_404(PurchaseOrder, pk=pk)
    
    if PurchaseOrderItem.objects.filter(purchase_order=po, receipts__isnull=False).exists():
        messages.error(request, 'لا يمكن حذف أمر الشراء هذا لأنه تم استلام بعض البنود بالفعل.')
        return redirect('inventory:view_purchase_order', pk=pk)
        
    try:
        po_number = po.po_number
        po.delete()
        messages.info(request, f"تم حذف أمر الشراء '{po_number}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف أمر الشراء: {e}")
        return redirect('inventory:view_purchase_order', pk=pk)
            
    return redirect('inventory:purchase_orders')