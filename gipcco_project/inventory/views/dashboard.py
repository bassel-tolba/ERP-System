from datetime import datetime

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Company, InventoryLog, Product, ProductTag


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
                # Create the log entry
                log_entry = InventoryLog.objects.create(
                    product_id=product_id,
                    company_id=company_id,
                    quantity=quantity,
                    timestamp=entry_datetime,
                    qc_no=qc_no
                )
                
                # Handle tags
                tag_ids = request.POST.getlist('tags')
                if tag_ids:
                    log_entry.tags.set(tag_ids)
                    messages.success(request, 'تم تسجيل الإدخال وإضافة الوسوم بنجاح.')
                else:
                    messages.success(request, 'تم تسجيل حركة المخزون بنجاح.')
            except (ValueError, TypeError):
                messages.error(request, 'صيغة التاريخ غير صالحة.')
        return redirect('inventory:index')

    context = {
        'active_page': 'index',
        'logs': InventoryLog.objects.select_related('product', 'company').all()[:15],
        'all_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'all_companies': Company.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'all_tags': ProductTag.objects.all(),  # Add all tags to context
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
            
            # Handle tags
            tag_ids = request.POST.getlist('tags')
            if tag_ids:
                log_entry.tags.set(tag_ids)
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