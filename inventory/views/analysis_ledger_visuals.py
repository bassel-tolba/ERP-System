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
                     SalesOrderItem, InventoryConsumption, ExpenseLog)
# --- MODIFIED: Rely solely on the main costing service ---
from ..services.costing_service import get_inventory_state_at_datetime


def _get_ledger_transactions(product: Product, start_date, end_date_inclusive, company_id=None, qc_no=None, tag_ids=None):
    """
    A private helper to fetch and consolidate all transaction types for a specific product.
    It intelligently queries different models based on the product's type.
    """
    transactions = []
    product_id = product.id

    # --- Case 1: The product is a Raw Material, MRO, or Consumable ---
    if product.product_type in [Product.ProductType.RAW_MATERIAL, Product.ProductType.PACKAGING, Product.ProductType.MRO, Product.ProductType.CONSUMABLE]:
        # Receipts (IN)
        in_logs_qs = InventoryLog.objects.filter(
            product_id=product_id, status=InventoryLog.Status.RELEASED,
            release_timestamp__gte=start_date, release_timestamp__lt=end_date_inclusive
        )
        # Returns from Production (IN)
        returns_qs = ProductionReturn.objects.filter(
            product_id=product_id, return_date__gte=start_date, return_date__lt=end_date_inclusive
        )
        # Consumption for Production (OUT)
        prod_consumptions_qs = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive
        )
        # Internal/Expense Consumption (OUT)
        internal_consumptions_qs = InventoryConsumption.objects.filter(
            product_id=product_id, consumption_date__gte=start_date, consumption_date__lt=end_date_inclusive
        )

        # Apply common filters
        if company_id:
            in_logs_qs = in_logs_qs.filter(company_id=company_id)
            # Other transaction types are internal, so we clear them
            returns_qs, prod_consumptions_qs, internal_consumptions_qs = (qs.none() for qs in [returns_qs, prod_consumptions_qs, internal_consumptions_qs])
        if qc_no:
            source_log_q = Q(source_log__qc_no__icontains=qc_no)
            in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
            returns_qs = returns_qs.filter(source_log_q)
            prod_consumptions_qs = prod_consumptions_qs.filter(source_log_q)
            internal_consumptions_qs = internal_consumptions_qs.filter(source_log_q)
        if tag_ids:
            source_log_tag_q = Q(source_log__tags__id__in=tag_ids)
            in_logs_qs = in_logs_qs.filter(tags__id__in=tag_ids).distinct()
            returns_qs = returns_qs.filter(source_log_tag_q).distinct()
            prod_consumptions_qs = prod_consumptions_qs.filter(source_log_tag_q).distinct()
            internal_consumptions_qs = internal_consumptions_qs.filter(source_log_tag_q).distinct()
        
        # Process and append each transaction type
        for log in in_logs_qs.select_related('company'):
            transactions.append({
                'date': log.release_timestamp, 'type': 'IN', 'quantity_change': log.quantity,
                'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})",
                'unit_price': log.costing_unit_price, 'source_ref': f"Receipt #{log.id}"
            })
        for ret in returns_qs.select_related('source_log'):
            transactions.append({
                'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
                'description': f"إرجاع من الإنتاج (مصدر QC: {ret.source_log.qc_no or 'N/A'})",
                'unit_price': ret.source_log.costing_unit_price, 'source_ref': f"Return #{ret.id}"
            })
        for item in prod_consumptions_qs.select_related('batch', 'source_log', 'batch__template__final_product'):
            source_desc = f"QC: {item.source_log.qc_no}" if item.source_log else 'رصيد افتتاحي'
            transactions.append({
                'date': item.batch.creation_date, 'type': 'PROD_OUT', 'quantity_change': -(item.actual_quantity or 0.0),
                'description': f"صرف لأمر تشغيل #{item.batch.shop_order_number} لإنتاج '{item.batch.template.final_product.name}'",
                'unit_price': item.cost_at_consumption, 'source_ref': f"Batch #{item.batch.id}"
            })
        for cons in internal_consumptions_qs.select_related('source_log'):
            transactions.append({
                'date': cons.consumption_date, 'type': 'EXPENSE_OUT', 'quantity_change': -cons.quantity_consumed,
                'description': f"صرف إداري لقسم: {cons.get_department_display()}",
                'unit_price': cons.cost_at_consumption / Decimal(str(cons.quantity_consumed)) if cons.quantity_consumed else Decimal('0.0'),
                'source_ref': f"Consumption #{cons.id}"
            })

    # --- Case 2: The product is a Final Product ---
    elif product.product_type == Product.ProductType.FINAL_PRODUCT:
        # Production Receipts (IN)
        receipts_qs = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id,
            status=FinishedProductReceipt.Status.RELEASED,
            release_date__gte=start_date.date(),
            release_date__lt=end_date_inclusive.date()
        )
        # Sales Dispatches (OUT)
        dispatch_qs = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product_id=product_id,
            dispatch_date__gte=start_date,
            dispatch_date__lt=end_date_inclusive
        )

        for r in receipts_qs.select_related('batch'):
            unit_cost = (r.total_cost / Decimal(str(r.total_quantity_produced))) if r.total_quantity_produced > 0 else Decimal('0.0')
            transactions.append({
                'date': timezone.make_aware(datetime.combine(r.release_date, time.min)),
                'type': 'PROD_IN', 'quantity_change': r.total_quantity_produced,
                'description': f"استلام إنتاج نهائي للتشغيلة #{r.individual_batch_number}",
                'unit_price': unit_cost, 'source_ref': f"FG Receipt #{r.id}"
            })
        for d in dispatch_qs.select_related('sales_order_item__sales_order__customer'):
            unit_cost = (d.cost_at_dispatch / Decimal(str(d.quantity))) if d.quantity > 0 else Decimal('0.0')
            transactions.append({
                'date': d.dispatch_date, 'type': 'SALE_OUT', 'quantity_change': -d.quantity,
                'description': f"صرف للعميل: {d.sales_order_item.sales_order.customer.name} (أمر بيع #{d.sales_order_item.sales_order.so_number})",
                'unit_price': unit_cost, 'source_ref': f"Dispatch #{d.id}"
            })

    # Sort all collected transactions chronologically
    transactions.sort(key=lambda x: x['date'])
    return transactions


