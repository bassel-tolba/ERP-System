import json
import logging
from datetime import datetime, time
from decimal import Decimal
from typing import List, Dict, Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum, F, Subquery, OuterRef, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import (
    Batch, BatchItem, InventoryLog, Product, FinishedProductReceipt,
    InventoryConsumption, ProductionReturn, InventoryAdjustment
)
from ..services import batch_service, costing_service
from ..services.batch_helpers import get_batch_form_context, check_and_update_batch_customization

ITEMS_PER_PAGE = 20
logger = logging.getLogger(__name__)


# --- Batch List View (No changes needed) ---
def batches(request: HttpRequest) -> HttpResponse:
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', 'active')

    base_queryset = Batch.objects.select_related('template__final_product')

    if status_filter == 'active':
        batch_list = base_queryset.exclude(status=Batch.Status.CANCELLED)
    else: # 'all'
        batch_list = base_queryset.all()

    if search_query:
        batch_list = batch_list.filter(
            Q(template__final_product__name__icontains=search_query) |
            Q(shop_order_number__icontains=search_query) |
            Q(batch_number__icontains=search_query)
        )
    
    paginator = Paginator(batch_list.order_by('-creation_date'), ITEMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page'))
    
    context = {
        'active_page': 'shop_orders',
        'batches': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    template = 'inventory/partials/batches_content.html' if 'X-Partial-Request' in request.headers else 'inventory/batches.html'
    return render(request, template, context)


# --- REFACTORED: Create Batch View ---
def create_batch(request: HttpRequest) -> HttpResponse:
    if request.method == 'POST':
        try:
            # 1. Parse and clean data from the request
            creation_date = datetime.strptime(request.POST.get('creation_date'), '%Y-%m-%d').date()
            
            items_data = []
            product_ids = request.POST.getlist('primitive_product_id')
            for i in range(len(product_ids)):
                if product_ids[i]:
                    items_data.append({
                        'product_id': int(product_ids[i]),
                        'theoretical_quantity': float(request.POST.getlist('theoretical_quantity')[i]),
                        'actual_quantity': float(request.POST.getlist('actual_quantity')[i]),
                        'source_log_id': int(request.POST.getlist('source_log_id')[i])
                    })

            # 2. Call the service function (Costing and JE are now internal to the service)
            batch = batch_service.create_batch(
                template_id=int(request.POST.get('template_id')),
                shop_order_number=request.POST.get('shop_order_number'),
                batch_number_from=request.POST.get('batch_number_from'),
                batch_number_to=request.POST.get('batch_number_to'),
                creation_date=creation_date,
                items_data=items_data,
                is_continuation='is_continuation' in request.POST,
                parent_batch_id=int(request.POST.get('parent_batch')) if request.POST.get('parent_batch') else None,
                notes=request.POST.get('notes', ''),
                machine_hours_consumed=float(request.POST.get('machine_hours_consumed')) if request.POST.get('machine_hours_consumed') else None,
                labor_hours_consumed=float(request.POST.get('labor_hours_consumed')) if request.POST.get('labor_hours_consumed') else None
            )

            # 3. Trigger side effects (Costing is now handled internally by service for atomicity. 
            # We remove the external recalculation call here.)
            
            messages.success(request, f"تم إنشاء مسودة أمر التشغيل '{batch.shop_order_number}' بنجاح.")
            return redirect('inventory:view_batch', pk=batch.pk)

        except (ValidationError, ValueError, TypeError) as e:
            logger.warning(f"Batch creation failed validation: {e}")
            messages.error(request, f"حدث خطأ في البيانات المدخلة: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating batch: {e}", exc_info=True)
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
        return redirect('inventory:create_batch')

    # For GET request
    context = {
        'active_page': 'shop_orders',
        **get_batch_form_context(),
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    template = 'inventory/partials/create_batch_content.html' if 'X-Partial-Request' in request.headers else 'inventory/create_batch.html'
    return render(request, template, context)


# --- REFACTORED: View Batch Details ---
def view_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch_info = get_object_or_404(Batch.objects.select_related('template__final_product', 'parent_batch'), pk=pk)
    
    # --- START: MODIFICATION - Fetch available stock for each item ---
    items = batch_info.items.select_related('primitive_product').order_by('primitive_product__name')
    
    # Subqueries for robust stock calculation
    consumed_prod_subquery = BatchItem.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('actual_quantity')).values('total')
    consumed_internal_subquery = InventoryConsumption.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity_consumed')).values('total')
    returned_subquery = ProductionReturn.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity')).values('total')
    adjusted_subquery = InventoryAdjustment.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('adjustment_quantity')).values('total')

    for item in items:
        # Find all released logs for this product
        released_logs = InventoryLog.objects.filter(
            product=item.primitive_product,
            status=InventoryLog.Status.RELEASED
        ).annotate(
            total_used_in_prod=Coalesce(Subquery(consumed_prod_subquery, output_field=FloatField()), 0.0),
            total_used_in_consumption=Coalesce(Subquery(consumed_internal_subquery, output_field=FloatField()), 0.0),
            total_returned=Coalesce(Subquery(returned_subquery, output_field=FloatField()), 0.0),
            total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
        ).annotate(
            remaining_quantity=F('quantity') - F('total_used_in_prod') - F('total_used_in_consumption') + F('total_returned') + F('total_adjusted')
        ).order_by('release_timestamp')
        
        # Create a list of dicts to be compatible with the template
        item.available_stock = [
            {
                'id': log.id,
                'qc_no': log.qc_no,
                'remaining_quantity': log.remaining_quantity,
                'timestamp': log.release_timestamp or log.timestamp
            } for log in released_logs if log.remaining_quantity > 0.001 or log.id == item.source_log_id
        ]
        
        # Ensure the currently selected source is in the list, even if its stock is now zero
        if item.source_log and not any(s['id'] == item.source_log.id for s in item.available_stock):
            item.available_stock.insert(0, {
                'id': item.source_log.id,
                'qc_no': item.source_log.qc_no,
                'remaining_quantity': 0,
                'timestamp': item.source_log.release_timestamp or item.source_log.timestamp
            })
    # --- END: MODIFICATION ---

    # This presentation logic is complex but specific to this view, so it remains here.
    # It could be moved to a helper if reused elsewhere.
    individual_batch_numbers_in_plan = []
    batch_from = ''
    batch_to = ''
    if batch_info.batch_number:
        parts = str(batch_info.batch_number).split('-')
        if parts:
            batch_from = ''.join(filter(str.isdigit, parts[0]))
        if len(parts) > 1:
            batch_to = ''.join(filter(str.isdigit, parts[1]))
        
        try:
            start_num = int(batch_from) if batch_from else 0
            prefix = parts[0].replace(str(start_num), '') if batch_from else parts[0]
            if batch_to:
                end_num = int(batch_to)
                if end_num >= start_num:
                    individual_batch_numbers_in_plan = [f"{prefix}{i}" for i in range(start_num, end_num + 1)]
            else:
                individual_batch_numbers_in_plan.append(batch_info.batch_number)
        except (ValueError, IndexError):
            individual_batch_numbers_in_plan.append(batch_info.batch_number)

    num_batches = len(individual_batch_numbers_in_plan) or 1
    
    received_receipts = {r.individual_batch_number: r for r in FinishedProductReceipt.objects.filter(batch=batch_info)}
    plan_status_list = [{'number': num, 'status': 'RECEIVED' if received_receipts.get(num) else 'PENDING', 'receipt': received_receipts.get(num)} for num in individual_batch_numbers_in_plan]

    total_batch_cost = sum(
        (Decimal(str(item.actual_quantity or 0.0)) * (item.cost_at_consumption or Decimal('0.0')))
        for item in batch_info.items.all()
    )
    
    # --- START: MODIFICATION - Add primitive products for the modal ---
    primitive_products = Product.objects.filter(
        product_type__in=[Product.ProductType.RAW_MATERIAL, Product.ProductType.PACKAGING]
    ).order_by('name')
    # --- END: MODIFICATION ---

    # Fetch related production returns
    related_returns = batch_info.production_returns.select_related('product', 'source_log').all()

    context = {
        'active_page': 'shop_orders',
        'batch': batch_info,
        'items': items, # Use the modified items list
        'total_batch_cost': total_batch_cost,
        'plan_status_list': plan_status_list,
        'available_parent_batches': Batch.objects.select_related('template__final_product').exclude(pk=pk).order_by('-creation_date'),
        'primitive_products': primitive_products, # Add this for the modal
        'related_returns': related_returns,
        'is_partial_request': 'X-Partial-Request' in request.headers,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'batch_from': batch_from,
        'batch_to': batch_to,
    }
    template = 'inventory/partials/batch_view_content.html' if 'X-Partial-Request' in request.headers else 'inventory/batch_view.html'
    return render(request, template, context)


# --- REFACTORED: Update Batch View ---
@require_POST
def update_batch_items_bulk(request: HttpRequest, batch_pk: int) -> HttpResponse:
    batch = get_object_or_404(Batch, pk=batch_pk)
    try:
        # 1. Parse and clean data
        creation_date = datetime.strptime(request.POST.get('creation_date'), '%Y-%m-%d').date()
        
        items_data = []
        item_ids = request.POST.getlist('item_id')
        all_products_in_batch = {item.id: item.primitive_product_id for item in batch.items.all()}
        
        for item_id_str in item_ids:
            item_id = int(item_id_str)
            items_data.append({
                'item_id': item_id,
                'product_id': all_products_in_batch.get(item_id),
                'theoretical_quantity': float(request.POST.get(f'theoretical_quantity_{item_id}')),
                'actual_quantity': float(request.POST.get(f'actual_quantity_{item_id}')),
                'source_log_id': int(request.POST.get(f'source_log_id_{item_id}')) if request.POST.get(f'source_log_id_{item_id}') else None
            })

        # 2. Call the service function (Costing and JE are now internal to the service)
        recalc_start_date = batch_service.update_batch(
            batch=batch,
            shop_order_number=request.POST.get('shop_order_number'),
            creation_date=creation_date,
            batch_number_from=request.POST.get('batch_number_from'),
            batch_number_to=request.POST.get('batch_number_to'),
            items_data=items_data,
            is_continuation='is_continuation' in request.POST,
            parent_batch_id=int(request.POST.get('parent_batch')) if request.POST.get('parent_batch') else None,
            notes=request.POST.get('notes', ''),
            machine_hours_consumed=float(request.POST.get('machine_hours_consumed')) if request.POST.get('machine_hours_consumed') else None,
            labor_hours_consumed=float(request.POST.get('labor_hours_consumed')) if request.POST.get('labor_hours_consumed') else None
        )

        # 3. Trigger side effects (Costing handled internally, removed external call)
        
        messages.success(request, "تم حفظ جميع التعديلات وتحديث التكاليف بنجاح.")

    except (ValidationError, ValueError, TypeError) as e:
        logger.warning(f"Batch {batch_pk} update failed validation: {e}")
        messages.error(request, f"حدث خطأ في البيانات المدخلة: {e}")
    except Exception as e:
        logger.error(f"Unexpected error updating batch {batch_pk}: {e}", exc_info=True)
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
    return redirect('inventory:view_batch', pk=batch_pk)


# --- REFACTORED: Add Batch Item View ---
@require_POST
def add_batch_item(request: HttpRequest, batch_pk: int) -> HttpResponse:
    batch = get_object_or_404(Batch, pk=batch_pk)
    try:
        product_id = int(request.POST.get('primitive_product_id'))
        theoretical_quantity = float(request.POST.get('theoretical_quantity', 0))
        actual_quantity = float(request.POST.get('actual_quantity', 0))
        source_log_id = int(request.POST.get('source_log_id')) if request.POST.get('source_log_id') else None
        
        new_item = batch_service.add_item_to_batch(
            batch=batch, 
            product_id=product_id, 
            theoretical_quantity=theoretical_quantity,
            actual_quantity=actual_quantity,
            source_log_id=source_log_id
        )
        
        # Costing handled internally by the service for atomicity, removing external call.
        
        messages.success(request, "تمت إضافة المادة وتحديث التكاليف.")
    except (ValidationError, ValueError) as e:
        messages.warning(request, str(e))
    except Exception as e:
        logger.error(f"Error adding item to batch {batch_pk}: {e}", exc_info=True)
        messages.error(request, f"حدث خطأ أثناء إضافة المادة: {e}")
    return redirect('inventory:view_batch', pk=batch_pk)


# --- BATCH WORKFLOW ACTIONS ---

@require_POST
def submit_batch_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles submitting a batch for approval.
    """
    batch = get_object_or_404(Batch, pk=pk)
    try:
        batch_service.submit_batch_for_approval(batch, request.user)
        messages.success(request, "تم إرسال أمر التشغيل للموافقة.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"لا يمكن إرسال أمر التشغيل: {e}")
    return redirect('inventory:view_batch', pk=pk)


@require_POST
def approve_batch_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles approving a batch.
    """
    batch = get_object_or_404(Batch, pk=pk)
    try:
        batch_service.approve_batch(batch, request.user)
        messages.success(request, "تمت الموافقة على أمر التشغيل.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"لا يمكن الموافقة على أمر التشغيل: {e}")
    return redirect('inventory:view_batch', pk=pk)


@require_POST
def reject_batch_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles rejecting a batch and returning it to Draft status.
    """
    batch = get_object_or_404(Batch, pk=pk)
    justification = request.POST.get('justification', '')
    if not justification:
        messages.error(request, "سبب الإرجاع مطلوب.")
        return redirect('inventory:view_batch', pk=pk)
    try:
        batch_service.reject_batch(batch, request.user, justification)
        messages.info(request, "تم إرجاع أمر التشغيل إلى مسودة.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"لا يمكن إرجاع أمر التشغيل: {e}")
    return redirect('inventory:view_batch', pk=pk)


@require_POST
def start_production_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles starting production for an approved batch.
    """
    batch = get_object_or_404(Batch, pk=pk)
    try:
        batch_service.start_batch_production(batch)
        messages.success(request, "تم بدء الإنتاج لأمر التشغيل.")
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"لا يمكن بدء الإنتاج: {e}")
    return redirect('inventory:view_batch', pk=pk)


# --- REFACTORED: Delete Batch Item View ---
@require_POST
def return_batch_item_view(request: HttpRequest, item_pk: int) -> HttpResponse:
    """
    Handles returning a component from a batch back to inventory via the batch service.
    """
    item = get_object_or_404(BatchItem, pk=item_pk)
    batch_id = item.batch.id
    try:
        quantity = float(request.POST.get('quantity', 0))
        return_date_str = request.POST.get('return_date')
        notes = request.POST.get('notes', '')

        if not return_date_str or quantity <= 0:
            raise ValidationError("Return date and a positive quantity are required.")

        return_date = datetime.strptime(return_date_str, '%Y-%m-%d').date()

        batch_service.return_item_from_batch(
            item=item,
            quantity=quantity,
            return_date=return_date,
            notes=notes
        )
        messages.info(request, "تم إرجاع المادة من أمر التشغيل بنجاح.")
    except (ValidationError, ValueError) as e:
        messages.error(request, f"حدث خطأ أثناء الإرجاع: {e}")
    except Exception as e:
        logger.error(f"Error returning batch item {item_pk}: {e}", exc_info=True)
        messages.error(request, f"حدث خطأ غير متوقع أثناء الإرجاع: {e}")
    return redirect('inventory:view_batch', pk=batch_id)


# --- REFACTORED: Delete Batch View ---
@require_POST
def cancel_batch_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles cancelling a batch non-destructively by calling the batch service.
    """
    batch = get_object_or_404(Batch, pk=pk)
    justification = request.POST.get('justification', '')

    if not justification:
        messages.error(request, "سبب الإلغاء مطلوب.")
        return redirect('inventory:view_batch', pk=pk)

    try:
        batch_service.cancel_batch(
            batch=batch,
            user=request.user,
            justification=justification
        )
        messages.info(request, 'تم إلغاء أمر التشغيل وتحديث التكاليف بنجاح.')
        return redirect('inventory:batches')
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"لا يمكن إلغاء أمر التشغيل: {e}")
        return redirect('inventory:view_batch', pk=pk)