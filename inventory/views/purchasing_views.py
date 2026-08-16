# gipcco_project/inventory/views/purchasing_views.py

import logging
from decimal import Decimal
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.contrib.auth.decorators import permission_required
from django.views.decorators.http import require_POST

from ..models import PurchaseReturn, Company, InventoryLog
from ..services import purchasing_service

logger = logging.getLogger(__name__)


@permission_required('inventory.view_purchasereturn')
def purchase_returns_list(request: HttpRequest) -> HttpResponse:
    """Displays a list of all purchase returns."""
    returns = PurchaseReturn.objects.select_related('supplier').all()
    context = {
        'active_page': 'purchasing',
        'sub_page': 'purchase_returns',
        'returns': returns,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_returns_list_content.html', context)
    return render(request, 'inventory/purchase_returns_list.html', context)


@permission_required('inventory.add_purchasereturn')
def create_purchase_return(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new Purchase Return."""
    if request.method == 'POST':
        try:
            return_data = {
                'supplier_id': request.POST.get('supplier'),
                'return_date': request.POST.get('return_date'),
                'notes': request.POST.get('notes'),
            }
            
            items_data = []
            receipt_ids = request.POST.getlist('receipt_id')
            quantities = request.POST.getlist('quantity_returned')

            for i in range(len(receipt_ids)):
                if receipt_ids[i] and quantities[i]:
                    items_data.append({
                        'original_receipt_id': receipt_ids[i],
                        'quantity_returned': quantities[i],
                    })
            
            purchase_return = purchasing_service.create_purchase_return(
                user=request.user,
                return_data=return_data,
                items_data=items_data
            )
            messages.success(request, "تم إنشاء مرتجع المشتريات بنجاح.")
            return redirect('inventory:view_purchase_return', pk=purchase_return.pk)
        except (ValidationError, ValueError) as e:
            messages.error(request, f"خطأ في البيانات: {e}")
        except Exception as e:
            logger.exception("Error creating purchase return")
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
            return redirect('inventory:create_purchase_return')

    context = {
        'active_page': 'purchasing',
        'sub_page': 'purchase_returns',
        'suppliers': Company.objects.all(),
        'today_date': datetime.now().strftime('%Y-m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_return_create_content.html', context)
    return render(request, 'inventory/purchase_return_create.html', context)


@permission_required('inventory.view_purchasereturn')
def view_purchase_return(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays the details of a single purchase return."""
    purchase_return = get_object_or_404(
        PurchaseReturn.objects.select_related('supplier', 'debit_memo'), 
        pk=pk
    )
    context = {
        'active_page': 'purchasing',
        'sub_page': 'purchase_returns',
        'return': purchase_return,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/purchase_return_view_content.html', context)
    return render(request, 'inventory/purchase_return_view.html', context)


@require_POST
@permission_required('inventory.change_purchasereturn')
def process_inventory_return_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Processes the inventory side of a purchase return."""
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)
    try:
        purchasing_service.process_inventory_return(user=request.user, purchase_return=purchase_return)
        messages.success(request, "تمت معالجة حركة المخزون للمرتجع بنجاح.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.exception(f"Error processing inventory for purchase return ID {pk}")
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
    
    return redirect('inventory:view_purchase_return', pk=pk)


@require_POST
@permission_required('inventory.add_supplierdebitmemo')
def create_debit_memo_from_return_view(request: HttpRequest, pk: int) -> HttpResponse:
    """Creates a Supplier Debit Memo from a processed Purchase Return."""
    purchase_return = get_object_or_404(PurchaseReturn, pk=pk)
    try:
        memo_data = {
            'memo_number': request.POST.get('memo_number'),
            'memo_date': request.POST.get('memo_date'),
        }
        debit_memo = purchasing_service.create_debit_memo_from_return(
            user=request.user,
            purchase_return=purchase_return,
            memo_data=memo_data
        )
        messages.success(request, f"تم إنشاء إشعار الخصم رقم {debit_memo.memo_number} بنجاح.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, str(e))
    except Exception as e:
        logger.exception(f"Error creating debit memo for purchase return ID {pk}")
        messages.error(request, f"حدث خطأ غير متوقع: {e}")

    return redirect('inventory:view_purchase_return', pk=pk)

