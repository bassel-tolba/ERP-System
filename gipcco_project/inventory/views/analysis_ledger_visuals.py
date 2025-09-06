# gipcco_project/inventory/views/analysis_ledger_visuals.py

import json
from datetime import datetime, timedelta, time
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum, Q, F, FloatField, Value, ExpressionWrapper, DecimalField, Count, Avg
from django.db.models.functions import Coalesce, TruncDay
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import (Batch, BatchItem, Company, InventoryLog, Product, ProductTag, 
                     ProductionReturn, FinishedProductReceipt, FinishedProductDispatch,
                     SalesOrderItem, InventoryConsumption, ExpenseLog) # --- NEW: Import new models
from .helpers import get_inventory_state_at_datetime

# --- NEW HELPER FUNCTION FOR FINAL PRODUCTS ---
def get_final_product_state_at_datetime(product_id: int, target_datetime: timezone.datetime) -> dict:
    """
    Calculates the total stock quantity and its total value for a FINAL product up to a specific datetime.
    """
    receipts_before = FinishedProductReceipt.objects.filter(
        batch__template__final_product_id=product_id,
        receipt_date__lt=target_datetime.date(),
        status=FinishedProductReceipt.Status.RELEASED, # Only count released stock
    )
    
    aggregates = receipts_before.aggregate(
        total_qty=Coalesce(Sum('total_quantity_produced'), 0.0, output_field=FloatField()),
        total_val=Coalesce(Sum('total_cost'), Decimal('0.0'), output_field=DecimalField())
    )
    
    return {
        'quantity': Decimal(str(aggregates['total_qty'])),
        'value': aggregates['total_val']
    }

