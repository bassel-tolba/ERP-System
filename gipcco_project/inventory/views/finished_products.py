# gipcco_project/inventory/views/finished_products.py
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Batch, FinishedProductReceipt, ReceiptSubBatch
from ..services.costing_service import get_inventory_state_at_datetime

def finished_goods_status(request):
    """
    Displays a unified view of the production pipeline:
    1. In Production: Plans with pending receipts.
    2. In Quarantine: Received batches pending QC.
    3. Released: Finished goods ready for sale.
    """
    # 1. Get batches that are still "In Production"
    # A batch is in production if the number of received batches is less than the total planned.
    all_plans = Batch.objects.annotate(received_count=Count('receipts')).select_related(
        'template__final_product'
    ).order_by('-creation_date')

    in_production_plans = []
    for plan in all_plans:
        # We must do this check in Python since number_of_batches_in_plan is a property
        if plan.received_count < plan.number_of_batches_in_plan:
            in_production_plans.append(plan)

    # 2. Get batches that are "In Quarantine"
    quarantined_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.QUARANTINED
    ).select_related('batch__template__final_product')

    # 3. Get batches that have been "Released"
    released_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).select_related('batch__template__final_product')
    
    context = {
        'active_page': 'shop_orders',
        'in_production_plans': in_production_plans,
        'quarantined_receipts': quarantined_receipts,
        'released_receipts': released_receipts,
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
        with transaction.atomic():
            receipt.status = FinishedProductReceipt.Status.RELEASED
            receipt.release_date = timezone.now().date()
            receipt.save(update_fields=['status', 'release_date'])
        
        messages.success(request, f"تم الإفراج عن تشغيلة رقم '{receipt.individual_batch_number}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء محاولة الإفراج عن التشغيلة: {e}")

    return redirect('inventory:finished_goods_status')


def receive_finished_product(request, batch_pk, individual_batch_number):
    """
    Handles the form for receiving a single batch from a production plan.
    """
    production_plan = get_object_or_404(
        Batch.objects.select_related('template__final_product').prefetch_related('items__primitive_product'), 
        pk=batch_pk
    )

    # ====== START OF CORRECTION ======
    # This logic now correctly calculates the cost even if the `cost_at_consumption`
    # field hasn't been populated by the costing service yet.
    total_plan_cost = Decimal('0.0')
    for item in production_plan.items.all():
        cost = item.cost_at_consumption
        # If cost is not yet calculated (due to signal timing), calculate it on the fly
        if cost is None:
            state = get_inventory_state_at_datetime(item.primitive_product_id, production_plan.creation_date)
            mac = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            cost = mac.quantize(Decimal('0.001'))
        
        total_plan_cost += cost * Decimal(str(item.actual_quantity or 0.0))
    # ====== END OF CORRECTION ======

    num_batches_in_plan = production_plan.number_of_batches_in_plan
    proportional_cost = (total_plan_cost / num_batches_in_plan) if num_batches_in_plan > 0 else Decimal('0.0')

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
            with transaction.atomic():
                receipt_date = datetime.strptime(receipt_date_str, '%Y-%m-%d').date()
                
                total_quantity_produced = sum(float(qty) for qty in sub_batch_qtys if qty)

                # Create the main receipt record
                receipt = FinishedProductReceipt.objects.create(
                    batch=production_plan,
                    individual_batch_number=individual_batch_number,
                    receipt_date=receipt_date,
                    market_type=market_type,
                    notes=notes,
                    total_cost=proportional_cost.quantize(Decimal('0.001')),
                    total_quantity_produced=total_quantity_produced,
                    status=FinishedProductReceipt.Status.QUARANTINED # Explicitly set
                )

                # Create all the sub-batch records
                sub_batches_to_create = []
                for identifier, qty_str in zip(sub_batch_ids, sub_batch_qtys):
                    if identifier and qty_str:
                        sub_batches_to_create.append(
                            ReceiptSubBatch(
                                receipt=receipt,
                                sub_batch_identifier=identifier,
                                quantity=float(qty_str)
                            )
                        )
                
                if not sub_batches_to_create:
                     raise ValueError("لا توجد بيانات صالحة للتشغيلات الفرعية.")

                ReceiptSubBatch.objects.bulk_create(sub_batches_to_create)

            messages.success(request, f"تم استلام التشغيلة رقم '{individual_batch_number}' بنجاح ووضعها تحت الفحص.")
            return redirect('inventory:view_batch', pk=production_plan.pk)
        except (ValueError, TypeError) as e:
            messages.error(request, f"حدث خطأ في البيانات المدخلة: {e}")
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
    Displays the details of a single finished product receipt.
    """
    receipt = get_object_or_404(
        FinishedProductReceipt.objects.select_related(
            'batch__template__final_product'
        ).prefetch_related('sub_batches'),
        pk=pk
    )
    context = {
        'active_page': 'shop_orders',
        'receipt': receipt,
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/view_finished_product_content.html', context)
    return render(request, 'inventory/view_finished_product.html', context)