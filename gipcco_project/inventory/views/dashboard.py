# gipcco_project/inventory/views/dashboard.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum
from django.db.models import ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Company, InventoryLog, Product, ProductTag, PurchaseOrder, PurchaseOrderItem
# --- NEW: Import costing helpers ---
from .helpers import update_moving_average_cost, recalculate_cost_history_for_product


def update_po_status(po_id: int):
    """Helper to update a PO's status after a receipt."""
    try:
        po = PurchaseOrder.objects.prefetch_related('items__receipts').get(pk=po_id)
        total_ordered = sum(item.quantity_ordered for item in po.items.all())
        total_received = sum(
            receipt.quantity 
            for item in po.items.all() 
            for receipt in item.receipts.all()
        )
        
        if abs(total_received - total_ordered) < 0.001:
            po.status = PurchaseOrder.Status.COMPLETED
        elif total_received > 0:
            po.status = PurchaseOrder.Status.PARTIALLY_RECEIVED
        else:
            po.status = PurchaseOrder.Status.PENDING
        po.save(update_fields=['status'])
    except PurchaseOrder.DoesNotExist:
        pass


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
        unit_price_str = request.POST.get('unit_price') # New
        po_item_id = request.POST.get('po_item_id') # New

        if not all([product_id, company_id, quantity, date_str, unit_price_str]):
            messages.warning(request, 'الرجاء تعبئة جميع الحقول (بما في ذلك سعر الوحدة).')
        else:
            try:
                entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                entry_datetime = timezone.make_aware(datetime.combine(entry_date, timezone.now().time()))
                
                log_entry = InventoryLog.objects.create(
                    product_id=product_id,
                    company_id=company_id,
                    quantity=float(quantity),
                    timestamp=entry_datetime,
                    qc_no=qc_no,
                    unit_price=Decimal(unit_price_str),
                    po_item_id=po_item_id if po_item_id else None
                )
                
                tag_ids = request.POST.getlist('tags')
                if tag_ids:
                    log_entry.tags.set(tag_ids)
                
                # --- COSTING ENGINE TRIGGER ---
                if entry_date < timezone.now().date():
                    recalculate_cost_history_for_product(int(product_id), entry_datetime)
                else:
                    update_moving_average_cost(int(product_id), log_entry)
                
                # Update PO status if applicable
                if po_item_id:
                    po_item = PurchaseOrderItem.objects.get(pk=po_item_id)
                    update_po_status(po_item.purchase_order_id)
                
                messages.success(request, 'تم تسجيل حركة المخزون بنجاح.')
            except (ValueError, TypeError) as e:
                messages.error(request, f'بيانات غير صالحة. خطأ: {e}')
        return redirect('inventory:index')

    context = {
        'active_page': 'index',
        'logs': InventoryLog.objects.select_related('product', 'company').all()[:15],
        'all_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'all_companies': Company.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'all_tags': ProductTag.objects.all(),
    }
    
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/dashboard_content.html', context)
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
    Handles editing an existing inventory log record and triggers cost recalculation.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    original_timestamp = log_entry.timestamp
    original_product_id = log_entry.product_id

    product_id = request.POST.get('product_id')
    company_id = request.POST.get('company_id')
    quantity = request.POST.get('quantity')
    date_str = request.POST.get('entry_date')
    qc_no = request.POST.get('qc_no')
    # Price is not editable to maintain financial integrity

    if not all([product_id, company_id, quantity, date_str]):
        messages.warning(request, 'الرجاء تعبئة جميع الحقول.')
    else:
        try:
            new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            new_datetime = timezone.make_aware(datetime.combine(new_date, original_timestamp.time()))
            
            log_entry.product_id = product_id
            log_entry.company_id = company_id
            log_entry.quantity = quantity
            log_entry.timestamp = new_datetime
            log_entry.qc_no = qc_no
            log_entry.save()
            
            tag_ids = request.POST.getlist('tags')
            log_entry.tags.set(tag_ids)

            # --- COSTING ENGINE TRIGGER ---
            start_recalc_time = min(original_timestamp, new_datetime)
            recalculate_cost_history_for_product(int(product_id), start_recalc_time)
            # If product was changed, recalc the old one too
            if original_product_id != int(product_id):
                 recalculate_cost_history_for_product(original_product_id, start_recalc_time)

            messages.success(request, "تم تعديل السجل بنجاح. تم تحديث تكاليف المخزون.")
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            
    return redirect('inventory:records')

@require_POST
def delete_record(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting an inventory log record and triggers cost recalculation.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    timestamp_for_recalc = log_entry.timestamp
    product_id_for_recalc = log_entry.product_id
    po_item = log_entry.po_item

    try:
        log_entry.delete()
        # --- COSTING ENGINE TRIGGER ---
        recalculate_cost_history_for_product(product_id_for_recalc, timestamp_for_recalc)

        # Update PO status if it was linked to one
        if po_item:
            update_po_status(po_item.purchase_order_id)
            
        messages.info(request, 'تم حذف السجل بنجاح. تم تحديث تكاليف المخزون.')
    except ProtectedError:
        messages.error(request, 'لا يمكن حذف هذا السجل لأنه تم استخدامه في أمر تشغيل. قم بحذف أمر التشغيل أولاً.')
            
    return redirect('inventory:records')