# --- MODIFIED: _get_ledger_transactions to include all transaction types ---
def _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids=None, final_product_id=None):
    """
    A private helper to fetch and consolidate all transaction types for the ledger.
    Now includes Finished Product Receipts, Sales Dispatches, and internal Inventory Consumptions.
    """
    transactions = []
    
    # --- RAW MATERIAL & MRO/CONSUMABLE TRANSACTIONS ---
    if not final_product_id:
        in_logs_qs = InventoryLog.objects.select_related('product', 'company').prefetch_related('tags').filter(
            status=InventoryLog.Status.RELEASED,
            release_timestamp__gte=start_date,
            release_timestamp__lt=end_date_inclusive
        )
        returns_qs = ProductionReturn.objects.select_related('product', 'source_log').prefetch_related('source_log__tags').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
        out_items_qs = BatchItem.objects.select_related(
            'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
        ).prefetch_related('source_log__tags').filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)
        # --- NEW: Query for internal consumptions ---
        consumption_qs = InventoryConsumption.objects.select_related('product', 'source_log').prefetch_related('source_log__tags').filter(
            consumption_date__gte=start_date, consumption_date__lt=end_date_inclusive
        )

        if product_id: 
            in_logs_qs = in_logs_qs.filter(product_id=product_id)
            returns_qs = returns_qs.filter(product_id=product_id)
            out_items_qs = out_items_qs.filter(primitive_product_id=product_id)
            consumption_qs = consumption_qs.filter(product_id=product_id) # Filter consumptions too
        if company_id: 
            in_logs_qs = in_logs_qs.filter(company_id=company_id)
            returns_qs = returns_qs.none()
            out_items_qs = out_items_qs.none()
            consumption_qs = consumption_qs.none() # Consumptions are internal, not from a company
        if qc_no: 
            in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
            returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
            out_items_qs = out_items_qs.filter(source_log__qc_no__icontains=qc_no)
            consumption_qs = consumption_qs.filter(source_log__qc_no__icontains=qc_no) # Filter by source QC
        
        if tag_ids:
            in_logs_qs = in_logs_qs.filter(tags__id__in=tag_ids).distinct()
            returns_qs = returns_qs.filter(source_log__tags__id__in=tag_ids).distinct()
            out_items_qs = out_items_qs.filter(source_log__tags__id__in=tag_ids).distinct()
            consumption_qs = consumption_qs.filter(source_log__tags__id__in=tag_ids).distinct()

        for log in in_logs_qs:
            transactions.append({
                'date': log.release_timestamp, 'type': 'IN', 'quantity_change': log.quantity,
                'product_id': log.product.id, 'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
                'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
                'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no,
                'tags': log.tags.all(), 'unit_price': log.unit_price,
            })

        for ret in returns_qs:
            transactions.append({
                'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
                'product_id': ret.product.id, 'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
                'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})",
                'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no,
                'tags': ret.source_log.tags.all(), 'unit_price': ret.source_log.unit_price,
            })

        for item in out_items_qs:
            source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
            continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
            transactions.append({
                'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -(item.actual_quantity or 0.0),
                'product_id': item.primitive_product.id, 'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
                'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})",
                'qc_no': source_desc, 'batch_id': item.batch.id,
                'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
                'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
                'tags': item.source_log.tags.all() if item.source_log else [], 'cost_at_consumption': item.cost_at_consumption,
            })
            
        # --- NEW: Add internal consumptions to ledger ---
        for cons in consumption_qs:
            transactions.append({
                'date': cons.consumption_date, 'type': 'CONSUME_OUT', 'quantity_change': -cons.quantity_consumed,
                'product_id': cons.product.id, 'product_name': cons.product.name, 'product_code': cons.product.code, 'unit': cons.product.unit,
                'description': f"صرف إداري لقسم: {cons.get_department_display()}",
                'qc_no': cons.source_log.qc_no if cons.source_log else 'N/A',
                'department': cons.get_department_display(), 'notes': cons.notes,
                'tags': cons.source_log.tags.all() if cons.source_log else [], 'cost_at_consumption': cons.cost_at_consumption,
            })

    # --- FINAL PRODUCT TRANSACTIONS ---
    if final_product_id:
        receipts_qs = FinishedProductReceipt.objects.select_related(
            'batch__template__final_product'
        ).filter(
            batch__template__final_product_id=final_product_id,
            receipt_date__gte=start_date.date(),
            receipt_date__lt=end_date_inclusive.date(),
            status=FinishedProductReceipt.Status.RELEASED,
        ).order_by('receipt_date')
        
        for receipt in receipts_qs:
            transactions.append({
                'date': timezone.make_aware(datetime.combine(receipt.receipt_date, time.min)),
                'type': 'PROD_IN', 'quantity_change': receipt.total_quantity_produced,
                'product_id': receipt.batch.template.final_product.id,
                'product_name': receipt.batch.template.final_product.name,
                'product_code': receipt.batch.template.final_product.code,
                'unit': receipt.batch.template.final_product.unit,
                'description': f"استلام إنتاج نهائي للتشغيلة #{receipt.individual_batch_number}",
                'shop_order_number': receipt.batch.shop_order_number, 'batch_number': receipt.individual_batch_number,
                'market_type': receipt.get_market_type_display(), 'total_cost': receipt.total_cost, 'tags': [], 
            })

        dispatch_qs = FinishedProductDispatch.objects.select_related(
            'sales_order_item__sales_order__customer',
            'sales_order_item__finished_product__batch__template__final_product'
        ).filter(
            sales_order_item__finished_product__batch__template__final_product_id=final_product_id,
            dispatch_date__gte=start_date,
            dispatch_date__lt=end_date_inclusive,
        )

        for dispatch in dispatch_qs:
            final_product = dispatch.sales_order_item.finished_product.batch.template.final_product
            transactions.append({
                'date': dispatch.dispatch_date, 'type': 'SALE_OUT', 'quantity_change': -dispatch.quantity,
                'product_id': final_product.id, 'product_name': final_product.name,
                'product_code': final_product.code, 'unit': final_product.unit,
                'description': f"صرف للعميل: {dispatch.sales_order_item.sales_order.customer.name} (أمر بيع #{dispatch.sales_order_item.sales_order.so_number})",
                'batch_number': dispatch.sales_order_item.finished_product.individual_batch_number,
                'total_cost': -dispatch.cost_at_dispatch, 'tags': [],
            })
            
    def get_sort_key(trx):
        # --- MODIFIED: Added CONSUME_OUT to the sort order ---
        type_order = {'IN': 1, 'RETURN_IN': 2, 'PROD_IN': 3, 'OUT': 4, 'CONSUME_OUT': 5, 'SALE_OUT': 6}
        return (trx['date'], type_order.get(trx['type'], 99))

    transactions.sort(key=get_sort_key)
    return transactions