def ledger(request: HttpRequest) -> HttpResponse:
    """
    Displays a unified, financially-transparent stock card/ledger for any product.
    """
    product_id_str = request.GET.get('product_id')
    company_id = request.GET.get('company_id')
    tag_ids = request.GET.getlist('tags')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    context = {
        'active_page': 'ledger',
        'all_products': Product.objects.all().order_by('product_type', 'name'),
        'all_companies': Company.objects.all(),
        'all_tags': ProductTag.objects.all(),
        'selected_tags': [int(t) for t in tag_ids],
    }
    
    # If no product is selected, just render the filter form
    if not product_id_str:
        template_name = 'inventory/ledger.html'
        if 'X-Partial-Request' in request.headers:
            template_name = 'inventory/partials/ledger_content.html'
        return render(request, template_name, context)

    # --- A product is selected, proceed with calculations ---
    product_id = int(product_id_str)
    product = get_object_or_404(Product, pk=product_id)
    
    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
    
    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
        end_date_inclusive = end_date + timedelta(days=1)

    # Use the single, robust service function to get the opening state
    opening_state = get_inventory_state_at_datetime(product_id, start_date)
    
    transactions_list = _get_ledger_transactions(product, start_date, end_date_inclusive, company_id, qc_no, tag_ids)
    
    # Process transactions to calculate running balances and values
    processed_transactions = []
    current_qty = opening_state['quantity']
    current_value = opening_state['value']
    
    for trx in transactions_list:
        qty_change = Decimal(str(trx['quantity_change']))
        unit_price = trx.get('unit_price', Decimal('0.0'))
        
        # For outgoing transactions, cost is already determined. For incoming, it adds to value.
        value_change = qty_change * unit_price
        
        trx_data = {
            'date': trx['date'],
            'description': trx['description'],
            'source_ref': trx['source_ref'],
            'quantity_change': qty_change,
            'balance_before': current_qty,
            'value_before': current_value,
            'unit_price': unit_price,
            'value_change': value_change,
        }
        
        current_qty += qty_change
        current_value += value_change

        trx_data.update({
            'balance_after': current_qty,
            'value_after': current_value,
            'moving_average_cost_after': (current_value / current_qty) if current_qty > 0 else Decimal('0.0')
        })
        processed_transactions.append(trx_data)

    context.update({
        'transactions': processed_transactions,
        'selected_product': product,
        'opening_balance_qty': opening_state['quantity'],
        'opening_balance_value': opening_state['value'],
        'closing_balance_qty': current_qty,
        'closing_balance_value': current_value,
    })
    
    template_name = 'inventory/ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/ledger_content.html'
    return render(request, template_name, context)


