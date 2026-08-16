# gipcco_project/inventory/views/finished_products.py
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.exceptions import ValidationError

from ..models import Batch, FinishedProductReceipt, ReceiptSubBatch
from ..services import finished_product_service
from ..services.costing_service import get_inventory_state_at_datetime

def finished_goods_status(request):
    """
    Displays a unified view of the production pipeline using data
    fetched from the finished product service.
    """
    
    data = finished_product_service.get_finished_goods_status_data()
    
    context = {
        'active_page': 'shop_orders',
        'in_production_plans': data['in_production_plans'],
        'quarantined_receipts': data['quarantined_receipts'],
        'released_receipts': data['released_receipts'],
    }
    
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/finished_goods_status_content.html', context)
    return render(request, 'inventory/finished_goods_status.html', context)


@require_POST
def release_from_quarantine(request, pk):
    """
    Changes a FinishedProductReceipt's status from QUARANTINED to RELEASED.
    """
    receipt = get_object_or_404(FinishedProductReceipt, pk=pk, status=FinishedProductReceipt.Status.QUARANTINED)
    
    try:
        finished_product_service.release_receipt_from_quarantine(receipt)
        messages.success(request, f"تم الإفراج عن تشغيلة رقم '{receipt.individual_batch_number}' بنجاح.")
    except ValidationError as e:
        messages.error(request, f"حدث خطأ في التحقق: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء محاولة الإفراج عن التشغيلة: {e}")

    return redirect('inventory:finished_goods_status')