def ledger(request: HttpRequest) -> HttpResponse:
    """
    Displays the stock card / ledger for products with full financial transparency.
    Now supports filtering by final products.
    """
    product_id = request.GET.get('product_id')
    final_product_id = request.GET.get('final_product_id')
    company_id = request.GET.get('company_id')
    tag_ids = request.GET.getlist('tags')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    all_primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
    all_final_products = Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT)
    all_companies = Company.objects.all()
    all_tags = ProductTag.objects.all()
    
    context = {
        'active_page': 'ledger',
        'all_primitive_products': all_primitive_products,
        'all_final_products': all_final_products,
        'all_companies': all_companies,
        'all_tags': all_tags,
        'selected_tags': tag_ids, 
    }
    
    if not any([product_id, final_product_id, company_id, qc_no, start_date_str, end_date_str, tag_ids]):
        template_name = 'inventory/ledger.html'
        if 'X-Partial-Request' in request.headers:
            template_name = 'inventory/partials/ledger_content.html'
        return render(request, template_name, context)
    
    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    
    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
        end_date_inclusive = end_date + timedelta(days=1)
    
    transactions = _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids, final_product_id)
    
    opening_state = {'quantity': Decimal('0.0'), 'value': Decimal('0.0')}
    product_unit = ""
    is_final_product_ledger = bool(final_product_id)

    if product_id:
        opening_state = get_inventory_state_at_datetime(int(product_id), start_date)
        product_unit = get_object_or_404(Product, pk=product_id).unit
    elif final_product_id:
        opening_state = get_final_product_state_at_datetime(int(final_product_id), start_date)
        product_unit = get_object_or_404(Product, pk=final_product_id).unit
    
    processed_transactions = []
    if product_id or final_product_id:
        current_qty = opening_state['quantity']
        current_value = opening_state['value']
        for trx in transactions:
            trx['balance_before'] = current_qty
            trx['value_before'] = current_value
            
            qty_change = Decimal(str(trx['quantity_change']))
            value_change = Decimal('0.0')

            trx_type = trx['type']
            if trx_type == 'IN':
                value_change = qty_change * (trx['unit_price'] or Decimal('0.0'))
            elif trx_type == 'OUT':
                value_change = qty_change * (trx['cost_at_consumption'] or Decimal('0.0'))
            # --- NEW: Handle value change for internal consumptions ---
            elif trx_type == 'CONSUME_OUT':
                # cost_at_consumption is the total cost, so value change is its negative
                value_change = -trx['cost_at_consumption']
            elif trx_type == 'RETURN_IN':
                original_price = trx.get('unit_price') or Decimal('0.0')
                value_change = qty_change * (original_price if original_price > 0 else (current_value / current_qty if current_qty > 0 else Decimal('0.0')))
            elif trx_type in ['PROD_IN', 'SALE_OUT']:
                value_change = trx['total_cost']
            
            trx['value_change'] = value_change
            current_qty += qty_change
            current_value += value_change

            trx['balance_after'] = current_qty
            trx['value_after'] = current_value
            trx['moving_average_cost_after'] = (current_value / current_qty) if current_qty > 0 else Decimal('0.0')
            
            processed_transactions.append(trx)
    else:
        for trx in transactions:
            trx.update({
                'balance_before': '---', 'balance_after': '---',
                'value_before': '---', 'value_after': '---', 'value_change': '---',
                'moving_average_cost_after': '---',
            })
            processed_transactions.append(trx)

    context.update({
        'transactions': processed_transactions,
        'opening_balance_for_period': opening_state['quantity'] if (product_id or final_product_id) else 'N/A',
        'opening_value_for_period': opening_state['value'] if (product_id or final_product_id) else 'N/A',
        'unit': product_unit,
        'is_final_product_ledger': is_final_product_ledger,
    })
    
    template_name = 'inventory/ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/ledger_content.html'
    return render(request, template_name, context)


def print_ledger(request: HttpRequest) -> HttpResponse:
    product_id = request.GET.get('product_id')
    final_product_id = request.GET.get('final_product_id')
    company_id = request.GET.get('company_id')
    tag_ids = request.GET.getlist('tags')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())

    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
        end_date_inclusive = end_date + timedelta(days=1)

    transactions = _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids, final_product_id)
    
    opening_state = {'quantity': Decimal('0.0'), 'value': Decimal('0.0')}
    if product_id:
        opening_state = get_inventory_state_at_datetime(int(product_id), start_date)
    elif final_product_id:
        opening_state = get_final_product_state_at_datetime(int(final_product_id), start_date)
    
    processed_transactions = []
    current_qty = opening_state['quantity']
    current_value = opening_state['value']
    
    if product_id or final_product_id:
        for trx in transactions:
            trx['balance_before'] = current_qty
            trx['value_before'] = current_value
            qty_change = Decimal(str(trx['quantity_change']))
            value_change = Decimal('0.0')

            trx_type = trx['type']
            if trx_type == 'IN':
                value_change = qty_change * (trx['unit_price'] or Decimal('0.0'))
            elif trx_type == 'OUT':
                value_change = qty_change * (trx['cost_at_consumption'] or Decimal('0.0'))
            # --- NEW: Handle value change for internal consumptions ---
            elif trx_type == 'CONSUME_OUT':
                value_change = -trx['cost_at_consumption']
            elif trx_type == 'RETURN_IN':
                original_price = trx.get('unit_price') or Decimal('0.0')
                value_change = qty_change * (original_price if original_price > 0 else (current_value / current_qty if current_qty > 0 else Decimal('0.0')))
            elif trx_type in ['PROD_IN', 'SALE_OUT']:
                value_change = trx['total_cost']
            
            trx['value_change'] = value_change
            current_qty += qty_change
            current_value += value_change
            trx['balance_after'] = current_qty
            trx['value_after'] = current_value
            processed_transactions.append(trx)

    closing_qty = current_qty if (product_id or final_product_id) else 'N/A'
    closing_value = current_value if (product_id or final_product_id) else 'N/A'
    
    report_title = "كشف حساب المخزون العام"
    product_details = None
    if product_id:
        product_details = get_object_or_404(Product, pk=product_id)
        report_title = f"كشف حساب مخزون - {product_details.name}"
    elif final_product_id:
        product_details = get_object_or_404(Product, pk=final_product_id)
        report_title = f"كشف حساب منتج نهائي - {product_details.name}"

    selected_tags = ProductTag.objects.filter(id__in=tag_ids) if tag_ids else []

    context = {
        'transactions': processed_transactions,
        'report_title': report_title,
        'product_details': product_details,
        'selected_tags': selected_tags,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'print_date': timezone.now(),
        'opening_balance': opening_state['quantity'] if (product_id or final_product_id) else 'N/A',
        'opening_value': opening_state['value'] if (product_id or final_product_id) else 'N/A',
        'closing_balance': closing_qty,
        'closing_value': closing_value,
    }
    return render(request, 'inventory/print_ledger_enhanced.html', context)