def print_ledger(request: HttpRequest) -> HttpResponse:
    """
    Generates a printable version of the detailed stock ledger.
    """
    product_id_str = request.GET.get('product_id')
    if not product_id_str:
        messages.error(request, "Please select a product to print the ledger.")
        return redirect('inventory:ledger')

    product_id = int(product_id_str)
    product = get_object_or_404(Product, pk=product_id)
    
    company_id = request.GET.get('company_id')
    tag_ids = request.GET.getlist('tags')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
    
    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = timezone.make_aware(datetime.strptime(end_date_str, '%Y-%m-%d'))
        end_date_inclusive = end_date + timedelta(days=1)

    opening_state = get_inventory_state_at_datetime(product_id, start_date)
    transactions_list = _get_ledger_transactions(product, start_date, end_date_inclusive, company_id, qc_no, tag_ids)

    processed_transactions = []
    current_qty = opening_state['quantity']
    current_value = opening_state['value']
    
    for trx in transactions_list:
        qty_change = Decimal(str(trx['quantity_change']))
        unit_price = trx.get('unit_price', Decimal('0.0'))
        value_change = qty_change * unit_price
        
        trx_data = {
            'date': trx['date'], 'description': trx['description'],
            'quantity_change': qty_change, 'balance_before': current_qty,
            'unit_price': unit_price, 'value_change': value_change,
        }
        current_qty += qty_change
        current_value += value_change
        trx_data['balance_after'] = current_qty
        processed_transactions.append(trx_data)

    context = {
        'transactions': processed_transactions,
        'product': product,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'print_date': timezone.now(),
        'opening_balance_qty': opening_state['quantity'],
        'opening_balance_value': opening_state['value'],
        'closing_balance_qty': current_qty,
        'closing_balance_value': current_value,
    }
    return render(request, 'inventory/print_ledger_enhanced.html', context)


# --- The rest of the file (stock_valuation, analysis, visuals) remains unchanged but is included for completeness ---

