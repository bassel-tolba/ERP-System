# gipcco_project/inventory/views/dashboard.py

import json
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q, Sum, ProtectedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import Company, InventoryLog, Product, ProductTag, PurchaseOrder, PurchaseOrderItem, Employee
from ..services.costing_service import recalculate_cost_history_for_product
from ..services import purchasing_service




def index(request: HttpRequest) -> HttpResponse:
    """
    Handles the dashboard page. Displays recent inventory logs and a form to add new ones.
    New logs are now created with a 'QUARANTINED' status by default.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        company_id = request.POST.get('company_id')
        quantity_str = request.POST.get('quantity')
        date_str = request.POST.get('entry_date')
        po_item_id = request.POST.get('po_item_id')
        employee_id = request.POST.get('employee_id') # NEW
        is_final_receipt = request.POST.get('is_final_receipt') == 'true'
        excess_is_free = request.POST.get('excess_is_free') == 'true'

        # --- MODIFIED: Get new accounting fields ---
        base_unit_price_str = request.POST.get('base_unit_price')
        vat_amount_str = request.POST.get('vat_amount')
        vat_treatment = request.POST.get('vat_treatment', InventoryLog.VatTreatment.RECOVERABLE)
        withholding_tax_amount_str = request.POST.get('withholding_tax_amount')


        if not all([product_id, company_id, quantity_str, date_str]):
            messages.warning(request, 'الرجاء تعبئة جميع الحقول المطلوبة.')
            return redirect('inventory:index')
        
        try:
            entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            entry_datetime = timezone.make_aware(datetime.combine(entry_date, timezone.now().time()))
            quantity = float(quantity_str)
            
            # --- MODIFIED: Logic to determine price and VAT ---
            if po_item_id:
                po_item = PurchaseOrderItem.objects.get(pk=po_item_id)
                # Over-delivery and the excess is free: recalculate unit price
                if quantity > po_item.quantity_ordered and excess_is_free:
                    original_total_value = po_item.base_price_per_unit * Decimal(str(po_item.quantity_ordered))
                    base_unit_price = original_total_value / Decimal(str(quantity))
                else:
                    base_unit_price = po_item.base_price_per_unit

                vat_rate = po_item.vat_rate
                wht_rate = po_item.withholding_tax_rate
                vat_amount = base_unit_price * Decimal(str(quantity)) * vat_rate
                withholding_tax_amount = base_unit_price * Decimal(str(quantity)) * wht_rate
            else:
                base_unit_price = Decimal(base_unit_price_str) if base_unit_price_str else Decimal('0.0')
                vat_amount = Decimal(vat_amount_str) if vat_amount_str else Decimal('0.0')
                withholding_tax_amount = Decimal(withholding_tax_amount_str) if withholding_tax_amount_str else Decimal('0.0')

            log_entry = InventoryLog.objects.create(
                product_id=product_id,
                company_id=company_id,
                quantity=quantity,
                timestamp=entry_datetime,
                po_item_id=po_item_id if po_item_id else None,
                employee_id=employee_id if employee_id else None, # NEW
                # --- MODIFIED: Save new accounting fields ---
                base_unit_price=base_unit_price,
                vat_amount=vat_amount,
                vat_treatment=vat_treatment,
                withholding_tax_amount=withholding_tax_amount
            )
            
            tag_ids = request.POST.getlist('tags')
            if tag_ids:
                log_entry.tags.set(tag_ids)
            
            if po_item_id:
                purchasing_service.update_po_status_after_receipt(
                    inventory_log_id=log_entry.id, 
                    is_final_receipt=is_final_receipt,
                    old_po_item_id=None
                )
            
            messages.success(request, 'تم تسجيل الاستلام المبدئي بنجاح. السجل الآن تحت الفحص.')
        except (ValueError, TypeError, PurchaseOrderItem.DoesNotExist) as e:
            messages.error(request, f'بيانات غير صالحة أو لم يتم العثور على أمر الشراء. خطأ: {e}')
        
        return redirect('inventory:index')

    prefill_data_json = None
    po_item_id_to_prefill = request.GET.get('po_item_id')
    if po_item_id_to_prefill:
        try:
            po_item = PurchaseOrderItem.objects.select_related('purchase_order').get(pk=po_item_id_to_prefill)
            prefill_data = {
                'supplier_id': po_item.purchase_order.supplier_id,
                'po_id': po_item.purchase_order_id,
                'po_item_id': po_item.id
            }
            prefill_data_json = json.dumps(prefill_data)
        except PurchaseOrderItem.DoesNotExist:
            messages.error(request, "رقم بند أمر الشراء المحدد غير صالح.")


    context = {
        'active_page': 'index',
        'logs': InventoryLog.objects.select_related('product', 'company').all()[:15],
        'all_products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'all_companies': Company.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'all_tags': ProductTag.objects.all(),
        'prefill_data_json': prefill_data_json,
        'vat_treatment_choices': InventoryLog.VatTreatment.choices,
        'employees': Employee.objects.filter(is_active=True), # NEW
    }
    
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/dashboard_content.html', context)
    return render(request, 'inventory/dashboard.html', context)


def records(request: HttpRequest) -> HttpResponse:
    """
    Displays a full list of all inventory log records, with status filtering.
    """
    status_filter = request.GET.get('status', 'all')
    
    logs_qs = InventoryLog.objects.select_related('product', 'company', 'po_item__purchase_order__supplier').all()
    
    if status_filter in [s.value for s in InventoryLog.Status]:
        logs_qs = logs_qs.filter(status=status_filter)

    context = {
        'active_page': 'records',
        'logs': logs_qs,
        'all_products': Product.objects.all(),
        'all_companies': Company.objects.all(),
        'status_filter': status_filter,
        'vat_treatment_choices': InventoryLog.VatTreatment.choices,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/records_content.html', context)
    return render(request, 'inventory/records.html', context)


def quarantine_list(request: HttpRequest) -> HttpResponse:
    """
    Displays a list of all inventory items currently in quarantine, awaiting release.
    """
    quarantined_items = InventoryLog.objects.select_related(
        'product', 'company', 'po_item__purchase_order'
    ).filter(status=InventoryLog.Status.QUARANTINED).order_by('timestamp')

    context = {
        'active_page': 'quarantine',
        'logs': quarantined_items,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/quarantine_content.html', context)
    return render(request, 'inventory/quarantine.html', context)


@require_POST
def release_from_quarantine(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Releases an inventory item from quarantine, setting its QC number and release date.
    Triggers the costing engine.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk, status=InventoryLog.Status.QUARANTINED)
    
    qc_no = request.POST.get('qc_no')
    release_date_str = request.POST.get('release_date')

    if not qc_no or not release_date_str:
        messages.warning(request, "الرجاء تعبئة رقم الفحص وتاريخ الإفراج.")
        return redirect('inventory:quarantine_list')

    try:
        release_date = datetime.strptime(release_date_str, '%Y-%m-%d').date()
        release_datetime = timezone.make_aware(datetime.combine(release_date, timezone.now().time()))

        if release_datetime < log_entry.timestamp:
            messages.error(request, "تاريخ الإفراج لا يمكن أن يكون أقدم من تاريخ الاستلام الأصلي.")
            return redirect('inventory:quarantine_list')

        log_entry.status = InventoryLog.Status.RELEASED
        log_entry.qc_no = qc_no
        log_entry.release_timestamp = release_datetime
        log_entry.save(update_fields=['status', 'qc_no', 'release_timestamp'])

        recalculate_cost_history_for_product(log_entry.product_id, release_datetime)

        messages.success(request, f"تم الإفراج عن البند (QC: {qc_no}) بنجاح وتحديث التكاليف.")

    except (ValueError, TypeError) as e:
        messages.error(request, f"حدث خطأ في البيانات: {e}")

    return redirect('inventory:quarantine_list')


@require_POST
def edit_record(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing inventory log record, including linking to a PO,
    and triggers cost recalculation.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    original_timestamp = log_entry.timestamp
    original_product_id = log_entry.product_id
    original_po_item = log_entry.po_item

    product_id = request.POST.get('product_id')
    company_id = request.POST.get('company_id')
    quantity_str = request.POST.get('quantity')
    date_str = request.POST.get('entry_date')
    po_item_id = request.POST.get('po_item_id')
    employee_id = request.POST.get('employee_id') # NEW
    
    # --- MODIFIED: Get new accounting fields ---
    base_unit_price_str = request.POST.get('base_unit_price')
    vat_amount_str = request.POST.get('vat_amount')
    vat_treatment = request.POST.get('vat_treatment')
    withholding_tax_amount_str = request.POST.get('withholding_tax_amount')

    if not all([product_id, company_id, quantity_str, date_str]):
        messages.warning(request, 'الرجاء تعبئة جميع الحقول.')
        return redirect('inventory:records')

    try:
        new_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        original_time = log_entry.timestamp.time() if log_entry.timestamp else timezone.now().time()
        new_datetime = timezone.make_aware(datetime.combine(new_date, original_time))
        
        quantity = float(quantity_str)
        new_po_item = None
        
        # --- MODIFIED: Logic to update price and VAT ---
        if po_item_id:
            new_po_item = get_object_or_404(PurchaseOrderItem, pk=po_item_id)
            base_unit_price = new_po_item.base_price_per_unit
            vat_amount = (new_po_item.base_price_per_unit * Decimal(str(quantity)) * new_po_item.vat_rate).quantize(Decimal('0.001'))
            withholding_tax_amount = (new_po_item.base_price_per_unit * Decimal(str(quantity)) * new_po_item.withholding_tax_rate).quantize(Decimal('0.001'))
        else:
            if not base_unit_price_str or not vat_amount_str:
                messages.warning(request, 'الرجاء تعبئة سعر الوحدة ومبلغ الضريبة عند عدم الربط بأمر شراء.')
                return redirect('inventory:records')
            base_unit_price = Decimal(base_unit_price_str)
            vat_amount = Decimal(vat_amount_str)
            withholding_tax_amount = Decimal(withholding_tax_amount_str) if withholding_tax_amount_str else Decimal('0.000')

        log_entry.product_id = product_id
        log_entry.company_id = company_id
        log_entry.quantity = quantity
        log_entry.timestamp = new_datetime
        log_entry.po_item = new_po_item
        log_entry.employee_id = employee_id if employee_id else None # NEW
        log_entry.base_unit_price = base_unit_price
        log_entry.vat_amount = vat_amount
        log_entry.vat_treatment = vat_treatment
        log_entry.withholding_tax_amount = withholding_tax_amount
        log_entry.save()
        
        tag_ids = request.POST.getlist('tags')
        log_entry.tags.set(tag_ids)

        if original_po_item != new_po_item:
            if original_po_item:
                purchasing_service.update_po_status_after_receipt(None, is_final_receipt=False, old_po_item_id=original_po_item.id)
            if new_po_item:
                purchasing_service.update_po_status_after_receipt(log_entry.id, is_final_receipt=False)
        elif new_po_item:
            purchasing_service.update_po_status_after_receipt(log_entry.id, is_final_receipt=False)

        if log_entry.status == InventoryLog.Status.RELEASED:
            start_recalc_time = min(original_timestamp, new_datetime, log_entry.release_timestamp)
            recalculate_cost_history_for_product(int(product_id), start_recalc_time)
            if original_product_id != int(product_id):
                 recalculate_cost_history_for_product(original_product_id, start_recalc_time)
            messages.success(request, "تم تعديل السجل بنجاح. تم تحديث تكاليف المخزون.")
        else:
            messages.success(request, "تم تعديل السجل تحت الفحص بنجاح.")

    except (ValueError, TypeError, PurchaseOrderItem.DoesNotExist) as e:
        messages.error(request, f"حدث خطأ: {e}")
        
    return redirect('inventory:records')


@require_POST
def delete_record(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting an inventory log record and triggers cost recalculation if it was released.
    """
    log_entry = get_object_or_404(InventoryLog, pk=pk)
    timestamp_for_recalc = log_entry.release_timestamp or log_entry.timestamp
    product_id_for_recalc = log_entry.product_id
    po_item = log_entry.po_item
    was_released = log_entry.status == InventoryLog.Status.RELEASED

    try:
        log_entry.delete()
        
        if was_released:
            recalculate_cost_history_for_product(product_id_for_recalc, timestamp_for_recalc)
            messages.info(request, 'تم حذف السجل بنجاح. تم تحديث تكاليف المخزون.')
        else:
            messages.info(request, 'تم حذف السجل من قائمة الفحص بنجاح.')

        if po_item:
            purchasing_service.update_po_status_after_receipt(inventory_log_id=None, is_final_receipt=False, old_po_item_id=po_item.id)
            
    except ProtectedError:
        messages.error(request, 'لا يمكن حذف هذا السجل لأنه تم استخدامه في أمر تشغيل. قم بحذف أمر التشغيل أولاً.')
            
    return redirect('inventory:records')