# --- The rest of the file (stock_valuation, analysis, visuals, reports) remains unchanged ---
def stock_valuation(request: HttpRequest) -> HttpResponse:
    """
    Displays a stock valuation report showing current stock, cost, and total value.
    """
    products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)).order_by('name')
    
    valuation_data = []
    grand_total_value = Decimal('0.0')

    for product in products:
        state = get_inventory_state_at_datetime(product.id, timezone.now())
        current_stock = state['quantity']
        
        stock_value = current_stock * product.moving_average_cost
        grand_total_value += stock_value
        
        valuation_data.append({
            'product': product,
            'current_stock': current_stock,
            'stock_value': stock_value,
        })

    context = {
        'active_page': 'analysis',
        'valuation_data': valuation_data,
        'grand_total_value': grand_total_value,
    }

    template_name = 'inventory/stock_valuation.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/stock_valuation_content.html'
    return render(request, template_name, context)


def analysis(request: HttpRequest) -> HttpResponse:
    """
    Displays a stock analysis report with both quantity and value for a given date range.
    """
    today = timezone.now()
    default_start_date = today.replace(day=1)
    
    start_date_str = request.POST.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.POST.get('end_date', today.strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    
    analysis_data = []
    primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))

    for product in primitive_products:
        opening_state = get_inventory_state_at_datetime(product.id, start_date)
        closing_state = get_inventory_state_at_datetime(product.id, end_date_inclusive)
        
        total_out_items = product.batch_items.filter(
            batch__creation_date__gte=start_date, 
            batch__creation_date__lt=end_date_inclusive
        )
        total_out_qty = total_out_items.aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
        total_out_value = sum(
            Decimal(str(item.actual_quantity or 0)) * (item.cost_at_consumption or Decimal('0.0')) 
            for item in total_out_items
        )
        
        total_in_qty_decimal = (closing_state['quantity'] - opening_state['quantity']) + Decimal(str(total_out_qty))
        total_in_value = (closing_state['value'] - opening_state['value']) + total_out_value

        analysis_data.append({
            'id': product.id, 'name': product.name, 'code': product.code, 'unit': product.unit,
            'opening_balance': opening_state['quantity'],
            'opening_value': opening_state['value'],
            'total_in_qty': total_in_qty_decimal,
            'total_in_value': total_in_value,
            'total_out_qty': total_out_qty,
            'total_out_value': total_out_value,
            'closing_balance': closing_state['quantity'],
            'closing_value': closing_state['value'],
        })

    context = {
        'active_page': 'visuals', # Changed to match nav link
        'data': analysis_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/analysis_content.html', context)
    return render(request, 'inventory/analysis.html', context)


# --- MODIFIED: `visuals` view now includes the Expense Analysis tab ---
def visuals(request: HttpRequest) -> HttpResponse:
    """
    Displays a powerful analysis dashboard with selectable modes for
    raw materials, finished products, and expenses.
    """
    analysis_type = request.GET.get('type', 'raw_material')
    
    # --- Common Filters ---
    today = timezone.now()
    default_start = today.replace(day=1)
    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    
    # --- MODIFIED: Add querysets for new filters ---
    consumable_products = Product.objects.filter(Q(product_type=Product.ProductType.MRO) | Q(product_type=Product.ProductType.CONSUMABLE))
    expense_product_types = [
        (Product.ProductType.MRO, Product.ProductType.MRO.label),
        (Product.ProductType.CONSUMABLE, Product.ProductType.CONSUMABLE.label),
    ]

    # --- Initialize context with shared data ---
    context = {
        'active_page': 'visuals',
        'analysis_type': analysis_type,
        'all_primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'all_final_products': Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT),
        'all_companies': Company.objects.all(),
        'all_tags': ProductTag.objects.all(),
        'consumable_products': consumable_products,
        'expense_product_types': expense_product_types,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }

    if analysis_type == 'raw_material':
        # --- RAW MATERIAL ANALYSIS LOGIC (UNCHANGED) ---
        product_id_str = request.GET.get('product_id')
        company_id = request.GET.get('company_id')
        tag_ids = request.GET.getlist('tags')
        qc_no = request.GET.get('qc_no', '').strip()
        
        kpi_data, supplier_analysis_data = {}, []
        in_out_data, consumption_data, variance_data, supplier_data = ({'labels': [], 'datasets': []} for _ in range(4))
        product_id = int(product_id_str) if product_id_str else None

        if product_id:
            product = get_object_or_404(Product, pk=product_id)
            receipts = InventoryLog.objects.filter(
                product_id=product_id, status=InventoryLog.Status.RELEASED,
                release_timestamp__gte=start_date, release_timestamp__lt=end_date_inclusive
            )
            consumptions = BatchItem.objects.filter(
                primitive_product_id=product_id, batch__creation_date__gte=start_date,
                batch__creation_date__lt=end_date_inclusive
            )
            if company_id: receipts = receipts.filter(company_id=company_id); consumptions = consumptions.none()
            if qc_no:
                receipts = receipts.filter(qc_no__icontains=qc_no)
                consumptions = consumptions.filter(source_log__qc_no__icontains=qc_no)
            if tag_ids:
                receipts = receipts.filter(tags__id__in=tag_ids).distinct()
                consumptions = consumptions.filter(source_log__tags__id__in=tag_ids).distinct()

            total_in_qty = receipts.aggregate(total=Coalesce(Sum('quantity', output_field=DecimalField()), Decimal('0.0')))['total']
            total_out_qty = consumptions.aggregate(total=Coalesce(Sum('actual_quantity', output_field=DecimalField()), Decimal('0.0')))['total']
            total_in_value = receipts.annotate(line_total=ExpressionWrapper(F('quantity') * F('unit_price'), output_field=DecimalField())).aggregate(total=Coalesce(Sum('line_total'), Decimal('0.0')))['total']
            total_out_value = consumptions.annotate(line_total=ExpressionWrapper(F('actual_quantity') * F('cost_at_consumption'), output_field=DecimalField())).aggregate(total=Coalesce(Sum('line_total'), Decimal('0.0')))['total']
            total_theoretical_qty = consumptions.aggregate(total=Coalesce(Sum('theoretical_quantity', output_field=DecimalField()), Decimal('0.0')))['total']
            total_variance_qty = total_out_qty - total_theoretical_qty
            num_days = (end_date - start_date).days + 1
            avg_daily_consumption = total_out_qty / num_days if num_days > 0 else 0
            current_stock = get_inventory_state_at_datetime(product_id, timezone.now())['quantity']

            kpi_data = {
                'avg_purchase_price': (total_in_value / total_in_qty) if total_in_qty > 0 else Decimal('0.0'),
                'avg_consumption_cost': (total_out_value / total_out_qty) if total_out_qty > 0 else Decimal('0.0'),
                'total_variance_qty': total_variance_qty,
                'total_variance_percent': (total_variance_qty / total_theoretical_qty * 100) if total_theoretical_qty > 0 else 0,
                'days_of_supply': (current_stock / avg_daily_consumption) if avg_daily_consumption > 0 else float('inf'),
                'product_unit': product.unit,
            }
            supplier_analysis_data = receipts.filter(company__isnull=False).values('company__name').annotate(receipt_count=Count('id'), total_qty=Sum('quantity', output_field=DecimalField()), total_val=Sum(ExpressionWrapper(F('quantity') * F('unit_price'), output_field=DecimalField()))).annotate(avg_price=F('total_val') / F('total_qty')).order_by('-total_val')
            all_transactions = _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids)
            opening_balance = get_inventory_state_at_datetime(product_id, start_date)['quantity']
            running_balance = float(opening_balance)
            chart_labels = [start_date.strftime('%Y-%m-%d (Start)')]; balance_data = [round(running_balance, 3)]
            for trx in all_transactions:
                running_balance += float(trx['quantity_change'])
                chart_labels.append(trx['date'].strftime('%Y-%m-%d %H:%M')); balance_data.append(round(running_balance, 3))
            in_out_data = {'labels': chart_labels, 'datasets': [{'label': 'الرصيد المتراكم', 'data': balance_data, 'borderColor': '#0d6efd', 'backgroundColor': 'rgba(13, 110, 253, 0.2)', 'fill': True, 'tension': 0.1}]}
            consumption_rows = consumptions.values('batch__template__final_product__name').annotate(total_consumed=Sum('actual_quantity')).order_by('-total_consumed')
            if consumption_rows: consumption_data = {'labels': [r['batch__template__final_product__name'] for r in consumption_rows], 'datasets': [{'data': [float(r['total_consumed']) for r in consumption_rows]}]}
            variance_rows = consumptions.filter(actual_quantity__isnull=False, theoretical_quantity__isnull=False).annotate(variance=F('actual_quantity') - F('theoretical_quantity')).order_by('batch__creation_date', 'batch__id')
            if variance_rows:
                cumulative_variance = 0; cumulative_data = []
                for r in variance_rows: cumulative_variance += r.variance; cumulative_data.append(float(cumulative_variance))
                variance_data = {'labels': [f"{r.batch.batch_number} ({r.batch.creation_date.strftime('%d-%m')})" for r in variance_rows], 'datasets': [{'type': 'bar', 'label': 'الفرق بالتشغيلة', 'data': [float(r.variance) for r in variance_rows]}, {'type': 'line', 'label': 'الفرق التراكمي', 'data': cumulative_data, 'borderColor': '#ffc107', 'backgroundColor': 'rgba(255, 193, 7, 0.5)', 'fill': False}]}
            if supplier_analysis_data: supplier_data = {'labels': [r['company__name'] for r in supplier_analysis_data], 'datasets': [{'data': [r['total_val'] for r in supplier_analysis_data]}]}

        context.update({
            'kpi_data': kpi_data,
            'supplier_analysis_data': supplier_analysis_data,
            'in_out_data_json': json.dumps(in_out_data, default=str),
            'consumption_data_json': json.dumps(consumption_data, default=str),
            'variance_data_json': json.dumps(variance_data, default=str),
            'supplier_data_json': json.dumps(supplier_data, default=str),
            'selected_product_id': product_id,
            'selected_company_id': company_id,
            'selected_tags': tag_ids,
        })
    
    elif analysis_type == 'finished_product':
        # --- FINISHED PRODUCT ANALYSIS LOGIC (UNCHANGED) ---
        final_product_id_str = request.GET.get('final_product_id')
        final_product_id = int(final_product_id_str) if final_product_id_str else None
        
        fp_kpi_data = {}
        prod_volume_data, cost_trend_data, market_share_data, product_mix_data = ({'labels': [], 'datasets': []} for _ in range(4))

        base_receipts = FinishedProductReceipt.objects.filter(
            status=FinishedProductReceipt.Status.RELEASED,
            release_date__gte=start_date.date(),
            release_date__lt=end_date_inclusive.date()
        )
        if final_product_id:
            base_receipts = base_receipts.filter(batch__template__final_product_id=final_product_id)
        aggregates = base_receipts.aggregate(
            total_produced=Coalesce(Sum('total_quantity_produced'), 0.0, output_field=FloatField()),
            total_cost=Coalesce(Sum('total_cost'), Decimal('0.0'))
        )
        total_produced = aggregates['total_produced']
        total_cost = aggregates['total_cost']
        avg_cost_per_unit = (total_cost / Decimal(str(total_produced))) if total_produced > 0 else Decimal('0.0')
        fp_kpi_data = {
            'total_produced': total_produced,
            'total_value': total_cost,
            'avg_cost_per_unit': avg_cost_per_unit
        }
        volume_by_day = base_receipts.annotate(day=TruncDay('release_date')).values('day').annotate(daily_total=Sum('total_quantity_produced')).order_by('day')
        if volume_by_day: prod_volume_data = { 'labels': [d['day'].strftime('%Y-%m-%d') for d in volume_by_day], 'datasets': [{'label': 'الإنتاج اليومي', 'data': [d['daily_total'] for d in volume_by_day], 'borderColor': '#198754', 'backgroundColor': 'rgba(25, 135, 84, 0.2)', 'fill': True, 'tension': 0.1}]}
        if final_product_id:
            cost_trend_rows = base_receipts.annotate(unit_cost=ExpressionWrapper(F('total_cost') / F('total_quantity_produced'), output_field=DecimalField())).order_by('release_date', 'id')
            if cost_trend_rows: cost_trend_data = { 'labels': [f"#{r.individual_batch_number} ({r.release_date.strftime('%d-%m')})" for r in cost_trend_rows], 'datasets': [{'label': 'تكلفة الوحدة', 'data': [r.unit_cost for r in cost_trend_rows], 'borderColor': '#dc3545', 'fill': False}]}
        market_share = base_receipts.values('market_type').annotate(total=Sum('total_quantity_produced'))
        if market_share: market_share_data = { 'labels': [dict(FinishedProductReceipt.MarketType.choices).get(m['market_type']) for m in market_share], 'datasets': [{'data': [m['total'] for m in market_share]}]}
        if not final_product_id:
            product_mix = base_receipts.values('batch__template__final_product__name').annotate(total=Sum('total_quantity_produced')).order_by('-total')
            if product_mix: product_mix_data = { 'labels': [p['batch__template__final_product__name'] for p in product_mix], 'datasets': [{'data': [p['total'] for p in product_mix]}]}
        
        context.update({
            'fp_kpi_data': fp_kpi_data,
            'production_volume_data_json': json.dumps(prod_volume_data, default=str),
            'cost_trend_data_json': json.dumps(cost_trend_data, default=str),
            'market_share_data_json': json.dumps(market_share_data, default=str),
            'product_mix_data_json': json.dumps(product_mix_data, default=str),
            'selected_final_product_id': final_product_id,
        })
    
    # --- MODIFIED: EXPENSE ANALYSIS LOGIC ---
    elif analysis_type == 'expense':
        # Get filters
        expense_product_type = request.GET.get('expense_product_type')
        expense_product_id_str = request.GET.get('expense_product_id')
        expense_product_id = int(expense_product_id_str) if expense_product_id_str else None

        expense_kpi_data = {}
        department_data, category_trend_data, top_items_data = ({'labels': [], 'datasets': []} for _ in range(3))

        # Base Querysets
        inventory_consumptions = InventoryConsumption.objects.filter(consumption_date__gte=start_date, consumption_date__lt=end_date_inclusive)
        general_expenses = ExpenseLog.objects.filter(expense_date__gte=start_date.date(), expense_date__lt=end_date_inclusive.date())

        # Apply new filters to inventory consumptions
        if expense_product_type:
            inventory_consumptions = inventory_consumptions.filter(product__product_type=expense_product_type)
        if expense_product_id:
            inventory_consumptions = inventory_consumptions.filter(product_id=expense_product_id)

        # KPI Calculations
        total_inv_exp = inventory_consumptions.aggregate(total=Coalesce(Sum('cost_at_consumption'), Decimal('0.0')))['total']
        total_gen_exp = general_expenses.aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
        
        top_consumed_item = inventory_consumptions.values('product__name').annotate(total_cost=Sum('cost_at_consumption')).order_by('-total_cost').first()
        top_spending_dept = inventory_consumptions.values('department').annotate(total_cost=Sum('cost_at_consumption')).order_by('-total_cost').first()

        expense_kpi_data = {
            'total_expense': total_inv_exp + total_gen_exp,
            'top_item_name': top_consumed_item['product__name'] if top_consumed_item else 'N/A',
            'top_item_value': top_consumed_item['total_cost'] if top_consumed_item else Decimal('0.0'),
            'top_dept_name': dict(InventoryConsumption.Department.choices).get(top_spending_dept['department']) if top_spending_dept else 'N/A',
            'top_dept_value': top_spending_dept['total_cost'] if top_spending_dept else Decimal('0.0'),
        }

        # Chart 1: Expenses by Department (Pie Chart)
        dept_expenses = inventory_consumptions.values('department').annotate(total=Sum('cost_at_consumption')).order_by('-total')
        if dept_expenses:
            department_data = {
                'labels': [dict(InventoryConsumption.Department.choices).get(d['department']) for d in dept_expenses],
                'datasets': [{'data': [d['total'] for d in dept_expenses]}]
            }

        # Chart 2: General Expenses Over Time (Line Chart)
        daily_gen_expenses = general_expenses.annotate(day=TruncDay('expense_date')).values('day').annotate(total=Sum('amount')).order_by('day')
        if daily_gen_expenses:
            category_trend_data = {
                'labels': [d['day'].strftime('%Y-%m-%d') for d in daily_gen_expenses],
                'datasets': [{'label': 'المصروفات العامة اليومية', 'data': [d['total'] for d in daily_gen_expenses], 'borderColor': '#6f42c1', 'backgroundColor': 'rgba(111, 66, 193, 0.2)', 'fill': True, 'tension': 0.1}]
            }
        
        # Chart 3: Top 20 Consumed Items (Bar Chart)
        top_items = inventory_consumptions.values('product__name').annotate(total=Sum('cost_at_consumption')).order_by('-total')[:20]
        if top_items:
            top_items_data = {
                'labels': [item['product__name'] for item in top_items],
                'datasets': [{'label': 'تكلفة الاستهلاك', 'data': [item['total'] for item in top_items]}]
            }

        context.update({
            'expense_kpi_data': expense_kpi_data,
            'department_data_json': json.dumps(department_data, default=str),
            'category_trend_data_json': json.dumps(category_trend_data, default=str),
            'top_items_data_json': json.dumps(top_items_data, default=str),
            'selected_expense_product_type': expense_product_type,
            'selected_expense_product_id': expense_product_id,
        })

    template_name = 'inventory/visuals.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/visuals_content.html'
    return render(request, template_name, context)