def stock_valuation(request: HttpRequest) -> HttpResponse:
    """
    Displays a stock valuation report showing current stock, cost, and total value for ALL products.
    """
    valuation_data = []
    grand_total_value = Decimal('0.0')

    # Query all products to ensure we get both primitive and final goods
    all_products = Product.objects.all().order_by('product_type', 'name')
    
    for product in all_products:
        # Use the single reliable function for all product types
        state = get_inventory_state_at_datetime(product.id, timezone.now())
        current_stock = state['quantity']
        
        # Value is directly from the state calculation, which is more accurate than multiplying by the potentially stale MAC on the model
        stock_value = state['value']
        grand_total_value += stock_value
        
        if current_stock > 0: # Only show items with stock
            valuation_data.append({
                'product': product,
                'current_stock': current_stock,
                'avg_cost': (stock_value / current_stock) if current_stock > 0 else Decimal('0.0'),
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
        'active_page': 'visuals',
        'data': analysis_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/analysis_content.html', context)
    return render(request, 'inventory/analysis.html', context)


def visuals(request: HttpRequest) -> HttpResponse:
    """
    Displays a powerful analysis dashboard with selectable modes for
    raw materials, finished products, and expenses.
    """
    analysis_type = request.GET.get('type', 'raw_material')
    
    today = timezone.now()
    default_start = today.replace(day=1)
    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    
    consumable_products = Product.objects.filter(Q(product_type=Product.ProductType.MRO) | Q(product_type=Product.ProductType.CONSUMABLE))
    expense_product_types = [
        (Product.ProductType.MRO, Product.ProductType.MRO.label),
        (Product.ProductType.CONSUMABLE, Product.ProductType.CONSUMABLE.label),
    ]

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
            total_in_value = receipts.annotate(line_total=ExpressionWrapper(F('quantity') * F('costing_unit_price'), output_field=DecimalField())).aggregate(total=Coalesce(Sum('line_total'), Decimal('0.0')))['total']
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
            supplier_analysis_data = receipts.filter(company__isnull=False).values('company__name').annotate(receipt_count=Count('id'), total_qty=Sum('quantity', output_field=DecimalField()), total_val=Sum(ExpressionWrapper(F('quantity') * F('costing_unit_price'), output_field=DecimalField()))).annotate(avg_price=F('total_val') / F('total_qty')).order_by('-total_val')
            
            transactions_list = _get_ledger_transactions(product, start_date, end_date_inclusive, company_id, qc_no, tag_ids)
            opening_balance = get_inventory_state_at_datetime(product_id, start_date)['quantity']
            running_balance = float(opening_balance)
            chart_labels = [start_date.strftime('%Y-%m-%d (Start)')]; balance_data = [round(running_balance, 3)]
            for trx in transactions_list:
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
            'selected_tags': [int(t) for t in tag_ids],
        })
    
    elif analysis_type == 'finished_product':
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
    
    elif analysis_type == 'expense':
        expense_product_type = request.GET.get('expense_product_type')
        expense_product_id_str = request.GET.get('expense_product_id')
        expense_product_id = int(expense_product_id_str) if expense_product_id_str else None

        expense_kpi_data = {}
        department_data, category_trend_data, top_items_data = ({'labels': [], 'datasets': []} for _ in range(3))

        inventory_consumptions = InventoryConsumption.objects.filter(consumption_date__gte=start_date, consumption_date__lt=end_date_inclusive)
        general_expenses = ExpenseLog.objects.filter(expense_date__gte=start_date.date(), expense_date__lt=end_date_inclusive.date())

        if expense_product_type:
            inventory_consumptions = inventory_consumptions.filter(product__product_type=expense_product_type)
        if expense_product_id:
            inventory_consumptions = inventory_consumptions.filter(product_id=expense_product_id)

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

        dept_expenses = inventory_consumptions.values('department').annotate(total=Sum('cost_at_consumption')).order_by('-total')
        if dept_expenses:
            department_data = {
                'labels': [dict(InventoryConsumption.Department.choices).get(d['department']) for d in dept_expenses],
                'datasets': [{'data': [d['total'] for d in dept_expenses]}]
            }

        daily_gen_expenses = general_expenses.annotate(day=TruncDay('expense_date')).values('day').annotate(total=Sum('amount')).order_by('day')
        if daily_gen_expenses:
            category_trend_data = {
                'labels': [d['day'].strftime('%Y-%m-%d') for d in daily_gen_expenses],
                'datasets': [{'label': 'المصروفات العامة اليومية', 'data': [d['total'] for d in daily_gen_expenses], 'borderColor': '#6f42c1', 'backgroundColor': 'rgba(111, 66, 193, 0.2)', 'fill': True, 'tension': 0.1}]
            }
        
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