def receive_finished_product(request, batch_pk, individual_batch_number):
    """
    Handles the form for receiving a single batch from a production plan.
    """
    production_plan = get_object_or_404(
        Batch.objects.select_related('template__final_product').prefetch_related(
            'items__primitive_product', 'continuation_batches__items'
        ), 
        pk=batch_pk
    )

    # ==========================================================================
    #  CRITICAL BACKEND VALIDATION: PREVENT RECEIPT ON CONTINUATION BATCHES
    # ==========================================================================
    if production_plan.is_continuation:
        messages.error(request, "خطأ: لا يمكن استلام منتج نهائي على أمر تشغيل تكميلي. الرجاء الاستلام على الأمر الأصلي فقط.")
        # Redirect to the correct parent batch for a better user experience
        redirect_pk = production_plan.parent_batch.pk if production_plan.parent_batch else production_plan.pk
        return redirect('inventory:view_batch', pk=redirect_pk)

    if production_plan.status != Batch.Status.IN_PROGRESS:
        messages.error(request, f"خطأ: لا يمكن استلام منتج نهائي إلا لأمر تشغيل بحالة 'تحت التنفيذ'. الحالة الحالية هي '{production_plan.get_status_display()}'.")
        return redirect('inventory:view_batch', pk=production_plan.pk)

    # --- NEW: CRITICAL VALIDATION - PREVENT RECEIPT IF CONTINUATIONS ARE NOT READY ---
    pending_continuations = production_plan.continuation_batches.filter(
        status__in=[Batch.Status.DRAFT, Batch.Status.PENDING_APPROVAL]
    )
    if pending_continuations.exists():
        pending_numbers = ", ".join([b.shop_order_number for b in pending_continuations])
        messages.error(request, f"خطأ: لا يمكن استلام المنتج النهائي. هناك أوامر تشغيل تكميلية ({pending_numbers}) لم تبدأ بعد. يجب أن تكون جميع الأوامر التكميلية بحالة 'تحت التنفيذ' على الأقل.")
        return redirect('inventory:view_batch', pk=production_plan.pk)

    # ==========================================================================

    cost_data = finished_product_service.get_proportional_cost_for_receipt(production_plan)
    total_plan_cost = cost_data['total_plan_cost']
    proportional_cost = cost_data['proportional_cost']

    if request.method == 'POST':
        receipt_date_str = request.POST.get('receipt_date')
        market_type = request.POST.get('market_type')
        notes = request.POST.get('notes', '')
        
        sub_batch_ids = request.POST.getlist('sub_batch_id')
        sub_batch_qtys = request.POST.getlist('sub_batch_qty')

        if not all([receipt_date_str, market_type, sub_batch_ids, sub_batch_qtys]):
            messages.error(request, "الرجاء تعبئة جميع الحقول المطلوبة، بما في ذلك تشغيلة فرعية واحدة على الأقل.")
            return redirect(request.path)

        try:
            receipt_date = datetime.strptime(receipt_date_str, '%Y-%m-%d').date()
            
            sub_batches_data = [
                {'identifier': identifier, 'quantity': qty_str}
                for identifier, qty_str in zip(sub_batch_ids, sub_batch_qtys) if identifier and qty_str
            ]

            if not sub_batches_data:
                raise ValueError("لا توجد بيانات صالحة للتشغيلات الفرعية.")

            receipt = finished_product_service.create_finished_product_receipt(
                production_plan=production_plan,
                individual_batch_number=individual_batch_number,
                receipt_date=receipt_date,
                market_type=market_type,
                notes=notes,
                sub_batches_data=sub_batches_data
            )
            
            # Check if the batch was completed to show the correct info message
            production_plan.refresh_from_db() # Ensure we have the latest status
            if production_plan.status == Batch.Status.COMPLETED:
                 messages.info(request, f"اكتمل استلام جميع التشغيلات لأمر التشغيل '{production_plan.shop_order_number}'. تم تغيير الحالة إلى 'مكتمل'.")

            messages.success(request, f"تم استلام التشغيلة رقم '{individual_batch_number}' بنجاح ووضعها تحت الفحص.")
            return redirect('inventory:view_batch', pk=production_plan.pk)
        except (ValueError, TypeError, ValidationError) as e:
            error_message = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, f"حدث خطأ في البيانات المدخلة: {error_message}")
            return redirect(request.path)


    context = {
        'active_page': 'shop_orders',
        'plan': production_plan,
        'individual_batch_number': individual_batch_number,
        'proportional_cost': proportional_cost.quantize(Decimal('0.001')),
        'total_plan_cost': total_plan_cost,
        'market_type_choices': FinishedProductReceipt.MarketType.choices,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/receive_finished_product_content.html', context)
    return render(request, 'inventory/receive_finished_product.html', context)


def view_finished_product(request, pk):
    """
    Displays the details of a single finished product receipt,
    including a detailed cost breakdown from the parent and continuation batches.
    """
    receipt = get_object_or_404(
        FinishedProductReceipt.objects.select_related(
            'batch__template__final_product'
        ).prefetch_related('sub_batches'),
        pk=pk
    )

    production_plan = receipt.batch

    # This case should not happen based on business rules, but it's a good safeguard.
    if production_plan.is_continuation:
        messages.error(request, "لا يمكن عرض تفاصيل استلام من أمر تشغيل تكميلي مباشرة.")
        redirect_pk = production_plan.parent_batch.pk if production_plan.parent_batch else production_plan.pk
        return redirect('inventory:view_batch', pk=redirect_pk)

    cost_breakdown = finished_product_service.get_finished_product_cost_breakdown(receipt)

    context = {
        'active_page': 'shop_orders',
        'receipt': receipt,
        'production_plan': production_plan,
        'main_plan_cost': cost_breakdown['main_plan_cost'],
        'continuation_batches_with_costs': cost_breakdown['continuation_batches_with_costs'],
        'total_continuation_cost': cost_breakdown['total_continuation_cost'],
        'total_plan_cost': cost_breakdown['total_plan_cost'],
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/view_finished_product_content.html', context)
    return render(request, 'inventory/view_finished_product.html', context)


@require_POST
def cancel_finished_product_receipt_view(request, pk: int) -> HttpResponse:
    """
    Handles the request to cancel a finished product receipt.
    """
    receipt = get_object_or_404(FinishedProductReceipt, pk=pk)
    justification = request.POST.get('justification', '')

    if not justification:
        messages.error(request, "سبب الإلغاء مطلوب.")
        return redirect('inventory:view_finished_product', pk=pk)

    try:
        # Import the service here to avoid circular dependency issues if it grows
        from ..services import finished_product_service
        finished_product_service.cancel_finished_product_receipt(
            receipt=receipt,
            user=request.user,
            justification=justification
        )
        messages.success(request, f"تم إلغاء استلام التشغيلة رقم '{receipt.individual_batch_number}' بنجاح.")
        return redirect('inventory:view_batch', pk=receipt.batch.pk)
    except ValidationError as e:
        messages.error(request, f"لا يمكن إلغاء الاستلام: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
    
    return redirect('inventory:view_finished_product', pk=pk)