# gipcco_project/inventory/views/finished_products.py
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Sum, F, ExpressionWrapper, DecimalField
from django.db.models.functions import Coalesce
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
    # ==========================================================================
    #  FIX: Filter out continuation batches from this list.
    #  Only parent batches can have finished goods received against them.
    # ==========================================================================
    all_plans = Batch.objects.filter(is_continuation=False, status=Batch.Status.IN_PROGRESS).annotate(
        received_count=Count('receipts')
    ).select_related(
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
    # ==========================================================================


    # ==========================================================================
    #  CORRECTED COST CALCULATION
    #  This now includes the cost of the main plan AND all its continuations.
    # ==========================================================================
    main_plan_cost = Decimal('0.0')
    for item in production_plan.items.all():
        cost = item.cost_at_consumption
        if cost is None: # Fallback calculation if costing service hasn't run yet
            state = get_inventory_state_at_datetime(item.primitive_product_id, production_plan.creation_date)
            mac = (state['value'] / state['quantity']) if state['quantity'] > 0 else Decimal('0.0')
            cost = mac.quantize(Decimal('0.001'))
        main_plan_cost += cost * Decimal(str(item.actual_quantity or 0.0))

    # Aggregate costs from all continuation batches using a more efficient DB query
    continuation_costs = production_plan.continuation_batches.aggregate(
        total=Sum(
            ExpressionWrapper(
                F('items__actual_quantity') * F('items__cost_at_consumption'),
                output_field=DecimalField()
            )
        )
    )['total'] or Decimal('0.0')

    total_plan_cost = main_plan_cost + continuation_costs
    # ==========================================================================

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
                    status=FinishedProductReceipt.Status.QUARANTINED
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

                # --- NEW: Check if all batches in the plan have been received ---
                # We refresh the count from the DB to ensure accuracy within the transaction
                if production_plan.receipts.count() >= production_plan.number_of_batches_in_plan:
                    production_plan.status = Batch.Status.COMPLETED
                    production_plan.save(update_fields=['status'])
                    messages.info(request, f"اكتمل استلام جميع التشغيلات لأمر التشغيل '{production_plan.shop_order_number}'. تم تغيير الحالة إلى 'مكتمل'.")

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

    # ==========================================================================
    #  COST BREAKDOWN CALCULATION
    # ==========================================================================
    # 1. Calculate cost of the main production plan using DB aggregation for efficiency
    main_plan_cost = production_plan.items.aggregate(
        total=Coalesce(Sum(
            ExpressionWrapper(
                F('actual_quantity') * F('cost_at_consumption'),
                output_field=DecimalField()
            )
        ), Decimal('0.0'))
    )['total']

    # 2. Get continuation batches with their individual costs annotated
    continuation_batches_with_costs = production_plan.continuation_batches.annotate(
        continuation_cost=Coalesce(Sum(
            ExpressionWrapper(
                F('items__actual_quantity') * F('items__cost_at_consumption'),
                output_field=DecimalField()
            )
        ), Decimal('0.0'))
    ).order_by('creation_date')

    # 3. Calculate total continuation cost from the annotated batches
    total_continuation_cost = continuation_batches_with_costs.aggregate(
        total=Sum('continuation_cost')
    )['total'] or Decimal('0.0')

    # 4. Calculate the grand total cost for the entire plan
    total_plan_cost = main_plan_cost + total_continuation_cost
    # ==========================================================================

    context = {
        'active_page': 'shop_orders',
        'receipt': receipt,
        'production_plan': production_plan,
        'main_plan_cost': main_plan_cost,
        'continuation_batches_with_costs': continuation_batches_with_costs,
        'total_continuation_cost': total_continuation_cost,
        'total_plan_cost': total_plan_cost,
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/view_finished_product_content.html', context)
    return render(request, 'inventory/view_finished_product.html', context)