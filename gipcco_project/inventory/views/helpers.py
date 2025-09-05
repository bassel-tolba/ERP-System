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


# --- MODIFIED: Added original unit price to returns for ledger display ---
def _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids=None):
    """
    A private helper to fetch and consolidate all transaction types for the ledger.
    """
    transactions = []
    
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').prefetch_related('tags').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').prefetch_related('source_log__tags').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
    ).prefetch_related('source_log__tags').filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)

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

    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_id': log.product.id, 'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': log.tags.all(),
            'unit_price': log.unit_price, 'cost_at_consumption': None,
        })

    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_id': ret.product.id, 'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})",
            'shop_order_number': None, 'batch_number': None, 'final_product_name': None, 'theoretical_quantity': None,
            'tags': ret.source_log.tags.all(),
            # --- KEY CHANGE: Pass the original unit price from the source log ---
            'unit_price': ret.source_log.unit_price, 
            'cost_at_consumption': None,
        })

    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -(item.actual_quantity or 0.0),
            'product_id': item.primitive_product.id, 'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'company_name': None, 'qc_no': source_desc, 'batch_id': item.batch.id,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})",
            'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
            'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
            'tags': item.source_log.tags.all() if item.source_log else [],
            'unit_price': None, 'cost_at_consumption': item.cost_at_consumption,
        })

    # Ensure deterministic sorting for same-timestamp transactions
    def get_sort_key(trx):
        # Sort by date, then by type (IN -> RETURN_IN -> OUT) to process logically
        type_order = {'IN': 1, 'RETURN_IN': 2, 'OUT': 3}
        return (trx['date'], type_order.get(trx['type'], 99))

    transactions.sort(key=get_sort_key)
    return transactions


# ==============================================================================
#  Costing Engine Helper Functions
# ==============================================================================

