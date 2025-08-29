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

from .models import (Batch, BatchItem, Company, InventoryLog, OpeningBalance,
                     Product, ProductionReturn, ShopOrderTemplate, TemplateItem)

ITEMS_PER_PAGE = 20

# Get an instance of the logger for this module
logger = logging.getLogger(__name__)


# ==============================================================================
#  Helper Functions (Converted to Django ORM)
# ==============================================================================

def check_and_update_batch_customization(batch_id: int):
    """
    Checks if any item in a batch is customized and updates the batch flag.
    A batch is customized if the number of items differs from its template,
    or if any item's actual_quantity differs from its theoretical_quantity.

    Args:
        batch_id: The primary key of the Batch to check.
    """
    try:
        batch = Batch.objects.select_related('template').get(pk=batch_id)
        template_item_count = batch.template.items.count()
        batch_item_count = batch.items.count()

        is_customized = False
        if template_item_count != batch_item_count:
            is_customized = True
        else:
            # Check for differences in quantities for all items in the batch
            # Using an aggregate query to see if any item has a mismatch.
            if batch.items.filter(~Q(actual_quantity=F('theoretical_quantity'))).exists():
                is_customized = True
        
        if batch.is_customized != is_customized:
            batch.is_customized = is_customized
            batch.save(update_fields=['is_customized'])

    except Batch.DoesNotExist:
        # Batch might have been deleted, so we do nothing.
        pass

def get_opening_balance_for_period(product_id: int, start_date: datetime) -> float:
    """
    Calculates the opening balance for a specific product at the beginning of a given start_date.
    This version is rewritten using the Django ORM.

    Args:
        product_id: The ID of the Product.
        start_date: The beginning of the period for which to find the opening balance.

    Returns:
        The calculated opening balance as a float.
    """
    # Find the most recent opening balance entry on or before the start date.
    most_recent_balance_entry = OpeningBalance.objects.filter(
        product_id=product_id,
        balance_date__lte=start_date
    ).order_by('-balance_date').first()

    opening_base_qty = 0.0
    # Use a very early date if no balance entry is found, to include all historical transactions.
    effective_balance_date = datetime(1, 1, 1, tzinfo=timezone.get_current_timezone())

    if most_recent_balance_entry:
        opening_base_qty = most_recent_balance_entry.quantity
        effective_balance_date = most_recent_balance_entry.balance_date

    # Sum all transactions between the effective balance date and the start of our period.
    # We use Coalesce to handle cases where the Sum is None (no records found).
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


def validate_stock_availability(product_ids, quantities, source_ids, batch_creation_date, batch_id_to_exclude=None):
    """
    Validates if requested quantities of products are available from specified sources.
    Rewritten using Django ORM for better performance and safety.

    Args:
        product_ids (list): List of product IDs.
        quantities (list): List of corresponding quantities requested.
        source_ids (list): List of source IDs ('-1' for opening balance, otherwise InventoryLog ID).
        batch_creation_date (datetime): The creation date of the batch being created/edited.
        batch_id_to_exclude (int, optional): A batch ID to exclude from calculations (used when editing).

    Returns:
        A tuple (is_valid, error_message).
    """
    # Consolidate requests to sum up quantities for the same product from the same source.
    requests = {}
    for i, source_id_str in enumerate(source_ids):
        if not source_id_str or not product_ids[i] or not quantities[i]:
            continue
        try:
            source_id = int(source_id_str)
            quantity = float(quantities[i])
            product_id = int(product_ids[i])
        except (ValueError, TypeError):
            continue
        request_key = (source_id, product_id)
        requests[request_key] = requests.get(request_key, 0) + quantity

    for request_key, total_requested in requests.items():
        source_id, product_id = request_key
        product = Product.objects.get(pk=product_id)

        # Base queryset for BatchItems to calculate used quantities
        used_items_qs = BatchItem.objects.filter(primitive_product_id=product_id)
        if batch_id_to_exclude:
            used_items_qs = used_items_qs.exclude(batch_id=batch_id_to_exclude)

        if source_id == -1:  # Opening Balance Check
            latest_balance = OpeningBalance.objects.filter(product_id=product_id).order_by('-balance_date').first()
            if not latest_balance:
                return (False, f"لا يوجد رصيد افتتاحي للمنتج '{product.name}'.")
            
            if latest_balance.balance_date.date() > batch_creation_date.date():
                return (False, f"لا يمكن استخدام الرصيد الافتتاحي للمنتج '{product.name}' بتاريخ ({latest_balance.balance_date.strftime('%Y-%m-%d')}) لأمر تشغيل بتاريخ أقدم ({batch_creation_date.strftime('%Y-%m-%d')}).")

            total_available_from_ob = latest_balance.quantity
            already_used = used_items_qs.filter(source_type=BatchItem.SourceType.OPENING_BALANCE).aggregate(
                total=Coalesce(Sum('actual_quantity'), 0.0)
            )['total']
            
            available_stock = total_available_from_ob - already_used
            if total_requested > available_stock + 0.001:
                return (False, f"كمية غير كافية للمنتج '{product.name}' من الرصيد الافتتاحي. مطلوب: {total_requested}, متاح: {available_stock:.3f}")
        
        else:  # Inventory Log Check
            try:
                log_entry = InventoryLog.objects.get(pk=source_id)
            except InventoryLog.DoesNotExist:
                return (False, f"مصدر المخزون برقم {source_id} غير موجود.")

            if log_entry.timestamp.date() > batch_creation_date.date():
                return (False, f"لا يمكن استخدام مصدر QC '{log_entry.qc_no}' للمنتج '{product.name}' بتاريخ ({log_entry.timestamp.strftime('%Y-%m-%d')}) لأمر تشغيل بتاريخ أقدم ({batch_creation_date.strftime('%Y-%m-%d')}).")
            
            if product_id != log_entry.product_id:
                return (False, f"عدم تطابق المنتج. تم طلب '{product.name}' من مصدر QC '{log_entry.qc_no}' الذي يخص منتج '{log_entry.product.name}'.")

            total_available_from_log = log_entry.quantity
            
            total_returned = log_entry.production_returns.aggregate(
                total=Coalesce(Sum('quantity'), 0.0)
            )['total']

            already_used = used_items_qs.filter(source_log_id=source_id).aggregate(
                total=Coalesce(Sum('actual_quantity'), 0.0)
            )['total']
            
            available_stock = total_available_from_log - already_used + total_returned
            if total_requested > available_stock + 0.001:
                return (False, f"كمية غير كافية للمنتج '{product.name}' من المصدر QC '{log_entry.qc_no}'. مطلوب: {total_requested}, متاح: {available_stock:.3f}")

    return (True, None)

