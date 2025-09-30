# gipcco_project/inventory/views/helpers.py

import json
import math
from datetime import datetime, timedelta, time
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Sum, Q, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
import logging

from ..models import (Batch, BatchItem, Company, InventoryLog,
                     Product, ProductionReturn, ShopOrderTemplate, TemplateItem,
                     InventoryConsumption)

# Get an instance of the logger for this module
logger = logging.getLogger(__name__)


# ==============================================================================
#  Operational Helper Functions
# ==============================================================================

def check_and_update_batch_customization(batch_id: int):
    """
    Checks if a batch's items deviate from its template's theoretical quantities
    or item count, and updates the `is_customized` flag accordingly.
    """
    try:
        batch = Batch.objects.select_related('template').get(pk=batch_id)
        template_item_count = batch.template.items.count()
        batch_item_count = batch.items.count()

        is_customized = False
        if template_item_count != batch_item_count:
            is_customized = True
        else:
            # Check if any item's actual quantity differs from its theoretical quantity
            if batch.items.filter(~Q(actual_quantity=F('theoretical_quantity'))).exists():
                is_customized = True
        
        if batch.is_customized != is_customized:
            batch.is_customized = is_customized
            batch.save(update_fields=['is_customized'])
    except Batch.DoesNotExist:
        logger.warning(f"Attempted to check customization for non-existent batch_id: {batch_id}")
        pass


def validate_stock_availability(product_ids, actual_quantities, source_log_ids, batch_creation_date, batch_id_to_exclude=None):
    """
    Validates stock availability by first aggregating all requests from the same source.
    Ensures that stock is 'RELEASED' and that its release date is not after the consumption date.
    - `batch_creation_date` is expected to be a `datetime.date` object.
    """
    requests = {}
    # Step 1: Aggregate all requested quantities by their source.
    for i, source_id_str in enumerate(source_log_ids):
        # Skip incomplete rows
        if not source_id_str or not product_ids[i] or not actual_quantities[i]:
            continue
        try:
            source_id = int(source_id_str)
            quantity = float(actual_quantities[i])
            product_id = int(product_ids[i])
        except (ValueError, TypeError):
            # Skip rows with invalid data
            continue
            
        request_key = (source_id, product_id)
        requests[request_key] = requests.get(request_key, 0) + quantity

    # Step 2: Validate each aggregated request against the available stock.
    for request_key, total_requested in requests.items():
        source_id, product_id = request_key
        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return (False, f"المنتج برقم {product_id} غير موجود.")
        
        # Base queryset to find items already using stock, excluding the current batch if editing.
        used_items_qs = BatchItem.objects.filter(primitive_product_id=product_id)
        if batch_id_to_exclude:
            used_items_qs = used_items_qs.exclude(batch_id=batch_id_to_exclude)

        try:
            log_entry = InventoryLog.objects.get(pk=source_id)
        except InventoryLog.DoesNotExist:
            return (False, f"مصدر المخزون برقم {source_id} غير موجود.")

        # --- QC VALIDATION ---
        if log_entry.status != InventoryLog.Status.RELEASED:
            return (False, f"خطأ في مادة '{log_entry.product.name}': المصدر (QC: {log_entry.qc_no or 'N/A'}) لم يتم الإفراج عنه بعد وهو تحت الفحص.")
        
        if not log_entry.release_timestamp or log_entry.release_timestamp.date() > batch_creation_date:
            return False, f"خطأ في مادة '{log_entry.product.name}': تاريخ الإفراج عن المصدر ({log_entry.release_timestamp.date()}) أحدث من تاريخ أمر التشغيل ({batch_creation_date})."
        
        if product_id != log_entry.product_id:
            return (False, f"عدم تطابق المنتج. تم طلب '{product.name}' من مصدر QC '{log_entry.qc_no}' الذي يخص منتج '{log_entry.product.name}'.")

        total_available_from_log = log_entry.quantity
        total_returned = log_entry.production_returns.aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
        already_used = used_items_qs.filter(source_log_id=source_id).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
        available_stock = total_available_from_log - already_used + total_returned

        if total_requested > available_stock + 0.001: # Add tolerance for float comparison
            return (False, f"كمية غير كافية للمنتج '{product.name}' من المصدر QC '{log_entry.qc_no}'. مطلوب: {total_requested:.3f}, متاح: {available_stock:.3f}")

    return (True, None)