def update_moving_average_cost(product_id: int, log_entry: InventoryLog):
    """
    Updates the moving average cost for a product based on a new incoming shipment.
    This is for simple, forward-moving transactions ONLY (date is today or future).
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        
        incoming_qty = Decimal(log_entry.quantity)
        incoming_price = log_entry.unit_price or Decimal('0.000')

        total_in = Decimal(product.inventory_logs.aggregate(q=Coalesce(Sum('quantity'), 0.0))['q'])
        total_out = Decimal(product.batch_items.aggregate(q=Coalesce(Sum('actual_quantity'), 0.0))['q'])
        total_ret = Decimal(product.production_returns.aggregate(q=Coalesce(Sum('quantity'), 0.0))['q'])
        
        qty_after_receipt = total_in - total_out + total_ret
        qty_before_receipt = qty_after_receipt - incoming_qty
        
        value_before_receipt = qty_before_receipt * product.moving_average_cost
        value_of_receipt = incoming_qty * incoming_price
        
        total_value_after = value_before_receipt + value_of_receipt
        total_qty_after = qty_before_receipt + incoming_qty
        
        if total_qty_after > 0:
            new_mac = total_value_after / total_qty_after
        else:
            new_mac = incoming_price
        
        product.moving_average_cost = new_mac.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        logger.info(f"Updated MAC for '{product.name}' to {product.moving_average_cost} via simple update.")


# --- MODIFIED: Implemented accountant's logic for returns ---
def get_inventory_state_at_datetime(product_id: int, target_datetime: timezone.datetime) -> dict:
    """
    Calculates the total stock quantity and its total value for a product up to a specific datetime.
    Used by the recalculation engine and ledger to find a starting point.
    *** MODIFIED to use original purchase price for returns. ***
    """
    most_recent_ob = OpeningBalance.objects.filter(
        product_id=product_id, balance_date__lt=target_datetime
    ).order_by('-balance_date').first()

    if most_recent_ob:
        running_qty = Decimal(str(most_recent_ob.quantity))
        running_value = most_recent_ob.total_value
        effective_date = most_recent_ob.balance_date
    else:
        running_qty = Decimal('0.0')
        running_value = Decimal('0.0')
        effective_date = timezone.make_aware(datetime.min)
    
    logs = InventoryLog.objects.filter(product_id=product_id, timestamp__gte=effective_date, timestamp__lt=target_datetime)
    consumptions = BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=effective_date, batch__creation_date__lt=target_datetime)
    
    # Pre-fetch the related source_log for returns to avoid N+1 queries.
    returns = ProductionReturn.objects.select_related('source_log').filter(
        product_id=product_id, 
        return_date__gte=effective_date, 
        return_date__lt=target_datetime
    )
    
    transactions = sorted(
        list(logs) + list(consumptions) + list(returns),
        key=lambda x: (
            x.timestamp if isinstance(x, InventoryLog) else
            x.batch.creation_date if isinstance(x, BatchItem) else
            x.return_date,
            1 if isinstance(x, InventoryLog) else 2 if isinstance(x, ProductionReturn) else 3
        )
    )

    for trx in transactions:
        current_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')

        if isinstance(trx, InventoryLog):
            incoming_qty = Decimal(str(trx.quantity))
            incoming_price = trx.unit_price or Decimal('0.0')
            running_value += incoming_qty * incoming_price
            running_qty += incoming_qty
        
        elif isinstance(trx, ProductionReturn):
            return_qty = Decimal(str(trx.quantity))
            
            # --- NEW LOGIC: Value returns at their original purchase price ---
            cost_of_return = Decimal('0.0')
            if trx.source_log and trx.source_log.unit_price is not None:
                # Use the unit price from the original inventory log.
                cost_of_return = trx.source_log.unit_price
            else:
                # Fallback to the current MAC if the source log or its price is missing.
                cost_of_return = current_avg_cost
            
            running_value += return_qty * cost_of_return
            running_qty += return_qty
        
        elif isinstance(trx, BatchItem):
            consumed_qty = Decimal(str(trx.actual_quantity or 0.0))
            running_value -= consumed_qty * current_avg_cost
            running_qty -= consumed_qty
            
    return {'quantity': running_qty, 'value': running_value}


# --- MODIFIED: Implemented accountant's logic for returns ---
def recalculate_cost_history_for_product(product_id: int, start_datetime: timezone.datetime):
    """
    Recalculates the entire cost and consumption history for a product from a specific point in time.
    *** MODIFIED to use original purchase price for returns. ***
    """
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        logger.info(f"Starting cost recalculation for '{product.name}' from {start_datetime.date()}...")
        
        state = get_inventory_state_at_datetime(product_id, start_datetime)
        running_qty = state['quantity']
        running_value = state['value']

        logs = InventoryLog.objects.filter(product_id=product_id, timestamp__gte=start_datetime)
        consumptions = BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=start_datetime)
        
        # Pre-fetch the related source_log for returns to avoid N+1 queries.
        returns = ProductionReturn.objects.select_related('source_log').filter(
            product_id=product_id, 
            return_date__gte=start_datetime
        )
        
        transactions = sorted(
            list(logs) + list(consumptions) + list(returns),
            key=lambda x: (
                x.timestamp if isinstance(x, InventoryLog) else
                x.batch.creation_date if isinstance(x, BatchItem) else
                x.return_date,
                1 if isinstance(x, InventoryLog) else 2 if isinstance(x, ProductionReturn) else 3
            )
        )
        
        items_to_update = []
        
        for trx in transactions:
            current_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')

            if isinstance(trx, InventoryLog):
                incoming_qty = Decimal(str(trx.quantity))
                incoming_price = trx.unit_price or Decimal('0.0')
                running_value += incoming_qty * incoming_price
                running_qty += incoming_qty
            
            elif isinstance(trx, ProductionReturn):
                return_qty = Decimal(str(trx.quantity))
                
                # --- NEW LOGIC: Value returns at their original purchase price ---
                cost_of_return = Decimal('0.0')
                if trx.source_log and trx.source_log.unit_price is not None:
                    # Use the unit price from the original inventory log.
                    cost_of_return = trx.source_log.unit_price
                else:
                    # Fallback to the current MAC if the source log or its price is missing.
                    cost_of_return = current_avg_cost
                
                running_value += return_qty * cost_of_return
                running_qty += return_qty
            
            elif isinstance(trx, BatchItem):
                new_cost = current_avg_cost.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
                if trx.cost_at_consumption != new_cost:
                    trx.cost_at_consumption = new_cost
                    items_to_update.append(trx)
                
                consumed_qty = Decimal(str(trx.actual_quantity or 0.0))
                running_value -= consumed_qty * new_cost
                running_qty -= consumed_qty

        if items_to_update:
            BatchItem.objects.bulk_update(items_to_update, ['cost_at_consumption'])
            logger.info(f"Updated cost_at_consumption for {len(items_to_update)} batch items of '{product.name}'.")

        final_avg_cost = (running_value / running_qty) if running_qty > 0 else Decimal('0.0')
        product.moving_average_cost = final_avg_cost.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
        product.save(update_fields=['moving_average_cost'])
        logger.info(f"Finished recalculating cost history for '{product.name}'. New MAC: {product.moving_average_cost}")