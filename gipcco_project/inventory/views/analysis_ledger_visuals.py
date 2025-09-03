# gipcco_project/inventory/views/analysis_ledger_visuals.py

import json
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum, Q, F, FloatField, Value
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import Batch, BatchItem, Company, InventoryLog, Product, ProductTag, ProductionReturn
from .helpers import get_inventory_state_at_datetime, _get_ledger_transactions

# --- Analysis, Ledger & Valuation Views ---

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
        'active_page': 'analysis',
        'data': analysis_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/analysis_content.html', context)
    return render(request, 'inventory/analysis.html', context)


def ledger(request: HttpRequest) -> HttpResponse:
    """
    Displays the stock card / ledger for products with full financial transparency.
    """
    product_id = request.GET.get('product_id')
    company_id = request.GET.get('company_id')
    tag_ids = request.GET.getlist('tags')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    all_primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
    all_companies = Company.objects.all()
    all_tags = ProductTag.objects.all()
    
    context = {
        'active_page': 'ledger',
        'all_primitive_products': all_primitive_products,
        'all_companies': all_companies,
        'all_tags': all_tags,
        'selected_tags': tag_ids, 
    }
    
    if not any([product_id, company_id, qc_no, start_date_str, end_date_str, tag_ids]):
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
    
    transactions = _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids)
    
    opening_state = {'quantity': Decimal('0.0'), 'value': Decimal('0.0')}
    product_unit = ""
    if product_id:
        opening_state = get_inventory_state_at_datetime(int(product_id), start_date)
        product_unit = get_object_or_404(Product, pk=product_id).unit
    
    processed_transactions = []
    if product_id:
        current_qty = opening_state['quantity']
        current_value = opening_state['value']
        for trx in transactions:
            trx['balance_before'] = current_qty
            trx['value_before'] = current_value
            
            qty_change = Decimal(str(trx['quantity_change']))
            value_change = Decimal('0.0')

            if trx['type'] == 'IN':
                price = trx['unit_price'] or Decimal('0.0')
                value_change = qty_change * price
            elif trx['type'] == 'OUT':
                cost = trx['cost_at_consumption'] or Decimal('0.0')
                value_change = qty_change * cost
            elif trx['type'] == 'RETURN_IN':
                avg_cost_before = (current_value / current_qty) if current_qty > 0 else Decimal('0.0')
                value_change = qty_change * avg_cost_before
            
            trx['value_change'] = value_change
            current_qty += qty_change
            current_value += value_change

            trx['balance_after'] = current_qty
            trx['value_after'] = current_value
            
            # --- THIS IS THE KEY ADDITION ---
            # Calculate and add the new Moving Average Cost for transparency
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
        'opening_balance_for_period': opening_state['quantity'] if product_id else 'N/A',
        'opening_value_for_period': opening_state['value'] if product_id else 'N/A',
        'unit': product_unit,
    })
    
    template_name = 'inventory/ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/ledger_content.html'
    return render(request, template_name, context)