def sales_margin_analysis(request: HttpRequest) -> HttpResponse:
    today = timezone.now()
    default_start_date = today.replace(day=1)
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    dispatches = FinishedProductDispatch.objects.filter(dispatch_date__gte=start_date, dispatch_date__lt=end_date_inclusive).select_related('sales_order_item__sales_order__customer', 'sales_order_item__finished_product__batch__template__final_product')
    total_revenue = dispatches.annotate(revenue=ExpressionWrapper(F('quantity') * F('sales_order_item__unit_price'), output_field=DecimalField())).aggregate(total=Coalesce(Sum('revenue'), Decimal('0.0')))['total']
    total_cogs = dispatches.aggregate(total=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0')))['total']
    gross_profit = total_revenue - total_cogs
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.0')
    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'dispatches': dispatches,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin,
    }
    template_name = 'inventory/sales_margin_analysis.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/sales_margin_analysis_content.html'
    return render(request, template_name, context)

def profit_and_loss_statement(request: HttpRequest) -> HttpResponse:
    today = timezone.now()
    default_start_date = today.replace(day=1)
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    dispatches = FinishedProductDispatch.objects.filter(dispatch_date__date__gte=start_date, dispatch_date__date__lte=end_date)
    total_revenue = dispatches.annotate(revenue=ExpressionWrapper(F('quantity') * F('sales_order_item__unit_price'), output_field=DecimalField())).aggregate(total=Coalesce(Sum('revenue'), Decimal('0.0')))['total']
    total_cogs = dispatches.aggregate(total=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0')))['total']
    gross_profit = total_revenue - total_cogs
    inventory_expenses = InventoryConsumption.objects.filter(consumption_date__date__gte=start_date, consumption_date__date__lte=end_date)
    general_expenses = ExpenseLog.objects.filter(expense_date__gte=start_date, expense_date__lte=end_date)
    mfg_overhead_from_inventory = inventory_expenses.aggregate(total=Coalesce(Sum('cost_at_consumption'), Decimal('0.0')))['total']
    mfg_overhead_from_general = general_expenses.filter(classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD).aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
    total_mfg_overhead = mfg_overhead_from_inventory + mfg_overhead_from_general
    sg_a_expenses = general_expenses.filter(classification=ExpenseLog.Classification.SG_A)
    total_sg_a = sg_a_expenses.aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
    net_operating_profit = gross_profit - total_mfg_overhead - total_sg_a
    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'inventory_expenses': inventory_expenses,
        'mfg_overhead_from_general': general_expenses.filter(classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD),
        'sg_a_expenses': sg_a_expenses,
        'total_mfg_overhead': total_mfg_overhead,
        'total_sg_a': total_sg_a,
        'net_operating_profit': net_operating_profit,
    }
    template_name = 'inventory/profit_and_loss_statement.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/profit_and_loss_statement_content.html'
    return render(request, template_name, context)


