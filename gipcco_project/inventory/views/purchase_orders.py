# gipcco_project/inventory/views/purchase_orders.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ..models import Company, Product, PurchaseOrder, PurchaseOrderItem


# The 'purchase_orders' and 'create_purchase_order' functions are correct and remain unchanged.
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
        unit_prices = request.POST.getlist('unit_price')

        if not all([po_number, supplier_id, order_date_str, product_ids, quantities, unit_prices]):
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
                for pid, qty, price in zip(product_ids, quantities, unit_prices):
                    if pid and qty and price:
                        items_to_create.append(
                            PurchaseOrderItem(
                                purchase_order=po,
                                product_id=pid,
                                quantity_ordered=float(qty),
                                unit_price=Decimal(price)
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


# --- THIS VIEW IS CORRECTED ---
def view_purchase_order(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single purchase order.
    """
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier')
        .prefetch_related('items__product', 'items__receipts'),
        pk=pk
    )
    
    # Calculate totals in the view to keep the template clean
    for item in po.items.all():
        item.total_received = sum(r.quantity for r in item.receipts.all())
        item.is_completed = item.total_received >= item.quantity_ordered
        # --- THE FIX IS HERE: Calculate remaining quantity in the view ---
        item.quantity_remaining = item.quantity_ordered - item.total_received

    context = {
        'active_page': 'purchasing',
        'po': po,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_view_content.html', context)
    return render(request, 'inventory/purchase_order_view.html', context)