# ==============================================================================
#  Django Views
# ==============================================================================


# --- Dashboard & Records ---
def index(request: HttpRequest) -> HttpResponse:
    """
    Handles the dashboard page. Displays recent inventory logs and a form to add new ones.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        company_id = request.POST.get('company_id')
        quantity = request.POST.get('quantity')
        date_str = request.POST.get('entry_date')
        qc_no = request.POST.get('qc_no')

        if not all([product_id, company_id, quantity, date_str]):
            messages.warning(request, 'الرجاء تعبئة جميع الحقول.')
        else:
            try:
                entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                entry_datetime = datetime.combine(entry_date, timezone.now().time())
                InventoryLog.objects.create(
                    product_id=product_id,
                    company_id=company_id,
                    quantity=quantity,
                    timestamp=entry_datetime,
                    qc_no=qc_no
                )
                messages.success(request, 'تم تسجيل حركة المخزون بنجاح!')
            except (ValueError, TypeError):
                messages.error(request, 'صيغة التاريخ غير صالحة.')
        return redirect('inventory:index')

    context = {
        'active_page': 'index',
        'logs': InventoryLog.objects.select_related('product', 'company').all()[:15],
        'all_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'all_companies': Company.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    
    # --- MODIFICATION FOR DYNAMIC LOADING ---
    # Check for the custom header sent by our JavaScript.
    if 'X-Partial-Request' in request.headers:
        # If it's a partial request, render only the content block.
        return render(request, 'inventory/partials/dashboard_content.html', context)
    else:
        # Otherwise, render the full page with the layout.
        return render(request, 'inventory/dashboard.html', context)


def records(request: HttpRequest) -> HttpResponse:
    """
    Displays a full list of all inventory log records.
    """
    context = {
        'active_page': 'records',
        'logs': InventoryLog.objects.select_related('product', 'company').all(),
        'all_products': Product.objects.all(),
        'all_companies': Company.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/records_content.html', context)
    return render(request, 'inventory/records.html', context)

@require_POST
def edit_record(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing inventory log record.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    
    product_id = request.POST.get('product_id')
    company_id = request.POST.get('company_id')
    quantity = request.POST.get('quantity')
    date_str = request.POST.get('entry_date')
    qc_no = request.POST.get('qc_no')

    if not all([product_id, company_id, quantity, date_str]):
        messages.warning(request, 'الرجاء تعبئة جميع الحقول.')
    else:
        try:
            new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            original_time = log_entry.timestamp.time()
            new_datetime = datetime.combine(new_date, original_time)
            
            log_entry.product_id = product_id
            log_entry.company_id = company_id
            log_entry.quantity = quantity
            log_entry.timestamp = new_datetime
            log_entry.qc_no = qc_no
            log_entry.save()
            messages.success(request, "تم تعديل السجل بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            
    return redirect('inventory:records')

@require_POST
def delete_record(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting an inventory log record.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    log_entry.delete()
    messages.info(request, 'تم حذف السجل بنجاح.')
    return redirect('inventory:records')

# --- Company and Product CRUD Views ---

def companies(request: HttpRequest) -> HttpResponse:
    """
    Manages companies. Handles both displaying the list and adding a new company.
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            company, created = Company.objects.get_or_create(name=name)
            if created:
                messages.success(request, f'تمت إضافة شركة "{name}" بنجاح.')
            else:
                messages.error(request, f'اسم الشركة "{name}" موجود بالفعل.')
        return redirect('inventory:companies')

    context = {
        'active_page': 'companies',
        'companies': Company.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/companies_content.html', context)
    return render(request, 'inventory/companies.html', context)


@require_POST
def edit_company(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing a company's name.
    """
    company = get_object_or_404(Company, pk=pk)
    name = request.POST.get('name')
    if name:
        if Company.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, "هذا الاسم مستخدم بالفعل.")
        else:
            company.name = name
            company.save()
            messages.success(request, "تم تعديل اسم الشركة بنجاح.")
    return redirect('inventory:companies')


@require_POST
def delete_company(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a company.
    """
    company = get_object_or_404(Company, pk=pk)
    company.delete()
    messages.info(request, 'تم حذف الشركة بنجاح.')
    return redirect('inventory:companies')


def products(request: HttpRequest) -> HttpResponse:
    """
    Manages products. Handles both displaying the list and adding a new product.
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        product_type = request.POST.get('product_type')
        unit = request.POST.get('unit')
        
        if Product.objects.filter(code=code).exists():
            messages.error(request, f'كود المنتج "{code}" موجود بالفعل.')
        else:
            Product.objects.create(name=name, code=code, product_type=product_type, unit=unit)
            messages.success(request, f'تمت إضافة المنتج "{name}" بنجاح.')
        return redirect('inventory:products')

    context = {
        'active_page': 'products',
        'products': Product.objects.order_by('name'),
        'product_type_choices': Product.ProductType.choices,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/products_content.html', context)
    return render(request, 'inventory/products.html', context)


@require_POST
def edit_product(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing product.
    """
    product = get_object_or_404(Product, pk=pk)
    name = request.POST.get('name')
    code = request.POST.get('code')
    p_type = request.POST.get('product_type')
    unit = request.POST.get('unit')

    if all([name, code, p_type, unit]):
        if Product.objects.filter(code=code).exclude(pk=pk).exists():
            messages.error(request, "كود المنتج موجود بالفعل لمنتج آخر.")
        else:
            product.name = name
            product.code = code
            product.product_type = p_type
            product.unit = unit
            product.save()
            messages.success(request, "تم تعديل المنتج بنجاح.")
    return redirect('inventory:products')


@require_POST
def delete_product(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a product.
    """
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.info(request, 'تم حذف المنتج وجميع سجلاته بنجاح.')
    return redirect('inventory:products')

# --- Template Views ---

def shop_order_templates(request: HttpRequest) -> HttpResponse:
    """
    Manages shop order templates. Handles creating and listing templates.
    """
    if request.method == 'POST':
        template_name = request.POST.get('template_name')
        final_product_id = request.POST.get('final_product_id')
        primitive_ids = request.POST.getlist('primitive_product_id')
        quantities = request.POST.getlist('theoretical_quantity')

        if not all([template_name, final_product_id, primitive_ids, quantities]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لإنشاء القالب.")
            return redirect('inventory:shop_order_templates')

        try:
            with transaction.atomic():
                template = ShopOrderTemplate.objects.create(
                    name=template_name,
                    final_product_id=final_product_id
                )
                items_to_create = []
                for pid, qty in zip(primitive_ids, quantities):
                    if pid and qty:
                        items_to_create.append(
                            TemplateItem(
                                template=template,
                                primitive_product_id=pid,
                                theoretical_quantity=qty
                            )
                        )
                TemplateItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم إنشاء قالب أمر التشغيل بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء القالب: {e}")
        
        return redirect('inventory:shop_order_templates')
    
    # Logic for copying a template
    source_template = None
    source_items = None
    copy_from_id = request.GET.get('copy_from')
    if copy_from_id:
        source_template = get_object_or_404(ShopOrderTemplate.objects.prefetch_related('items'), pk=copy_from_id)
        source_items = source_template.items.all()

    context = {
        'active_page': 'shop_orders',
        'templates': ShopOrderTemplate.objects.select_related('final_product').all(),
        'final_products': Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT),
        'primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'source_template': source_template,
        'source_items': source_items,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_templates_content.html', context)
    return render(request, 'inventory/shop_order_templates.html', context)


@require_POST
def delete_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a shop order template.
    """
    template = get_object_or_404(ShopOrderTemplate, pk=pk)
    template.delete()
    messages.info(request, 'تم حذف القالب بنجاح.')
    return redirect('inventory:shop_order_templates')


def view_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single shop order template.
    """
    template = get_object_or_404(ShopOrderTemplate.objects.select_related('final_product'), pk=pk)
    items = template.items.select_related('primitive_product').order_by('primitive_product__name')
    context = {
        'active_page': 'shop_orders',
        'template': template,
        'items': items,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_template_view_content.html', context)
    return render(request, 'inventory/shop_order_template_view.html', context)


def edit_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles both displaying the form to edit a template and processing the submission.
    """
    template = get_object_or_404(ShopOrderTemplate, pk=pk)
    
    if request.method == 'POST':
        template_name = request.POST.get('template_name')
        final_product_id = request.POST.get('final_product_id')
        primitive_ids = request.POST.getlist('primitive_product_id')
        quantities = request.POST.getlist('theoretical_quantity')
        
        if not all([template_name, final_product_id, primitive_ids, quantities]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لتعديل القالب.")
            return redirect('inventory:edit_shop_order_template', pk=pk)
        
        try:
            with transaction.atomic():
                template.name = template_name
                template.final_product_id = final_product_id
                template.save()

                # Delete old items and create new ones
                template.items.all().delete()
                
                items_to_create = []
                for pid, qty in zip(primitive_ids, quantities):
                    if pid and qty:
                        items_to_create.append(
                            TemplateItem(
                                template=template,
                                primitive_product_id=pid,
                                theoretical_quantity=qty
                            )
                        )
                TemplateItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم تحديث القالب بنجاح.")
            return redirect('inventory:view_shop_order_template', pk=pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تحديث القالب: {e}")
            return redirect('inventory:edit_shop_order_template', pk=pk)

    context = {
        'active_page': 'shop_orders',
        'template': template,
        'template_items': template.items.all(),
        'final_products': Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT),
        'primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_template_edit_content.html', context)
    return render(request, 'inventory/shop_order_template_edit.html', context)

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
        'batches': page_obj,  # Pass the page object to the template
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
    # This nested function prepares the complex data needed for the form.
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
            
            # Opening Balance stock
            latest_balance = prod.opening_balances.order_by('-balance_date').first()
            if latest_balance:
                used_from_ob = BatchItem.objects.filter(
                    primitive_product=prod, source_type=BatchItem.SourceType.OPENING_BALANCE
                ).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
                remaining_ob_qty = latest_balance.quantity - used_from_ob
                if remaining_ob_qty > 0.001:
                    stock_list.append({'id': -1, 'qc_no': 'رصيد افتتاحي', 'timestamp': latest_balance.balance_date, 'remaining_quantity': remaining_ob_qty})

            # Inventory Log stock
            inventory_logs = prod.inventory_logs.annotate(
                total_used=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
                total_returned=Coalesce(Sum('production_returns__quantity'), 0.0, output_field=FloatField())
            ).annotate(
                remaining_quantity=F('quantity') - F('total_used') + F('total_returned')
            )
            
            for log in inventory_logs:
                if log.remaining_quantity > 0.001:
                    stock_list.append({'id': log.id, 'qc_no': log.qc_no or 'N/A', 'timestamp': log.timestamp, 'remaining_quantity': log.remaining_quantity})
            
            stock_list.sort(key=lambda x: x['timestamp'])
            all_available_stock[prod.id] = stock_list
            
        return {
            'templates': templates, 
            'templates_with_items': templates_with_items, 
            'all_available_stock': all_available_stock,
            'primitive_products': primitive_products
        }

    if request.method == 'POST':
        template_id = request.POST.get('template_id')
        shop_order_number = request.POST.get('shop_order_number')
        batch_from_str = request.POST.get('batch_number_from')
        batch_to_str = request.POST.get('batch_number_to')
        creation_date_str = request.POST.get('creation_date')
        is_continuation = 'is_continuation' in request.POST
        notes = request.POST.get('notes', '')
        product_ids = request.POST.getlist('primitive_product_id')
        theoretical_quantities = request.POST.getlist('theoretical_quantity')
        actual_quantities = request.POST.getlist('actual_quantity')
        source_log_ids = request.POST.getlist('source_log_id')

        if not all([template_id, shop_order_number, batch_from_str, creation_date_str, product_ids]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول وتحميل قالب أولاً.")
            return redirect('inventory:create_batch')

        try:
            creation_date_for_validation = datetime.strptime(creation_date_str, '%Y-%m-%d')
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
            with transaction.atomic():
                final_batch_number_str = batch_from_str
                if batch_to_str and batch_to_str.strip() and int(batch_to_str) >= int(batch_from_str):
                    final_batch_number_str = f"{batch_from_str}-{batch_to_str}"
                
                batch = Batch.objects.create(
                    template_id=template_id,
                    shop_order_number=shop_order_number,
                    batch_number=final_batch_number_str,
                    creation_date=creation_date_for_validation,
                    is_customized=True, # Always customized on creation from this form
                    is_continuation=is_continuation,
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
            
            messages.success(request, f"تم إنشاء أمر التشغيل '{shop_order_number}' بنجاح.")
            return redirect('inventory:view_batch', pk=batch.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
            return redirect('inventory:create_batch')

    page_data = get_page_data()
    json_stock = {pid: [{'id': s['id'], 'qc_no': s['qc_no'], 'timestamp': s['timestamp'].strftime('%Y-%m-%d'), 'remaining_quantity': "%.3f" % s['remaining_quantity']} for s in stock_list] for pid, stock_list in page_data['all_available_stock'].items()}
    primitive_products_for_json = list(page_data['primitive_products'].values('id', 'name', 'unit'))
    
    context = {
        'active_page': 'shop_orders',
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'templates': page_data['templates'],
        'templates_with_items': page_data['templates_with_items'],
        'all_available_stock': json_stock,
        'primitive_products': primitive_products_for_json,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/create_batch_content.html', context)
    return render(request, 'inventory/create_batch.html', context)


def view_batch(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single batch, allowing for edits.
    """
    batch_info = get_object_or_404(Batch.objects.select_related('template__final_product'), pk=pk)
    
    # Logic to parse batch number range
    batch_from, batch_to, num_batches = None, None, 1
    if batch_info.batch_number:
        parts = str(batch_info.batch_number).split('-')
        try:
            batch_from = int(parts[0])
            if len(parts) > 1 and parts[1]:
                batch_to = int(parts[1])
                num_batches = (batch_to - batch_from) + 1
        except (ValueError, IndexError):
            batch_from = batch_info.batch_number
            batch_to = ''
    if num_batches <= 0: num_batches = 1
        
    batch_items_with_stock = []
    # Fetch all items for the batch at once
    batch_items = batch_info.items.select_related('primitive_product').order_by('primitive_product__name')
    
    for item in batch_items:
        item.base_theoretical_quantity = item.theoretical_quantity / num_batches
        item.base_actual_quantity = (item.actual_quantity or 0) / num_batches
        
        # Calculate available stock for this item's product for the dropdown
        product = item.primitive_product
        available_stock_rows = []

        # Opening Balance
        latest_balance = product.opening_balances.order_by('-balance_date').first()
        if latest_balance:
            used_from_ob = BatchItem.objects.filter(primitive_product=product, source_type=BatchItem.SourceType.OPENING_BALANCE).exclude(pk=item.pk).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            remaining_ob_qty = latest_balance.quantity - used_from_ob
            if remaining_ob_qty > 0.001 or item.source_type == BatchItem.SourceType.OPENING_BALANCE:
                available_stock_rows.append({'id': -1, 'qc_no': 'رصيد افتتاحي', 'timestamp': latest_balance.balance_date, 'remaining_quantity': remaining_ob_qty})
        
        # Inventory Logs
        all_logs = product.inventory_logs.all()
        for log in all_logs:
            used_from_log = BatchItem.objects.filter(source_log=log).exclude(pk=item.pk).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
            returned_to_log = log.production_returns.aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
            remaining_log_qty = log.quantity - used_from_log + returned_to_log
            if remaining_log_qty > 0.001 or item.source_log_id == log.id:
                available_stock_rows.append({'id': log.id, 'qc_no': log.qc_no, 'timestamp': log.timestamp, 'remaining_quantity': remaining_log_qty})
        
        item.available_stock = sorted(available_stock_rows, key=lambda x: x['timestamp'])
        batch_items_with_stock.append(item)

    context = {
        'active_page': 'shop_orders',
        'batch': batch_info,
        'items': batch_items_with_stock,
        'primitive_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'batch_from': batch_from,
        'batch_to': batch_to,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/batch_view_content.html', context)
    return render(request, 'inventory/batch_view.html', context)


@require_POST
def delete_batch(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a batch and its associated items.
    """
    batch = get_object_or_404(Batch, pk=pk)
    batch.delete()
    messages.info(request, 'تم حذف أمر التشغيل وجميع بياناته بنجاح.')
    return redirect('inventory:batches')


@require_POST
def add_batch_item(request: HttpRequest, batch_pk: int) -> HttpResponse:
    """
    Adds a new item to an existing batch.
    """
    batch = get_object_or_404(Batch, pk=batch_pk)
    try:
        product_id = request.POST.get('primitive_product_id')
        theoretical_quantity = float(request.POST.get('theoretical_quantity', 0))
        
        if not product_id or theoretical_quantity <= 0:
            messages.warning(request, "الرجاء اختيار منتج وتحديد كمية صالحة.")
            return redirect('inventory:view_batch', pk=batch_pk)
        
        # Create the new item. It will need a source to be assigned later by the user.
        BatchItem.objects.create(
            batch=batch,
            primitive_product_id=product_id,
            theoretical_quantity=theoretical_quantity,
            actual_quantity=theoretical_quantity,
            source_type=BatchItem.SourceType.INVENTORY_LOG, # Default, user must select one
            source_log=None
        )
        check_and_update_batch_customization(batch_pk)
        messages.success(request, "تمت إضافة المادة بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إضافة المادة: {e}")
        
    return redirect('inventory:view_batch', pk=batch_pk)


@require_POST
def update_batch_items_bulk(request: HttpRequest, batch_pk: int) -> HttpResponse:
    """
    Handles the bulk update of a batch's header info and all of its items.
    """
    batch = get_object_or_404(Batch, pk=batch_pk)
    
    shop_order_number = request.POST.get('shop_order_number')
    creation_date_str = request.POST.get('creation_date')
    batch_from_str = request.POST.get('batch_number_from')
    batch_to_str = request.POST.get('batch_number_to')
    is_continuation = 'is_continuation' in request.POST
    notes = request.POST.get('notes', '')

    if not all([shop_order_number, creation_date_str, batch_from_str]):
        messages.error(request, "الرجاء تعبئة بيانات أمر التشغيل الأساسية (رقم الأمر، التاريخ، رقم التشغيلة).")
        return redirect('inventory:view_batch', pk=batch_pk)

    item_ids = request.POST.getlist('item_id')
    if not item_ids:
        messages.info(request, "لا توجد مواد لحفظها.")
        return redirect('inventory:view_batch', pk=batch_pk)

    theoretical_quantities = request.POST.getlist('theoretical_quantity')
    actual_quantities = request.POST.getlist('actual_quantity')
    source_log_ids = request.POST.getlist('source_log_id')
    
    # Get product IDs for stock validation
    product_ids_for_validation = BatchItem.objects.filter(id__in=item_ids).values_list('primitive_product_id', flat=True)

    try:
        creation_date_for_validation = datetime.strptime(creation_date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        messages.error(request, 'تاريخ الإنشاء غير صالح.')
        return redirect('inventory:view_batch', pk=batch_pk)

    is_valid, error_msg = validate_stock_availability(
        product_ids_for_validation, actual_quantities, source_log_ids, creation_date_for_validation, batch_id_to_exclude=batch_pk
    )
    if not is_valid:
        messages.error(request, error_msg)
        return redirect('inventory:view_batch', pk=batch_pk)

    try:
        with transaction.atomic():
            # Update batch header
            final_batch_number_str = batch_from_str
            if batch_to_str and batch_to_str.strip() and int(batch_to_str) >= int(batch_from_str):
                final_batch_number_str = f"{batch_from_str}-{batch_to_str}"
            
            batch.shop_order_number = shop_order_number
            batch.creation_date = creation_date_for_validation
            batch.batch_number = final_batch_number_str
            batch.is_continuation = is_continuation
            batch.notes = notes
            batch.save()
            
            # Update batch items
            for i, item_id in enumerate(item_ids):
                item = BatchItem.objects.get(pk=item_id, batch_id=batch_pk)
                item.theoretical_quantity = float(theoretical_quantities[i])
                item.actual_quantity = float(actual_quantities[i])
                
                source_id_str = source_log_ids[i]
                if source_id_str:
                    source_id_from_form = int(source_id_str)
                    item.source_type = BatchItem.SourceType.OPENING_BALANCE if source_id_from_form == -1 else BatchItem.SourceType.INVENTORY_LOG
                    item.source_log_id = None if source_id_from_form == -1 else source_id_from_form
                item.save()

        check_and_update_batch_customization(batch_pk)
        messages.success(request, "تم حفظ جميع التعديلات بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حفظ التعديلات: {e}")
        
    return redirect('inventory:view_batch', pk=batch_pk)


@require_POST
def delete_batch_item(request: HttpRequest, item_pk: int) -> HttpResponse:
    """
    Deletes a single item from a batch.
    """
    item = get_object_or_404(BatchItem, pk=item_pk)
    batch_id = item.batch.id
    try:
        item.delete()
        check_and_update_batch_customization(batch_id)
        messages.info(request, "تم حذف المادة من أمر التشغيل.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء الحذف: {e}")

    return redirect('inventory:view_batch', pk=batch_id)


# --- Production Returns Views ---

def production_returns(request: HttpRequest) -> HttpResponse:
    """
    Manages production returns. Handles listing returns and adding a new one.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        source_log_id = request.POST.get('source_log_id')
        quantity_str = request.POST.get('quantity')
        return_date_str = request.POST.get('return_date')
        notes = request.POST.get('notes', '')

        if not all([product_id, source_log_id, quantity_str, return_date_str]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول المطلوبة.")
            return redirect('inventory:production_returns')

        try:
            with transaction.atomic():
                quantity = float(quantity_str)
                return_date = datetime.strptime(return_date_str, '%Y-%m-%d')
                
                # Validation
                total_consumed = BatchItem.objects.filter(source_log_id=source_log_id).aggregate(total=Coalesce(Sum('actual_quantity'), 0.0))['total']
                total_returned = ProductionReturn.objects.filter(source_log_id=source_log_id).aggregate(total=Coalesce(Sum('quantity'), 0.0))['total']
                max_returnable = total_consumed - total_returned

                if quantity > max_returnable + 0.001:
                    messages.error(request, f"لا يمكن إرجاع هذه الكمية. الكمية القصوى المسموحة من هذا المصدر هي {max_returnable:.3f}")
                else:
                    ProductionReturn.objects.create(
                        product_id=product_id,
                        source_log_id=source_log_id,
                        quantity=quantity,
                        return_date=return_date,
                        notes=notes
                    )
                    messages.success(request, "تم تسجيل المرتجع بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {e}")
        
        return redirect('inventory:production_returns')

    context = {
        'active_page': 'production_returns',
        'returns': ProductionReturn.objects.select_related('product', 'source_log').all(),
        'products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/production_returns_content.html', context)
    return render(request, 'inventory/production_returns.html', context)


@require_POST
def delete_production_return(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Deletes a production return record.
    """
    pr_return = get_object_or_404(ProductionReturn, pk=pk)
    pr_return.delete()
    messages.info(request, 'تم حذف سجل الإرجاع بنجاح.')
    return redirect('inventory:production_returns')


# --- Opening Balances Views ---

def opening_balances(request: HttpRequest) -> HttpResponse:
    """
    Manages opening balances. Handles listing and creating new entries.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = request.POST.get('quantity')
        balance_date_str = request.POST.get('balance_date')
        
        if not all([product_id, quantity, balance_date_str]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول.")
        else:
            try:
                balance_date = datetime.strptime(balance_date_str, '%Y-%m-%d')
                OpeningBalance.objects.create(
                    product_id=product_id,
                    quantity=quantity,
                    balance_date=balance_date
                )
                messages.success(request, "تم حفظ الرصيد الافتتاحي بنجاح.")
            except Exception as e:
                messages.error(request, f"حدث خطأ: {e}")
        return redirect('inventory:opening_balances')

    context = {
        'active_page': 'opening_balances',
        'balances': OpeningBalance.objects.select_related('product').all(),
        'products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'is_partial_request': 'X-Partial-Request' in request.headers
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/opening_balances_content.html', context)
    return render(request, 'inventory/opening_balances.html', context)


@require_POST
def edit_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edits an existing opening balance record.
    """
    balance = get_object_or_404(OpeningBalance, pk=pk)
    try:
        quantity = request.POST.get('quantity')
        balance_date_str = request.POST.get('balance_date')
        balance.quantity = float(quantity)
        balance.balance_date = datetime.strptime(balance_date_str, '%Y-%m-%d')
        balance.save()
        messages.success(request, "تم تعديل الرصيد بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء التعديل: {e}")
    return redirect('inventory:opening_balances')


@require_POST
def delete_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Deletes an opening balance record.
    """
    balance = get_object_or_404(OpeningBalance, pk=pk)
    balance.delete()
    messages.info(request, "تم حذف الرصيد الافتتاحي بنجاح.")
    return redirect('inventory:opening_balances')


# --- Analysis & Ledger Views ---

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


def ledger(request: HttpRequest) -> HttpResponse:
    """
    Displays the stock card / ledger for products based on filters.
    """
    product_id = request.GET.get('product_id')
    company_id = request.GET.get('company_id')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    all_primitive_products = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))
    all_companies = Company.objects.all()

    context = {
        'active_page': 'ledger',
        'all_primitive_products': all_primitive_products,
        'all_companies': all_companies,
        'is_partial_request': 'X-Partial-Request' in request.headers
    }

    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/ledger_content.html'
    else:
        template_name = 'inventory/ledger.html'

    if not any([product_id, company_id, qc_no, start_date_str, end_date_str]):
        return render(request, template_name, context)
    
    # Date filtering
    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    
    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
        end_date_inclusive = end_date + timedelta(days=1)
    
    transactions = []
    
    # INCOMING from suppliers
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    if product_id: in_logs_qs = in_logs_qs.filter(product_id=product_id)
    if company_id: in_logs_qs = in_logs_qs.filter(company_id=company_id)
    if qc_no: in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})"
        })

    # INCOMING from production returns
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    if product_id: returns_qs = returns_qs.filter(product_id=product_id)
    if qc_no: returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
    if company_id: returns_qs = returns_qs.none() # Cannot filter returns by company
    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})"
        })

    # OUTGOING to production
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
    ).filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)
    if product_id: out_items_qs = out_items_qs.filter(primitive_product_id=product_id)
    if qc_no: out_items_qs = out_items_qs.filter(source_log__qc_no__icontains=qc_no)
    if company_id: out_items_qs = out_items_qs.none() # Cannot filter outgoing by company
    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -item.actual_quantity,
            'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'qc_no': source_desc, 'batch_id': item.batch.id,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})"
        })

    # Sort all transactions chronologically
    transactions.sort(key=lambda x: x['date'])

    opening_balance = 0
    product_unit = ""
    if product_id:
        opening_balance = get_opening_balance_for_period(int(product_id), start_date)
        product_unit = get_object_or_404(Product, pk=product_id).unit
    
    transactions_with_balance = []
    current_balance = opening_balance
    for trx in transactions:
        trx['balance_before'] = current_balance
        current_balance += trx['quantity_change']
        trx['balance_after'] = current_balance
        transactions_with_balance.append(trx)
    
    context.update({
        'transactions': transactions_with_balance,
        'opening_balance_for_period': opening_balance,
        'unit': product_unit,
    })
    return render(request, template_name, context)


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
        
        # Balance over time chart data
        opening_balance = get_opening_balance_for_period(product_id, start_date)
        
        # Combine all transaction types into one list
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

        # Consumption by final product chart data
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

        # Variance chart data
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


# --- API Views ---

def get_used_qc_sources(request: HttpRequest, product_pk: int) -> JsonResponse:
    """
    API endpoint to get inventory sources that have been consumed for a product.
    """
    get_object_or_404(Product, pk=product_pk)
    
    # Get all inventory logs that have been used as a source at least once for this product.
    source_logs = InventoryLog.objects.filter(
        product_id=product_pk,
        batch_items__isnull=False
    ).distinct().annotate(
        total_consumed=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
        total_returned=Coalesce(Sum('production_returns__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        max_returnable=F('total_consumed') - F('total_returned')
    ).filter(max_returnable__gt=0.001)

    result = [
        {
            'id': source.id,
            'qc_no': source.qc_no,
            'timestamp': source.timestamp.isoformat(),
            'max_returnable': source.max_returnable
        } for source in source_logs
    ]
    return JsonResponse(result, safe=False)


def api_batch_details(request: HttpRequest, batch_pk: int) -> JsonResponse:
    """
    API endpoint to get full, detailed information for a single batch.
    """
    batch = get_object_or_404(
        Batch.objects.select_related('template__final_product')
        .prefetch_related('items__primitive_product', 'items__source_log'),
        pk=batch_pk
    )
    
    batch_details = {
        'id': batch.id,
        'shop_order_number': batch.shop_order_number,
        'batch_number': batch.batch_number,
        'creation_date': batch.creation_date.isoformat(),
        'is_customized': batch.is_customized,
        'is_continuation': batch.is_continuation,
        'notes': batch.notes,
        'template_name': batch.template.name,
        'final_product_name': batch.template.final_product.name,
        'final_product_code': batch.template.final_product.code,
        'item_list': [
            {
                'id': item.id,
                'primitive_product_name': item.primitive_product.name,
                'primitive_product_code': item.primitive_product.code,
                'primitive_product_unit': item.primitive_product.unit,
                'theoretical_quantity': item.theoretical_quantity,
                'actual_quantity': item.actual_quantity,
                'source_qc_no': 'رصيد افتتاحي' if item.source_type == 'opening_balance' else (item.source_log.qc_no if item.source_log else 'N/A')
            } for item in batch.items.all()
        ]
    }
    return JsonResponse(batch_details)

def print_ledger(request: HttpRequest) -> HttpResponse:
    """
    Gathers all ledger data based on filters and renders a dedicated, print-friendly template.
    This view now contains the full logic, not a placeholder.
    """
    product_id_str = request.GET.get('product_id')
    company_id_str = request.GET.get('company_id')
    qc_no = request.GET.get('qc_no', '').strip()
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')

    # Date filtering setup
    start_date = datetime.min.replace(tzinfo=timezone.get_current_timezone())
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
    
    end_date_inclusive = datetime.max.replace(tzinfo=timezone.get_current_timezone())
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=timezone.get_current_timezone())
        end_date_inclusive = end_date + timedelta(days=1)

    # --- Re-run the exact same query logic as the main ledger page ---
    transactions = []
    
    # INCOMING from suppliers
    in_logs_qs = InventoryLog.objects.select_related('product', 'company').filter(timestamp__gte=start_date, timestamp__lt=end_date_inclusive)
    if product_id_str: in_logs_qs = in_logs_qs.filter(product_id=product_id_str)
    if company_id_str: in_logs_qs = in_logs_qs.filter(company_id=company_id_str)
    if qc_no: in_logs_qs = in_logs_qs.filter(qc_no__icontains=qc_no)
    for log in in_logs_qs:
        transactions.append({
            'date': log.timestamp, 'type': 'IN', 'quantity_change': log.quantity,
            'product_name': log.product.name, 'product_code': log.product.code, 'unit': log.product.unit,
            'company_name': log.company.name if log.company else '---', 'qc_no': log.qc_no, 'batch_id': None,
            'description': f"استلام من {log.company.name if log.company else '---'} (QC: {log.qc_no or 'N/A'})"
        })

    # INCOMING from production returns
    returns_qs = ProductionReturn.objects.select_related('product', 'source_log').filter(return_date__gte=start_date, return_date__lt=end_date_inclusive)
    if product_id_str: returns_qs = returns_qs.filter(product_id=product_id_str)
    if qc_no: returns_qs = returns_qs.filter(source_log__qc_no__icontains=qc_no)
    if company_id_str: returns_qs = returns_qs.none()
    for ret in returns_qs:
        transactions.append({
            'date': ret.return_date, 'type': 'RETURN_IN', 'quantity_change': ret.quantity,
            'product_name': ret.product.name, 'product_code': ret.product.code, 'unit': ret.product.unit,
            'company_name': 'إرجاع من الإنتاج', 'qc_no': ret.source_log.qc_no, 'batch_id': None,
            'description': f"إرجاع من الإنتاج (مصدر QC الأصلي: {ret.source_log.qc_no or 'N/A'})"
        })

    # OUTGOING to production
    out_items_qs = BatchItem.objects.select_related(
        'primitive_product', 'batch', 'source_log', 'batch__template__final_product'
    ).filter(batch__creation_date__gte=start_date, batch__creation_date__lt=end_date_inclusive)
    if product_id_str: out_items_qs = out_items_qs.filter(primitive_product_id=product_id_str)
    if qc_no: out_items_qs = out_items_qs.filter(Q(source_log__qc_no__icontains=qc_no) | Q(source_type=BatchItem.SourceType.OPENING_BALANCE, source_log__isnull=True))
    if company_id_str: out_items_qs = out_items_qs.none()
    for item in out_items_qs:
        source_desc = item.source_log.qc_no or 'N/A' if item.source_log else 'رصيد افتتاحي'
        continuation_str = ' (تكملة)' if item.batch.is_continuation else ''
        transactions.append({
            'date': item.batch.creation_date, 'type': 'OUT', 'quantity_change': -item.actual_quantity,
            'product_name': item.primitive_product.name, 'product_code': item.primitive_product.code, 'unit': item.primitive_product.unit,
            'company_name': None, 'qc_no': source_desc, 'batch_id': item.batch.id,
            'shop_order_number': item.batch.shop_order_number, 'batch_number': item.batch.batch_number,
            'final_product_name': item.batch.template.final_product.name, 'theoretical_quantity': item.theoretical_quantity,
            'description': f"صرف لأمر تشغيل {item.batch.shop_order_number}{continuation_str} (مصدر: {source_desc})"
        })

    transactions.sort(key=lambda x: x['date'])
    
    # Calculate running balances
    opening_balance_for_period = 0
    if product_id_str:
        opening_balance_for_period = get_opening_balance_for_period(int(product_id_str), start_date)

    transactions_with_balance = []
    current_balance = opening_balance_for_period
    for row in transactions:
        row['balance_before'] = current_balance
        current_balance += row['quantity_change']
        row['balance_after'] = current_balance
        transactions_with_balance.append(row)
    
    closing_balance = current_balance

    # Get extra data for the report header
    report_title = "كشف حساب المخزون العام"
    product_details = None
    if product_id_str:
        product_details = get_object_or_404(Product, pk=product_id_str)
        report_title = f"كشف حساب مخزون - {product_details.name}"

    # For each 'OUT' transaction, pre-fetch the full batch details
    batch_details_map = {}
    batch_ids_to_fetch = {trx['batch_id'] for trx in transactions if trx['type'] == 'OUT' and trx['batch_id']}
    if batch_ids_to_fetch:
        batches_from_db = Batch.objects.filter(id__in=batch_ids_to_fetch).select_related(
            'template__final_product'
        ).prefetch_related(
            'items__primitive_product', 'items__source_log'
        )
        for batch in batches_from_db:
            batch_details_map[batch.id] = {
                'info': batch,
                'item_list': batch.items.all()
            }

    context = {
        'transactions': transactions_with_balance,
        'batch_details_map': batch_details_map,
        'report_title': report_title,
        'product_details': product_details,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'print_date': timezone.now(),
        'opening_balance_for_period': opening_balance_for_period,
        'closing_balance': closing_balance,
    }
    
    return render(request, 'inventory/print_ledger.html', context)