# --- NEW REPORTING VIEWS ---

def sales_margin_analysis(request: HttpRequest) -> HttpResponse:
    """
    Analyzes sales data within a date range to calculate revenue, COGS, gross profit, and margin.
    """
    today = timezone.now()
    default_start_date = today.replace(day=1)
    
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)

    # Get all dispatches within the date range
    dispatches = FinishedProductDispatch.objects.filter(
        dispatch_date__gte=start_date,
        dispatch_date__lt=end_date_inclusive
    ).select_related(
        'sales_order_item__sales_order__customer',
        'sales_order_item__finished_product__batch__template__final_product'
    )
    
    # Calculate revenue and COGS
    total_revenue = dispatches.annotate(
        revenue=ExpressionWrapper(F('quantity') * F('sales_order_item__unit_price'), output_field=DecimalField())
    ).aggregate(total=Coalesce(Sum('revenue'), Decimal('0.0')))['total']

    total_cogs = dispatches.aggregate(total=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0')))['total']
    
    gross_profit = total_revenue - total_cogs
    gross_margin = (gross_profit / total_revenue * 100) if total_revenue > 0 else Decimal('0.0')
    
    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'dispatches': dispatches,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin,
    }

    template_name = 'inventory/sales_margin_analysis.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/sales_margin_analysis_content.html'
    return render(request, template_name, context)

