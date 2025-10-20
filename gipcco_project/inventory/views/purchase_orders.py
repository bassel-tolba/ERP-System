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
from django.core.exceptions import ValidationError, PermissionDenied

from ..models import Company, Product, PurchaseOrder, PurchaseOrderItem
from ..services import purchasing_service


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
    Handles the creation of a new Purchase Order by calling the purchasing service.
    """
    if request.method == 'POST':
        try:
            po_data = {
                'po_number': request.POST.get('po_number'),
                'supplier_id': request.POST.get('supplier_id'),
                'order_date': request.POST.get('order_date'),
            }
            
            items_data = []
            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            base_prices = request.POST.getlist('base_price_per_unit')
            vat_rates = request.POST.getlist('vat_rate')
            wht_rates = request.POST.getlist('withholding_tax_rate')

            for i in range(len(product_ids)):
                if product_ids[i]:
                    items_data.append({
                        'product_id': product_ids[i],
                        'quantity': quantities[i],
                        'base_price_per_unit': base_prices[i],
                        'vat_rate': vat_rates[i],
                        'withholding_tax_rate': wht_rates[i],
                    })

            po = purchasing_service.create_purchase_order(
                user=request.user,
                po_data=po_data,
                items_data=items_data
            )
            messages.success(request, f"تم إنشاء أمر الشراء {po.po_number} بنجاح.")
            return redirect('inventory:purchase_orders')
        except (ValidationError, ValueError) as e:
            messages.error(request, f"حدث خطأ في البيانات: {e}")
            # Fall through to render the form again with errors
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
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
    Displays the details of a single purchase order, including related receipts and invoices.
    """
    po = get_object_or_404(
        PurchaseOrder.objects.select_related('supplier')
        .prefetch_related(
            'items__product', 
            'items__receipts__supplierinvoiceitem_set__invoice' # Prefetch through to invoices
        ),
        pk=pk
    )
    
    # This logic is for display and doesn't need to be in a service
    related_invoices = set()
    for item in po.items.all():
        item.total_received = sum(r.quantity for r in item.receipts.all())
        item.is_completed = item.total_received >= item.quantity_ordered
        item.quantity_remaining = item.quantity_ordered - item.total_received

        # Gather related invoices
        for receipt in item.receipts.all():
            if hasattr(receipt, 'supplierinvoiceitem_set'):
                for inv_item in receipt.supplierinvoiceitem_set.all():
                    related_invoices.add(inv_item.invoice)

    context = {
        'active_page': 'purchasing',
        'po': po,
        'has_any_receipts': any(item.total_received > 0 for item in po.items.all()),
        'related_invoices': sorted(list(related_invoices), key=lambda x: x.invoice_date, reverse=True),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_view_content.html', context)
    return render(request, 'inventory/purchase_order_view.html', context)


def edit_purchase_order(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing Purchase Order by calling the purchasing service.
    """
    po = get_object_or_404(PurchaseOrder.objects.prefetch_related('items__product'), pk=pk)

    if request.method == 'POST':
        try:
            po_data = {
                'po_number': request.POST.get('po_number'),
                'supplier_id': request.POST.get('supplier_id'),
                'order_date': request.POST.get('order_date'),
            }
            
            items_data = []
            product_ids = request.POST.getlist('product_id')
            quantities = request.POST.getlist('quantity')
            base_prices = request.POST.getlist('base_price_per_unit')
            vat_rates = request.POST.getlist('vat_rate')
            wht_rates = request.POST.getlist('withholding_tax_rate')

            for i in range(len(product_ids)):
                if product_ids[i]:
                    items_data.append({
                        'product_id': product_ids[i],
                        'quantity': quantities[i],
                        'base_price_per_unit': base_prices[i],
                        'vat_rate': vat_rates[i],
                        'withholding_tax_rate': wht_rates[i],
                    })

            purchasing_service.update_purchase_order(
                user=request.user,
                po=po,
                po_data=po_data,
                items_data=items_data
            )
            messages.success(request, "تم تعديل أمر الشراء بنجاح.")
            return redirect('inventory:view_purchase_order', pk=po.id)
        except (ValidationError, ValueError) as e:
            messages.error(request, f"حدث خطأ في البيانات: {e}")
        except PermissionError as e:
            messages.error(request, str(e))
            return redirect('inventory:view_purchase_order', pk=pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
            return redirect('inventory:edit_purchase_order', pk=pk)

    primitive_products_qs = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
    
    po_items_data = [
        {
            'product_id': item.product_id,
            'quantity': item.quantity_ordered,
            'base_price_per_unit': str(item.base_price_per_unit),
            'vat_rate': str(item.vat_rate * 100),
            'withholding_tax_rate': str(item.withholding_tax_rate * 100)
        } for item in po.items.all()
    ]

    context = {
        'active_page': 'purchasing',
        'po': po,
        'suppliers': Company.objects.all(),
        'products': list(primitive_products_qs.values('id', 'name', 'code')),
        'po_items_data': po_items_data,
    }
    
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_order_edit_content.html', context)
    return render(request, 'inventory/purchase_order_edit.html', context)


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