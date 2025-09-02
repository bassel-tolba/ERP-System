# gipcco_project/inventory/views/helpers.py

import json
import math
from datetime import datetime, timedelta, time

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

from ..models import (Batch, BatchItem, Company, InventoryLog, OpeningBalance,
                     Product, ProductionReturn, ShopOrderTemplate, TemplateItem)

# Get an instance of the logger for this module
logger = logging.getLogger(__name__)


# ==============================================================================
#  Helper Functions (Unchanged section)
# ==============================================================================

def check_and_update_batch_customization(batch_id: int):
    # This function remains unchanged
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
        pass

def get_opening_balance_for_period(product_id: int, start_date: datetime) -> float:
    # This function remains unchanged
    most_recent_balance_entry = OpeningBalance.objects.filter(
        product_id=product_id,
        balance_date__lte=start_date
    ).order_by('-balance_date').first()

    opening_base_qty = 0.0
    effective_balance_date = datetime(1, 1, 1, tzinfo=timezone.get_current_timezone())

    if most_recent_balance_entry:
        opening_base_qty = most_recent_balance_entry.quantity
        effective_balance_date = most_recent_balance_entry.balance_date

    sum_expression = Coalesce(Sum('quantity', output_field=FloatField()), 0.0)
    
    prior_period_in_log = InventoryLog.objects.filter(
        product_id=product_id,
        timestamp__gte=effective_balance_date,
        timestamp__lt=start_date
    ).aggregate(total=sum_expression)['total']

    prior_period_in_returns = ProductionReturn.objects.filter(
        product_id=product_id,
        return_date__gte=effective_balance_date,
        return_date__lt=start_date
    ).aggregate(total=sum_expression)['total']

    prior_period_out = BatchItem.objects.filter(
        primitive_product_id=product_id,
        batch__creation_date__gte=effective_balance_date,
        batch__creation_date__lt=start_date
    ).aggregate(total=Coalesce(Sum('actual_quantity', output_field=FloatField()), 0.0))['total']

    return opening_base_qty + prior_period_in_log + prior_period_in_returns - prior_period_out