def profit_and_loss_statement(request: HttpRequest) -> HttpResponse:
    """
    Generates a full Profit & Loss statement for a given period.
    """
    today = timezone.now()
    default_start_date = today.replace(day=1)
    
    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    
    # --- 1. Gross Profit Calculation ---
    dispatches = FinishedProductDispatch.objects.filter(
        dispatch_date__date__gte=start_date,
        dispatch_date__date__lte=end_date
    )
    total_revenue = dispatches.annotate(
        revenue=ExpressionWrapper(F('quantity') * F('sales_order_item__unit_price'), output_field=DecimalField())
    ).aggregate(total=Coalesce(Sum('revenue'), Decimal('0.0')))['total']
    total_cogs = dispatches.aggregate(total=Coalesce(Sum('cost_at_dispatch'), Decimal('0.0')))['total']
    gross_profit = total_revenue - total_cogs
    
    # --- 2. Operating Expenses Calculation ---
    inventory_expenses = InventoryConsumption.objects.filter(
        consumption_date__date__gte=start_date,
        consumption_date__date__lte=end_date
    )
    
    general_expenses = ExpenseLog.objects.filter(
        expense_date__gte=start_date,
        expense_date__lte=end_date
    )

    # Manufacturing Overhead
    mfg_overhead_from_inventory = inventory_expenses.aggregate(
        total=Coalesce(Sum('cost_at_consumption'), Decimal('0.0'))
    )['total']
    
    mfg_overhead_from_general = general_expenses.filter(
        classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD
    ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
    
    total_mfg_overhead = mfg_overhead_from_inventory + mfg_overhead_from_general
    
    # SG&A Expenses
    sg_a_expenses = general_expenses.filter(
        classification=ExpenseLog.Classification.SG_A
    )
    total_sg_a = sg_a_expenses.aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']

    # --- 3. Final Calculation ---
    net_operating_profit = gross_profit - total_mfg_overhead - total_sg_a

    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'total_revenue': total_revenue,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'inventory_expenses': inventory_expenses,
        'mfg_overhead_from_general': general_expenses.filter(classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD),
        'sg_a_expenses': sg_a_expenses,
        'total_mfg_overhead': total_mfg_overhead,
        'total_sg_a': total_sg_a,
        'net_operating_profit': net_operating_profit,
    }
    
    template_name = 'inventory/profit_and_loss_statement.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/profit_and_loss_statement_content.html'
    return render(request, template_name, context)