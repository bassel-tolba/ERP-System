# gipcco_project/inventory/services/batch_helpers.py

import logging
from datetime import datetime
from typing import List, Dict, Any

from django.db.models import Sum, Q, F, FloatField
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import (
    Batch, BatchItem, InventoryLog, Product, ShopOrderTemplate
)

logger = logging.getLogger(__name__)


def get_batch_form_context() -> Dict[str, Any]:
    """
    Prepares all necessary data for rendering the create_batch form.
    This includes templates, available stock for each product, and other form choices.
    """
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
        # Correctly calculate remaining quantity for each released log
        inventory_logs = prod.inventory_logs.filter(status=InventoryLog.Status.RELEASED).annotate(
            total_used=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
            total_returned=Coalesce(Sum('production_returns__quantity'), 0.0, output_field=FloatField()),
            total_consumed=Coalesce(Sum('consumptions__quantity_consumed'), 0.0, output_field=FloatField()),
            total_adjusted=Coalesce(Sum('adjustments__adjustment_quantity'), 0.0, output_field=FloatField())
        ).annotate(
            remaining_quantity=F('quantity') - F('total_used') - F('total_consumed') + F('total_returned') + F('total_adjusted')
        )
        
        for log in inventory_logs:
            if log.remaining_quantity > 0.001:
                stock_list.append({
                    'id': log.id, 
                    'qc_no': log.qc_no or 'N/A', 
                    'timestamp': log.release_timestamp, 
                    'remaining_quantity': log.remaining_quantity
                })
        
        stock_list.sort(key=lambda x: x['timestamp'])
        all_available_stock[prod.id] = stock_list

    json_stock = {
        pid: [
            {
                'id': s['id'], 
                'qc_no': s['qc_no'], 
                'timestamp': s['timestamp'].strftime('%Y-%m-%d'), 
                'remaining_quantity': "%.3f" % s['remaining_quantity']
            } for s in stock_list
        ] for pid, stock_list in all_available_stock.items()
    }
    
    primitive_products_for_json = list(primitive_products.values('id', 'name', 'code', 'unit'))

    return {
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'templates': templates,
        'templates_with_items': templates_with_items,
        'all_available_stock': json_stock,
        'primitive_products': primitive_products,
        'primitive_products_json': primitive_products_for_json,
        'batches': Batch.objects.select_related('template__final_product').all(),
    }


def validate_stock_availability(
    product_ids: List[int], 
    actual_quantities: List[float], 
    source_log_ids: List[int], 
    batch_creation_date: datetime.date, 
    batch_id_to_exclude: int = None
) -> (bool, str):
    """
    Validates stock availability by first aggregating all requests from the same source.
    Ensures that stock is 'RELEASED' and that its release date is not after the consumption date.
    """
    requests = {}
    # Step 1: Aggregate all requested quantities by their source.
    for i, source_id in enumerate(source_log_ids):
        if not all([source_id, product_ids[i], actual_quantities[i]]):
            continue
        
        quantity = float(actual_quantities[i])
        product_id = int(product_ids[i])
            
        request_key = (source_id, product_id)
        requests[request_key] = requests.get(request_key, 0.0) + quantity

    # Step 2: Validate each aggregated request against the available stock.
    for request_key, total_requested in requests.items():
        source_id, product_id = request_key
        try:
            product = Product.objects.get(pk=product_id)
            log_entry = InventoryLog.objects.get(pk=source_id)
        except (Product.DoesNotExist, InventoryLog.DoesNotExist):
            return False, f"المنتج أو مصدر المخزون برقم {product_id}/{source_id} غير موجود."

        # --- Validation Checks ---
        if log_entry.status != InventoryLog.Status.RELEASED:
            return False, f"خطأ في مادة '{log_entry.product.name}': المصدر (QC: {log_entry.qc_no or 'N/A'}) لم يتم الإفراج عنه بعد."
        
        if not log_entry.release_timestamp or log_entry.release_timestamp.date() > batch_creation_date:
            return False, f"خطأ في مادة '{log_entry.product.name}': تاريخ الإفراج عن المصدر ({log_entry.release_timestamp.date()}) أحدث من تاريخ أمر التشغيل ({batch_creation_date})."
        
        if product_id != log_entry.product_id:
            return False, f"عدم تطابق المنتج. تم طلب '{product.name}' من مصدر QC '{log_entry.qc_no}' الذي يخص منتج '{log_entry.product.name}'."

        # --- Calculate Available Stock ---
        used_items_qs = BatchItem.objects.filter(source_log_id=source_id)
        if batch_id_to_exclude:
            used_items_qs = used_items_qs.exclude(batch_id=batch_id_to_exclude)

        already_used = used_items_qs.aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
        total_returned = log_entry.production_returns.aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
        
        available_stock = float(log_entry.quantity) - already_used + total_returned

        if total_requested > available_stock + 0.001: # Tolerance for float comparison
            return False, f"كمية غير كافية للمنتج '{product.name}' من المصدر QC '{log_entry.qc_no}'. مطلوب: {total_requested:.3f}, متاح: {available_stock:.3f}"

    return True, None


def check_and_update_batch_customization(batch_id: int):
    """
    Checks if a batch's items deviate from its template, updating the `is_customized` flag.
    """
    try:
        batch = Batch.objects.select_related('template').get(pk=batch_id)
        template_item_count = batch.template.items.count()
        batch_item_count = batch.items.count()

        is_customized = False
        if template_item_count != batch_item_count:
            is_customized = True
        else:
            if batch.items.filter(~Q(actual_quantity=F('theoretical_quantity'))).exists():
                is_customized = True
        
        if batch.is_customized != is_customized:
            batch.is_customized = is_customized
            batch.save(update_fields=['is_customized'])
    except Batch.DoesNotExist:
        logger.warning(f"Attempted to check customization for non-existent batch_id: {batch_id}")