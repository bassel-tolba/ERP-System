# gipcco_project/inventory/views/analysis_ledger_visuals.py

import json
from datetime import datetime, timedelta

from django.contrib import messages
from django.db.models import Sum, Q, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..models import Batch, BatchItem, Company, InventoryLog, Product, ProductTag, ProductionReturn
from .helpers import get_opening_balance_for_period, _get_ledger_transactions

# --- Analysis & Ledger Views ---

# The 'analysis' function remains unchanged.
def analysis(request: HttpRequest) -> HttpResponse:
    """
    Displays a stock analysis report for a given date range.
    """
    today = timezone.now()
    default_start_date = today.replace(month=1, day=1)
    
    start_date_str = request.POST.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.POST.get('end_date', today.strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    end_date_inclusive = end_date + timedelta(days=1)
    
    analysis_data = []
    primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))

    for product in primitive_products:
        opening_balance = get_opening_balance_for_period(product.id, start_date)
        
        total_in_log = product.inventory_logs.filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive).aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
        total_in_returns = product.production_returns.filter(return_date__gte=start_date, return_date__lt=end_date_inclusive).aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
        total_in = total_in_log + total_in_returns

        total_out = product.batch_items.filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
        
        closing_balance = opening_balance + total_in - total_out
        
        analysis_data.append({
            'id': product.id, 'name': product.name, 'code': product.code, 'unit': product.unit,
            'opening_balance': opening_balance, 'total_in': total_in, 'total_out': total_out,
            'closing_balance': closing_balance
        })

    context = {
        'active_page': 'analysis',
        'data': analysis_data,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/analysis_content.html', context)
    return render(request, 'inventory/analysis.html', context)


# --- CORRECTED ledger view ---
def ledger(request: HttpRequest) -> HttpResponse:
    """
    Displays the stock card / ledger for products based on filters.
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
        # --- FIX: Pass the selected tag IDs to the context for the template to use ---
        'selected_tag_ids': tag_ids, 
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
    
    opening_balance = 0
    product_unit = ""
    if product_id:
        opening_balance = get_opening_balance_for_period(int(product_id), start_date)
        product_unit = get_object_or_404(Product, pk=product_id).unit
    
    transactions_with_balance = []
    if product_id:
        current_balance = opening_balance
        for trx in transactions:
            trx['balance_before'] = current_balance
            current_balance += trx['quantity_change']
            trx['balance_after'] = current_balance
            transactions_with_balance.append(trx)
    else:
        for trx in transactions:
            trx['balance_before'] = '---'
            trx['balance_after'] = '---'
            transactions_with_balance.append(trx)

    context.update({
        'transactions': transactions_with_balance,
        'opening_balance_for_period': opening_balance if product_id else 'N/A',
        'unit': product_unit,
    })
    
    template_name = 'inventory/ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/ledger_content.html'
    return render(request, template_name, context)

# The 'visuals' and 'print_ledger' functions remain unchanged from the last working version.
# I will include them for completeness.

def visuals(request: HttpRequest) -> HttpResponse:
    """
    Provides data for charts and visualizations.
    """
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
        
        opening_balance = get_opening_balance_for_period(product_id, start_date)
        
        all_transactions = []
        for log in InventoryLog.objects.filter(product_id=product_id, timestamp__gte=start_date, timestamp__lt=end_date_inclusive):
            all_transactions.append({'date': log.timestamp, 'change': log.quantity})
        for ret in ProductionReturn.objects.filter(product_id=product_id, return_date__gte=start_date, return_date__lt=end_date_inclusive):
            all_transactions.append({'date': ret.return_date, 'change': ret.quantity})
        for item in BatchItem.objects.filter(primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive):
            all_transactions.append({'date': item.batch.creation_date, 'change': -item.actual_quantity})
        
        all_transactions.sort(key=lambda x: x['date'])

        running_balance = opening_balance
        chart_labels = [start_date.strftime('%Y-%m-%d (Start)')]
        balance_data = [round(opening_balance, 3)]
        for trx in all_transactions:
            running_balance += trx['change']
            chart_labels.append(trx['date'].strftime('%Y-%m-%d'))
            balance_data.append(round(running_balance, 3))
            
        in_out_data = {'labels': chart_labels, 'datasets': [{'label': 'الرصيد المتراكم', 'data': balance_data, 'borderColor': '#0d6efd', 'backgroundColor': 'rgba(13, 110, 253, 0.2)', 'fill': True, 'tension': 0.1}]}

        consumption_rows = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive
        ).values('batch__template__final_product__name').annotate(
            total_consumed=Sum('actual_quantity')
        ).order_by('-total_consumed')
        if consumption_rows:
            consumption_data = {
                'labels': [r['batch__template__final_product__name'] for r in consumption_rows],
                'datasets': [{'data': [r['total_consumed'] for r in consumption_rows]}]
            }

        variance_rows = BatchItem.objects.filter(
            primitive_product_id=product_id, batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive,
            actual_quantity__isnull=False, theoretical_quantity__isnull=False
        ).annotate(
            label=F('batch__batch_number'),
            variance=F('actual_quantity') - F('theoretical_quantity')
        ).order_by('batch__creation_date')
        if variance_rows:
            variance_data = {
                'labels': [f"{r.label} ({r.batch.creation_date.strftime('%d-%m')})" for r in variance_rows],
                'datasets': [{'label': 'الفرق (الفعلي - النظري)', 'data': [r.variance for r in variance_rows]}]
            }

    context = {
        'active_page': 'visuals',
        'all_primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'in_out_data': json.dumps(in_out_data),
        'consumption_data': json.dumps(consumption_data),
        'variance_data': json.dumps(variance_data),
        'selected_product_id': product_id,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/visuals_content.html', context)
    return render(request, 'inventory/visuals.html', context)


def print_ledger(request: HttpRequest) -> HttpResponse:
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
    
    opening_balance_for_period = 0
    if product_id:
        opening_balance_for_period = get_opening_balance_for_period(int(product_id), start_date)
    
    transactions_with_balance = []
    current_balance = opening_balance_for_period
    for row in transactions:
        if product_id:
            row['balance_before'] = current_balance
            current_balance += row['quantity_change']
            row['balance_after'] = current_balance
        else:
            row['balance_before'] = '---'
            row['balance_after'] = '---'
        transactions_with_balance.append(row)

    closing_balance = current_balance if product_id else 'N/A'
    
    report_title = "كشف حساب المخزون العام"
    product_details = None
    if product_id:
        product_details = get_object_or_404(Product, pk=product_id)
        report_title = f"كشف حساب مخزون - {product_details.name}"

    selected_tags = []
    if tag_ids:
        selected_tags = ProductTag.objects.filter(id__in=tag_ids)
        if not product_id: 
            report_title = f"كشف حساب للمنتجات بالوسوم المحددة"

    batch_details_map = {}
    batch_ids_to_fetch = {trx['batch_id'] for trx in transactions if trx['type'] == 'OUT' and trx['batch_id']}
    if batch_ids_to_fetch:
        batches_from_db = Batch.objects.filter(id__in=batch_ids_to_fetch).select_related('template__final_product').prefetch_related('items__primitive_product', 'items__source_log')
        for batch in batches_from_db:
            item_list_serialized = []
            for item in batch.items.all():
                source_qc = 'رصيد افتتاحي'
                if item.source_type != BatchItem.SourceType.OPENING_BALANCE:
                    source_qc = item.source_log.qc_no if item.source_log else 'N/A'
                item_list_serialized.append({'primitive_product_name': item.primitive_product.name, 'source_qc_no': source_qc, 'theoretical_quantity': item.theoretical_quantity, 'actual_quantity': item.actual_quantity, 'unit': item.primitive_product.unit})
            batch_details_map[batch.id] = {'info': batch, 'item_list': item_list_serialized}

    context = {
        'transactions': transactions_with_balance,
        'batch_details_map': batch_details_map,
        'report_title': report_title,
        'product_details': product_details,
        'selected_tags': selected_tags,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'print_date': timezone.now(),
        'opening_balance_for_period': opening_balance_for_period if product_id else 'N/A',
        'closing_balance': closing_balance,
    }
    return render(request, 'inventory/print_ledger.html', context)