def validate_stock_availability(product_ids, actual_quantities, source_log_ids, batch_creation_date, batch_id_to_exclude=None):
    """
    Validates stock availability by first aggregating all requests from the same source.
    This is a more robust version that handles multiple lines drawing from the same QC.
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
        product = Product.objects.get(pk=product_id)
        
        # Base queryset to find items already using stock, excluding the current batch if editing.
        used_items_qs = BatchItem.objects.filter(primitive_product_id=product_id)
        if batch_id_to_exclude:
            used_items_qs = used_items_qs.exclude(batch_id=batch_id_to_exclude)

        if source_id == -1: # ---- VALIDATING AGAINST OPENING BALANCE ----
            latest_balance = OpeningBalance.objects.filter(product_id=product_id).order_by('-balance_date').first()
            if not latest_balance:
                return (False, f"لا يوجد رصيد افتتاحي للمنتج '{product.name}'.")

            # --- THE FIX IS HERE ---
            # We must convert the `balance_date` (a DateTimeField) to a `date` object
            # before comparing it with `batch_creation_date` (a date object).
            if latest_balance.balance_date.date() > batch_creation_date:
                return False, f"خطأ في مادة '{product.name}': تاريخ الرصيد الافتتاحي ({latest_balance.balance_date.date()}) أحدث من تاريخ أمر التشغيل ({batch_creation_date})."
            
            total_available_from_ob = latest_balance.quantity
            already_used = used_items_qs.filter(source_type=BatchItem.SourceType.OPENING_BALANCE).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            available_stock = total_available_from_ob - already_used

            if total_requested > available_stock + 0.001: # Add tolerance for float comparison
                return (False, f"كمية غير كافية للمنتج '{product.name}' من الرصيد الافتتاحي. مطلوب: {total_requested:.3f}, متاح: {available_stock:.3f}")
        
        else: # ---- VALIDATING AGAINST INVENTORY LOG (QC) ----
            try:
                log_entry = InventoryLog.objects.get(pk=source_id)
            except InventoryLog.DoesNotExist:
                return (False, f"مصدر المخزون برقم {source_id} غير موجود.")

            # This part was already correct, ensuring we compare date vs date.
            if log_entry.timestamp.date() > batch_creation_date:
                return False, f"خطأ في مادة '{log_entry.product.name}': تاريخ المصدر ({log_entry.timestamp.date()}) أحدث من تاريخ أمر التشغيل ({batch_creation_date})."
            
            if product_id != log_entry.product_id:
                return (False, f"عدم تطابق المنتج. تم طلب '{product.name}' من مصدر QC '{log_entry.qc_no}' الذي يخص منتج '{log_entry.product.name}'.")

            total_available_from_log = log_entry.quantity
            total_returned = log_entry.production_returns.aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
            already_used = used_items_qs.filter(source_log_id=source_id).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            available_stock = total_available_from_log - already_used + total_returned

            if total_requested > available_stock + 0.001: # Add tolerance for float comparison
                return (False, f"كمية غير كافية للمنتج '{product.name}' من المصدر QC '{log_entry.qc_no}'. مطلوب: {total_requested:.3f}, متاح: {available_stock:.3f}")

    return (True, None)


# ==============================================================================
#  CORRECTED Helper Function
# ==============================================================================
def _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids=None):
    """
    A private helper to fetch and consolidate all transaction types for the ledger.
    NOW CORRECTLY FILTERS LOGS BY TAGS, not products by tags.
    """
    transactions = []
    
    # Base querysets with CORRECT optimization
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').prefetch_related('tags').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    
    # --- FIX 1: Added prefetch_related for the tags on the source log ---
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').prefetch_related('source_log__tags').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    
    # --- FIX 2: Moved 'source_log__tags' from select_related to prefetch_related ---
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
    ).prefetch_related('source_log__tags').filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)

    # Apply standard filters
    if product_id: 
        in_logs_qs = in_logs_qs.filter(product_id=product_id)
        returns_qs = returns_qs.filter(product_id=product_id)
        out_items_qs = out_items_qs.filter(primitive_product_id=product_id)
    if company_id: 
        in_logs_qs = in_logs_qs.filter(company_id=company_id)
        returns_qs = returns_qs.none()
        out_items_qs = out_items_qs.none()
    if qc_no: 
        in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
        returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
        out_items_qs = out_items_qs.filter(source_log__qc_no__icontains=qc_no)
    
    if tag_ids:
        in_logs_qs = in_logs_qs.filter(tags__id__in=tag_ids).distinct()
        returns_qs = returns_qs.filter(source_log__tags__id__in=tag_ids).distinct()
        out_items_qs = out_items_qs.filter(source_log__tags__id__in=tag_ids).distinct()

    # Process INCOMING from suppliers
    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_id': log.product.id, 'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': log.tags.all(),
        })

    # Process INCOMING from production returns
    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_id': ret.product.id, 'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': ret.source_log.tags.all(),
        })

    # Process OUTGOING to production
    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -item.actual_quantity,
            'product_id': item.primitive_product.id, 'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'company_name': None, 'qc_no': source_desc, 'batch_id': item.batch.id,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})",
            'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
            'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
            'tags': item.source_log.tags.all() if item.source_log else [],
        })

    transactions.sort(key=lambda x: x['date'])
    return transactions
    """
    A private helper to fetch and consolidate all transaction types for the ledger.
    NOW CORRECTLY FILTERS LOGS BY TAGS, not products by tags.
    """
    transactions = []
    
    # Base querysets
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').prefetch_related('tags').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'source_log__tags', 'batch__template__final_product'
    ).filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)

    # Apply standard filters
    if product_id: 
        in_logs_qs = in_logs_qs.filter(product_id=product_id)
        returns_qs = returns_qs.filter(product_id=product_id)
        out_items_qs = out_items_qs.filter(primitive_product_id=product_id)
    if company_id: 
        in_logs_qs = in_logs_qs.filter(company_id=company_id)
        returns_qs = returns_qs.none()
        out_items_qs = out_items_qs.none()
    if qc_no: 
        in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
        returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
        out_items_qs = out_items_qs.filter(source_log__qc_no__icontains=qc_no)
    
    # --- CORRECTED: Apply tag filter to the LOGS and BATCH ITEMS ---
    if tag_ids:
        # Filter INCOMING logs that have at least one of the selected tags
        in_logs_qs = in_logs_qs.filter(tags__id__in=tag_ids).distinct()
        # Filter RETURNS based on the tags of their original source log
        returns_qs = returns_qs.filter(source_log__tags__id__in=tag_ids).distinct()
        # Filter OUTGOING items based on the tags of their source log
        out_items_qs = out_items_qs.filter(source_log__tags__id__in=tag_ids).distinct()

    # Process INCOMING from suppliers
    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_id': log.product.id, 'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': log.tags.all(), # Include tags for display
        })

    # Process INCOMING from production returns
    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_id': ret.product.id, 'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': ret.source_log.tags.all(), # Include tags for display
        })

    # Process OUTGOING to production
    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -item.actual_quantity,
            'product_id': item.primitive_product.id, 'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'company_name': None, 'qc_no': source_desc, 'batch_id': item.batch.id,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})",
            'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
            'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
            'tags': item.source_log.tags.all() if item.source_log else [], # Include tags for display
        })

    transactions.sort(key=lambda x: x['date'])
    return transactions
    """
    A private helper to fetch and consolidate all transaction types for the ledger.
    NOW INCLUDES FILTERING BY TAGS.
    """
    transactions = []
    
    # Base querysets
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
    ).filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)

    # Apply filters
    if product_id: 
        in_logs_qs = in_logs_qs.filter(product_id=product_id)
        returns_qs = returns_qs.filter(product_id=product_id)
        out_items_qs = out_items_qs.filter(primitive_product_id=product_id)
    # --- NEW: Apply tag filter only if no specific product is chosen ---
    elif tag_ids:
        in_logs_qs = in_logs_qs.filter(product__tags__id__in=tag_ids).distinct()
        returns_qs = returns_qs.filter(product__tags__id__in=tag_ids).distinct()
        out_items_qs = out_items_qs.filter(primitive_product__tags__id__in=tag_ids).distinct()

    if company_id: 
        in_logs_qs = in_logs_qs.filter(company_id=company_id)
        # Cannot filter returns or outgoing by company
        returns_qs = returns_qs.none()
        out_items_qs = out_items_qs.none()

    if qc_no: 
        in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
        returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
        out_items_qs = out_items_qs.filter(source_log__qc_no__icontains=qc_no)

    # Process INCOMING from suppliers
    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_id': log.product.id, 'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
        })

    # Process INCOMING from production returns
    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_id': ret.product.id, 'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
        })

    # Process OUTGOING to production
    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -item.actual_quantity,
            'product_id': item.primitive_product.id, 'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'company_name': None, 'qc_no': source_desc, 'batch_id': item.batch.id,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})",
            'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
            'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
        })

    transactions.sort(key=lambda x: x['date'])
    return transactions