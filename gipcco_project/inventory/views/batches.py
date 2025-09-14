# gipcco_project/inventory/views/batches.py

import json
import math
from datetime import datetime, timedelta, time
from decimal import Decimal

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q, F, FloatField, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
import logging

from ..models import (Batch, BatchItem, Company, InventoryLog, OpeningBalance,
                     Product, ProductionReturn, ShopOrderTemplate, TemplateItem, FinishedProductReceipt)
from .helpers import check_and_update_batch_customization, validate_stock_availability
# --- MODIFIED: Import from the new costing service ---
from ..services.costing_service import recalculate_cost_history_for_product

ITEMS_PER_PAGE = 20

logger = logging.getLogger(__name__)

# --- Batch Views ---

def batches(request: HttpRequest) -> HttpResponse:
    """
    Displays a paginated list of all batches, with search functionality.
    """
    search_query = request.GET.get('q', '').strip()
    
    batch_list = Batch.objects.select_related('template__final_product').all()
    
    if search_query:
        batch_list = batch_list.filter(
            Q(template__final_product__name__icontains=search_query) |
            Q(shop_order_number__icontains=search_query) |
            Q(batch_number__icontains=search_query)
        )
        
    paginator = Paginator(batch_list, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'active_page': 'shop_orders',
        'batches': page_obj,
        'search_query': search_query,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/batches_content.html', context)
    return render(request, 'inventory/batches.html', context)


def create_batch(request: HttpRequest) -> HttpResponse:
    """
    Handles creation of a new production batch.
    """
    def get_page_data():
        templates = ShopOrderTemplate.objects.select_related('final_product').prefetch_related('items__primitive_product').all()
        templates_with_items = {
            t.id: [
                {
                    'primitive_product_id': item.primitive_product.id,
                    'name': item.primitive_product.name,
                    'unit': item.primitive_product.unit,
                    'theoretical_quantity': item.theoretical_quantity
                } for item in t.items.all()
            ] for t in templates
        }
        all_available_stock = {}
        primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
        for prod in primitive_products:
            stock_list = []
            latest_balance = prod.opening_balances.order_by('-balance_date').first()
            if latest_balance:
                used_from_ob = BatchItem.objects.filter(
                    primitive_product=prod, source_type=BatchItem.SourceType.OPENING_BALANCE
                ).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
                remaining_ob_qty = latest_balance.quantity - used_from_ob
                if remaining_ob_qty > 0.001:
                    # --- MODIFIED: Use release_timestamp for sorting consistency ---
                    stock_list.append({'id': -1, 'qc_no': 'رصيد افتتاحي', 'timestamp': latest_balance.balance_date, 'remaining_quantity': remaining_ob_qty})
            
            # --- MODIFIED: Only fetch RELEASED inventory logs ---
            inventory_logs = prod.inventory_logs.filter(status=InventoryLog.Status.RELEASED).annotate(
                total_used=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
                total_returned=Coalesce(Sum('production_returns__quantity'), 0.0, output_field=FloatField())
            ).annotate(
                remaining_quantity=F('quantity') - F('total_used') + F('total_returned')
            )
            for log in inventory_logs:
                if log.remaining_quantity > 0.001:
                    # --- MODIFIED: Use release_timestamp for sorting ---
                    stock_list.append({'id': log.id, 'qc_no': log.qc_no or 'N/A', 'timestamp': log.release_timestamp, 'remaining_quantity': log.remaining_quantity})
            
            stock_list.sort(key=lambda x: x['timestamp'])
            all_available_stock[prod.id] = stock_list
        return {
            'templates': templates, 
            'templates_with_items': templates_with_items, 
            'all_available_stock': all_available_stock,
            'primitive_products': primitive_products,
            'batches': Batch.objects.select_related('template__final_product').all() # Add all batches for parent selection
        }

    if request.method == 'POST':
        template_id = request.POST.get('template_id')
        shop_order_number = request.POST.get('shop_order_number')
        batch_from_str = request.POST.get('batch_number_from')
        batch_to_str = request.POST.get('batch_number_to')
        creation_date_str = request.POST.get('creation_date')
        is_continuation = 'is_continuation' in request.POST
        parent_batch_id = request.POST.get('parent_batch') # Get parent batch ID
        notes = request.POST.get('notes', '')
        product_ids = request.POST.getlist('primitive_product_id')
        theoretical_quantities = request.POST.getlist('theoretical_quantity')
        actual_quantities = request.POST.getlist('actual_quantity')
        source_log_ids = request.POST.getlist('source_log_id')

        if not all([template_id, shop_order_number, batch_from_str, creation_date_str, product_ids]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول وتحميل قالب أولاً.")
            return redirect('inventory:create_batch')

        try:
            creation_date_for_validation = datetime.strptime(creation_date_str, '%Y-%m-%d').date()
            creation_datetime = timezone.make_aware(datetime.combine(creation_date_for_validation, time.min))
        except (ValueError, TypeError):
            messages.error(request, 'تاريخ الإنشاء غير صالح.')
            return redirect('inventory:create_batch')

        is_valid, error_msg = validate_stock_availability(
            product_ids, actual_quantities, source_log_ids, creation_date_for_validation
        )
        if not is_valid:
            messages.error(request, error_msg)
            return redirect('inventory:create_batch')
        
        try:
            batch = None
            with transaction.atomic():
                final_batch_number_str = batch_from_str
                if batch_to_str and batch_to_str.strip() and int(batch_to_str) >= int(batch_from_str):
                    final_batch_number_str = f"{batch_from_str}-{batch_to_str}"
                
                batch = Batch.objects.create(
                    template_id=template_id,
                    shop_order_number=shop_order_number,
                    batch_number=final_batch_number_str,
                    creation_date=creation_datetime, # Use datetime object
                    is_customized=True,
                    is_continuation=is_continuation,
                    parent_batch_id=parent_batch_id if is_continuation and parent_batch_id else None, # Set parent batch
                    notes=notes
                )
                items_to_create = []
                for pid, t_qty, a_qty, src_id_str in zip(product_ids, theoretical_quantities, actual_quantities, source_log_ids):
                    if pid and t_qty and a_qty and src_id_str:
                        source_id_from_form = int(src_id_str)
                        source_type = BatchItem.SourceType.OPENING_BALANCE if source_id_from_form == -1 else BatchItem.SourceType.INVENTORY_LOG
                        source_log_id = None if source_id_from_form == -1 else source_id_from_form
                        items_to_create.append(BatchItem(
                            batch=batch,
                            primitive_product_id=int(pid),
                            theoretical_quantity=float(t_qty),
                            actual_quantity=float(a_qty),
                            source_type=source_type,
                            source_log_id=source_log_id
                        ))
                BatchItem.objects.bulk_create(items_to_create)

            # --- COSTING ENGINE TRIGGER ---
            product_ids_to_recalc = {int(pid) for pid in product_ids if pid}
            for pid in product_ids_to_recalc:
                recalculate_cost_history_for_product(pid, creation_datetime)
            
            messages.success(request, f"تم إنشاء أمر التشغيل '{shop_order_number}' وتحديث التكاليف بنجاح.")
            return redirect('inventory:view_batch', pk=batch.pk)
        except Exception as e:
            logger.error(f"Error creating batch: {e}", exc_info=True)
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
            return redirect('inventory:create_batch')

    page_data = get_page_data()
    json_stock = {pid: [{'id': s['id'], 'qc_no': s['qc_no'], 'timestamp': s['timestamp'].strftime('%Y-%m-%d'), 'remaining_quantity': "%.3f" % s['remaining_quantity']} for s in stock_list] for pid, stock_list in page_data['all_available_stock'].items()}
    primitive_products_for_json = list(page_data['primitive_products'].values('id', 'name', 'code', 'unit'))
    context = {
        'active_page': 'shop_orders',
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'templates': page_data['templates'],
        'templates_with_items': page_data['templates_with_items'],
        'all_available_stock': json_stock,
        'primitive_products': page_data['primitive_products'],
        'primitive_products_json': primitive_products_for_json,
        'batches': page_data['batches'], # Pass all batches to the template
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/create_batch_content.html', context)
    return render(request, 'inventory/create_batch.html', context)


def view_batch(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single batch, allowing for edits.
    """
    batch_info = get_object_or_404(Batch.objects.select_related('template__final_product', 'parent_batch'), pk=pk)
    
    # --- MODIFIED: Logic to handle batch ranges for receiving finished products ---
    batch_from, batch_to = None, None
    individual_batch_numbers_in_plan = []
    
    if batch_info.batch_number:
        parts = str(batch_info.batch_number).split('-')
        try:
            # Attempt to parse start and end as integers for ranging
            start_num_str = ''.join(filter(str.isdigit, parts[0]))
            start_num = int(start_num_str)
            prefix = parts[0].replace(start_num_str, '')

            if len(parts) > 1 and parts[1]:
                end_num_str = ''.join(filter(str.isdigit, parts[1]))
                end_num = int(end_num_str)
                batch_from = parts[0]
                batch_to = parts[1]
                if end_num >= start_num:
                    for i in range(start_num, end_num + 1):
                        individual_batch_numbers_in_plan.append(f"{prefix}{i}")
            else:
                 batch_from = batch_info.batch_number
                 individual_batch_numbers_in_plan.append(batch_info.batch_number)
        except (ValueError, IndexError):
            # Fallback for non-standard batch numbers
            batch_from = batch_info.batch_number
            individual_batch_numbers_in_plan.append(batch_info.batch_number)

    num_batches = len(individual_batch_numbers_in_plan) if len(individual_batch_numbers_in_plan) > 0 else 1
    
    # Check status of each individual batch in the plan
    received_receipts = {
        r.individual_batch_number: r 
        for r in FinishedProductReceipt.objects.filter(batch=batch_info)
    }
    
    plan_status_list = []
    for num_str in individual_batch_numbers_in_plan:
        receipt = received_receipts.get(num_str)
        plan_status_list.append({
            'number': num_str,
            'status': 'RECEIVED' if receipt else 'PENDING',
            'receipt': receipt
        })
    # --- END MODIFICATION ---

    batch_items_with_stock = []
    total_batch_cost = Decimal('0.0')
    batch_items = batch_info.items.select_related('primitive_product').order_by('primitive_product__name')

    for item in batch_items:
        item_cost = item.cost_at_consumption or Decimal('0.0')
        item_qty = Decimal(str(item.actual_quantity or 0.0))
        item.line_total = item_qty * item_cost
        total_batch_cost += item.line_total
        item.base_theoretical_quantity = item.theoretical_quantity / num_batches
        item.base_actual_quantity = (item.actual_quantity or 0) / num_batches
        product = item.primitive_product
        available_stock_rows = []
        latest_balance = product.opening_balances.order_by('-balance_date').first()
        if latest_balance:
            used_from_ob = BatchItem.objects.filter(primitive_product=product, source_type=BatchItem.SourceType.OPENING_BALANCE).exclude(pk=item.pk).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            remaining_ob_qty = latest_balance.quantity - used_from_ob
            if remaining_ob_qty > 0.001 or item.source_type == BatchItem.SourceType.OPENING_BALANCE:
                available_stock_rows.append({'id': -1, 'qc_no': 'رصيد افتتاحي', 'timestamp': latest_balance.balance_date, 'remaining_quantity': remaining_ob_qty})
        
        # --- MODIFIED: Only query RELEASED logs for available stock ---
        all_logs = product.inventory_logs.filter(status=InventoryLog.Status.RELEASED)
        for log in all_logs:
            used_from_log = BatchItem.objects.filter(source_log=log).exclude(pk=item.pk).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            returned_to_log = log.production_returns.aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
            remaining_log_qty = log.quantity - used_from_log + returned_to_log
            if remaining_log_qty > 0.001 or item.source_log_id == log.id:
                # --- MODIFIED: Use release_timestamp for sorting ---
                available_stock_rows.append({'id': log.id, 'qc_no': log.qc_no, 'timestamp': log.release_timestamp, 'remaining_quantity': remaining_log_qty})
        
        item.available_stock = sorted(available_stock_rows, key=lambda x: x['timestamp'])
        batch_items_with_stock.append(item)
    
    # --- START OF MODIFICATION: Provide batches for parent selection ---
    # A batch cannot be its own parent.
    available_parent_batches = Batch.objects.select_related(
        'template__final_product'
    ).exclude(pk=pk).order_by('-creation_date')
    # --- END OF MODIFICATION ---

    context = {
        'active_page': 'shop_orders',
        'batch': batch_info,
        'items': batch_items_with_stock,
        'total_batch_cost': total_batch_cost,
        'primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'batch_from': batch_from,
        'batch_to': batch_to,
        'plan_status_list': plan_status_list, # --- NEW CONTEXT VARIABLE ---
        'available_parent_batches': available_parent_batches, # --- NEW CONTEXT VARIABLE ---
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/batch_view_content.html', context)
    return render(request, 'inventory/batch_view.html', context)


@require_POST
def delete_batch(request: HttpRequest, pk: int) -> HttpResponse:
    batch = get_object_or_404(Batch.objects.prefetch_related('items'), pk=pk)
    
    # --- COSTING ENGINE TRIGGER ---
    product_ids_to_recalc = {item.primitive_product_id for item in batch.items.all()}
    recalc_start_date = batch.creation_date
    
    batch.delete()
    
    for pid in product_ids_to_recalc:
        recalculate_cost_history_for_product(pid, recalc_start_date)

    messages.info(request, 'تم حذف أمر التشغيل وتحديث التكاليف بنجاح.')
    return redirect('inventory:batches')


@require_POST
def add_batch_item(request: HttpRequest, batch_pk: int) -> HttpResponse:
    batch = get_object_or_404(Batch, pk=batch_pk)
    try:
        product_id = request.POST.get('primitive_product_id')
        theoretical_quantity = float(request.POST.get('theoretical_quantity', 0))
        if not product_id or theoretical_quantity <= 0:
            messages.warning(request, "الرجاء اختيار منتج وتحديد كمية صالحة.")
            return redirect('inventory:view_batch', pk=batch_pk)
        
        BatchItem.objects.create(
            batch=batch,
            primitive_product_id=product_id,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=theoretical_quantity,
            source_type=BatchItem.SourceType.INVENTORY_LOG,
            source_log=None
        )
        check_and_update_batch_customization(batch_pk)

        # --- COSTING ENGINE TRIGGER ---
        recalculate_cost_history_for_product(int(product_id), batch.creation_date)
        
        messages.success(request, "تمت إضافة المادة وتحديث التكاليف.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إضافة المادة: {e}")
    return redirect('inventory:view_batch', pk=batch_pk)


@require_POST
def update_batch_items_bulk(request: HttpRequest, batch_pk: int) -> HttpResponse:
    batch = get_object_or_404(Batch, pk=batch_pk)
    original_creation_date = batch.creation_date
    
    shop_order_number = request.POST.get('shop_order_number')
    creation_date_str = request.POST.get('creation_date')
    batch_from_str = request.POST.get('batch_number_from')
    batch_to_str = request.POST.get('batch_number_to')
    is_continuation = 'is_continuation' in request.POST
    # --- START OF MODIFICATION: Get parent batch ID from form ---
    parent_batch_id = request.POST.get('parent_batch')
    # --- END OF MODIFICATION ---
    notes = request.POST.get('notes', '')

    if not all([shop_order_number, creation_date_str, batch_from_str]):
        messages.error(request, "الرجاء تعبئة بيانات أمر التشغيل الأساسية (رقم الأمر، التاريخ، رقم التشغيلة).")
        return redirect('inventory:view_batch', pk=batch_pk)

    item_ids = request.POST.getlist('item_id')
    items_in_db = {str(item.id): item for item in BatchItem.objects.filter(id__in=item_ids)}
    original_product_ids = {item.primitive_product_id for item in items_in_db.values()}

    product_ids_for_validation = []
    actual_quantities_for_validation = []
    source_log_ids_for_validation = []

    for item_id in item_ids: 
        if item_id in items_in_db:
            item = items_in_db[item_id]
            product_ids_for_validation.append(item.primitive_product_id)
            actual_qty = request.POST.get(f'actual_quantity_{item_id}', '0')
            source_id = request.POST.get(f'source_log_id_{item_id}', '')
            actual_quantities_for_validation.append(actual_qty)
            source_log_ids_for_validation.append(source_id)

    try:
        creation_date_for_validation = datetime.strptime(creation_date_str, '%Y-%m-%d').date()
        creation_datetime = timezone.make_aware(datetime.combine(creation_date_for_validation, time.min))
    except (ValueError, TypeError):
        messages.error(request, 'تاريخ الإنشاء غير صالح.')
        return redirect('inventory:view_batch', pk=batch_pk)

    is_valid, error_msg = validate_stock_availability(
        product_ids_for_validation, 
        actual_quantities_for_validation, 
        source_log_ids_for_validation, 
        creation_date_for_validation, 
        batch_id_to_exclude=batch_pk
    )
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('inventory:view_batch', pk=batch_pk)

    try:
        with transaction.atomic():
            final_batch_number_str = batch_from_str
            if batch_to_str and batch_to_str.strip() and int(batch_to_str) >= int(batch_from_str):
                final_batch_number_str = f"{batch_from_str}-{batch_to_str}"
            batch.shop_order_number = shop_order_number
            batch.creation_date = creation_datetime
            batch.batch_number = final_batch_number_str
            batch.is_continuation = is_continuation
            batch.notes = notes
            
            # --- START OF MODIFICATION: Update parent batch ---
            if is_continuation and parent_batch_id:
                batch.parent_batch_id = parent_batch_id
            else:
                batch.parent_batch = None # Clear parent if it's not a continuation
            # --- END OF MODIFICATION ---

            batch.save()

            for item_id in item_ids:
                item = items_in_db.get(item_id)
                if not item: continue
                theoretical_qty = request.POST.get(f'theoretical_quantity_{item_id}')
                actual_qty = request.POST.get(f'actual_quantity_{item_id}')
                source_id_str = request.POST.get(f'source_log_id_{item_id}')
                item.theoretical_quantity = float(theoretical_qty or 0)
                item.actual_quantity = float(actual_qty or 0)
                if source_id_str:
                    source_id_from_form = int(source_id_str)
                    item.source_type = BatchItem.SourceType.OPENING_BALANCE if source_id_from_form == -1 else BatchItem.SourceType.INVENTORY_LOG
                    item.source_log_id = None if source_id_from_form == -1 else source_id_from_form
                else:
                    item.source_log_id = None
                item.save()

        check_and_update_batch_customization(batch_pk)
        
        # --- COSTING ENGINE TRIGGER ---
        all_affected_product_ids = original_product_ids.union(product_ids_for_validation)
        recalc_start_date = min(original_creation_date, creation_datetime)
        for pid in all_affected_product_ids:
            recalculate_cost_history_for_product(int(pid), recalc_start_date)

        messages.success(request, "تم حفظ جميع التعديلات وتحديث التكاليف بنجاح.")
    except Exception as e:
        logger.error(f"Error updating batch {batch_pk}: {e}", exc_info=True)
        messages.error(request, f"حدث خطأ أثناء حفظ التعديلات: {e}")
        
    return redirect('inventory:view_batch', pk=batch_pk)

@require_POST
def delete_batch_item(request: HttpRequest, item_pk: int) -> HttpResponse:
    item = get_object_or_404(BatchItem, pk=item_pk)
    batch_id = item.batch.id
    
    # --- COSTING ENGINE TRIGGER ---
    product_id_to_recalc = item.primitive_product_id
    recalc_start_date = item.batch.creation_date

    try:
        item.delete()
        check_and_update_batch_customization(batch_id)
        recalculate_cost_history_for_product(product_id_to_recalc, recalc_start_date)
        messages.info(request, "تم حذف المادة وتحديث التكاليف.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء الحذف: {e}")
    return redirect('inventory:view_batch', pk=batch_id)