def visuals(request: HttpRequest) -> HttpResponse:
    # This function remains unchanged.
    today = timezone.now()
    default_start = today.replace(day=1)
    product_id_str = request.GET.get('product_id')
    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', today.strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    in_out_data, consumption_data, variance_data = ({'labels': [], 'datasets': []} for _ in range(3))
    product_id = None
    if product_id_str:
        product_id = int(product_id_str)
        opening_balance = get_inventory_state_at_datetime(product_id, start_date)['quantity']
        all_transactions = []
        for log in InventoryLog.objects.filter(product_id=product_id, timestamp__gte=start_date, timestamp__lt=end_date_inclusive):
            all_transactions.append({'date': log.timestamp, 'change': log.quantity})
        for ret in ProductionReturn.objects.filter(product_id=product_id, return_date__gte=start_date, return_date__lt=end_date_inclusive):
            all_transactions.append({'date': ret.return_date, 'change': ret.quantity})
        for item in BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive):
            all_transactions.append({'date': item.batch.creation_date, 'change': -(item.actual_quantity or 0.0)})
        all_transactions.sort(key=lambda x: x['date'])
        running_balance = float(opening_balance)
        chart_labels = [start_date.strftime('%Y-%m-%d (Start)')]
        balance_data = [round(running_balance, 3)]
        for trx in all_transactions:
            running_balance += trx['change']
            chart_labels.append(trx['date'].strftime('%Y-%m-%d'))
            balance_data.append(round(running_balance, 3))
        in_out_data = {'labels': chart_labels, 'datasets': [{'label': 'الرصيد المتراكم', 'data': balance_data, 'borderColor': '#0d6efd', 'backgroundColor': 'rgba(13, 110, 253, 0.2)', 'fill': True, 'tension': 0.1}]}
        consumption_rows = BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive).values('batch__template__final_product__name').annotate(total_consumed=Sum('actual_quantity')).order_by('-total_consumed')
        if consumption_rows:
            consumption_data = {'labels': [r['batch__template__final_product__name'] for r in consumption_rows], 'datasets': [{'data': [r['total_consumed'] for r in consumption_rows]}]}
        variance_rows = BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive, actual_quantity__isnull=False, theoretical_quantity__isnull=False).annotate(label=F('batch__batch_number'), variance=F('actual_quantity') - F('theoretical_quantity')).order_by('batch__creation_date')
        if variance_rows:
            variance_data = {'labels': [f"{r.label} ({r.batch.creation_date.strftime('%d-%m')})" for r in variance_rows], 'datasets': [{'label': 'الفرق (الفعلي - النظري)', 'data': [r.variance for r in variance_rows]}]}
    context = {'active_page': 'visuals', 'all_primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)), 'in_out_data': json.dumps(in_out_data), 'consumption_data': json.dumps(consumption_data), 'variance_data': json.dumps(variance_data), 'selected_product_id': product_id, 'start_date': start_date_str, 'end_date': end_date_str, 'is_partial_request': 'X-Partial-Request' in request.headers}
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/visuals_content.html', context)
    return render(request, 'inventory/visuals.html', context)



def print_ledger(request: HttpRequest) -> HttpResponse:
    # This function now uses the same logic as the main ledger view
    # but renders to a new, enhanced, print-specific template.
    product_id = request.GET.get('product_id')
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

    transactions = _get_ledger_transactions(product_id, company_id, qc_no, start_date, end_date_inclusive, tag_ids)
    
    opening_state = {'quantity': Decimal('0.0'), 'value': Decimal('0.0')}
    if product_id:
        opening_state = get_inventory_state_at_datetime(int(product_id), start_date)
    
    processed_transactions = []
    current_qty = opening_state['quantity']
    current_value = opening_state['value']
    for trx in transactions:
        trx['balance_before'] = current_qty
        trx['value_before'] = current_value
        qty_change = Decimal(str(trx['quantity_change']))
        value_change = Decimal('0.0')

        if trx['type'] == 'IN':
            price = trx['unit_price'] or Decimal('0.0')
            value_change = qty_change * price
        elif trx['type'] == 'OUT':
            cost = trx['cost_at_consumption'] or Decimal('0.0')
            value_change = qty_change * cost
        elif trx['type'] == 'RETURN_IN':
            avg_cost_before = (current_value / current_qty) if current_qty > 0 else Decimal('0.0')
            value_change = qty_change * avg_cost_before
        
        trx['value_change'] = value_change
        current_qty += qty_change
        current_value += value_change
        trx['balance_after'] = current_qty
        trx['value_after'] = current_value
        processed_transactions.append(trx)

    closing_qty = current_qty if product_id else 'N/A'
    closing_value = current_value if product_id else 'N/A'
    
    report_title = "كشف حساب المخزون العام"
    product_details = None
    if product_id:
        product_details = get_object_or_404(Product, pk=product_id)
        report_title = f"كشف حساب مخزون - {product_details.name}"

    selected_tags = ProductTag.objects.filter(id__in=tag_ids) if tag_ids else []

    context = {
        'transactions': processed_transactions,
        'report_title': report_title,
        'product_details': product_details,
        'selected_tags': selected_tags,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'print_date': timezone.now(),
        'opening_balance': opening_state['quantity'] if product_id else 'N/A',
        'opening_value': opening_state['value'] if product_id else 'N/A',
        'closing_balance': closing_qty,
        'closing_value': closing_value,
    }
    # --- RENDER THE NEW, ENHANCED TEMPLATE ---
    return render(request, 'inventory/print_ledger_enhanced.html', context)