# gipcco_project/inventory/views/api.py

from decimal import Decimal
import logging

from django.shortcuts import get_object_or_404
from django.http import HttpRequest, JsonResponse
from django.contrib.contenttypes.models import ContentType
from django.db.models import F, Q, Sum, Subquery, OuterRef, FloatField, Value, DecimalField
from django.db.models.functions import Coalesce

from ..models import (
    Product, ProductTag, PurchaseOrder, PurchaseOrderItem, InventoryLog, Batch,
    FinishedProductReceipt, SalesOrderItem, FinishedProductDispatch, SalesOrder,
    InventoryAdjustment, Employee, ExpenseLog, BatchItem, InventoryConsumption,
    ProductionReturn, EmployeeAdvanceSettlement, JournalEntry, LandedCostInvoice
)


# --- API Views ---

def get_used_qc_sources(request: HttpRequest, product_pk: int) -> JsonResponse:
    """
    API endpoint to get inventory sources that have been consumed for a product.
    """
    get_object_or_404(Product, pk=product_pk)
    
    source_logs = Product.objects.get(pk=product_pk).inventory_logs.filter(
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
                # 'source_qc_no': item.source_log.qc_no if item.source_log else 'N/A'
            } for item in batch.items.all()
        ]
    }
    return JsonResponse(batch_details)

# --- NEW: BATCH ANALYSIS API ---
def api_get_full_batch_analysis(request: HttpRequest, batch_pk: int) -> JsonResponse:
    """
    API endpoint that returns a comprehensive analysis of a single production batch,
    including raw material costs, finished product receipts, and calculated costs.
    """
    batch = get_object_or_404(
        Batch.objects.select_related('template__final_product').prefetch_related(
            'items__primitive_product', 'receipts'
        ), pk=batch_pk
    )

    total_actual_cost = sum(
        Decimal(str(item.actual_quantity or 0.0)) * (item.cost_at_consumption or Decimal('0.0'))
        for item in batch.items.all()
    )

    total_quantity_produced = sum(r.total_quantity_produced for r in batch.receipts.all())

    analysis_data = {
        'id': batch.id,
        'shop_order_number': batch.shop_order_number,
        'batch_number': batch.batch_number,
        'creation_date': batch.creation_date.isoformat(),
        'final_product_name': batch.template.final_product.name,
        'final_product_unit': batch.template.final_product.unit,
        'notes': batch.notes,

        'summary': {
            'total_raw_material_cost': total_actual_cost,
            'total_quantity_produced': total_quantity_produced,
            'average_cost_per_unit': (total_actual_cost / Decimal(str(total_quantity_produced))) if total_quantity_produced > 0 else Decimal('0.0'),
        },

        'raw_materials_used': [
            {
                'product_name': item.primitive_product.name,
                'unit': item.primitive_product.unit,
                'theoretical_quantity': item.theoretical_quantity,
                'actual_quantity': item.actual_quantity,
                'cost_at_consumption': item.cost_at_consumption,
                'line_total': (item.cost_at_consumption or Decimal('0.0')) * Decimal(str(item.actual_quantity or 0.0)),
            } for item in batch.items.all()
        ],

        'finished_product_receipts': [
            {
                'receipt_id': receipt.id,
                'receipt_date': receipt.receipt_date.isoformat(),
                'quantity_produced': receipt.total_quantity_produced,
                'market_type': receipt.get_market_type_display(),
                'proportional_cost': receipt.total_cost,
                'cost_per_unit': (receipt.total_cost / Decimal(str(receipt.total_quantity_produced))) if receipt.total_quantity_produced > 0 else Decimal('0.0'),
                'status': receipt.get_status_display(),
            } for receipt in batch.receipts.all()
        ]
    }
    return JsonResponse(analysis_data)


def get_product_tags(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    API endpoint to get all tags associated with a product.
    If a product has specific tags, only those are returned.
    Otherwise, all tags are returned as a fallback.
    """
    product = get_object_or_404(Product, id=product_id)
    tags = product.tags.all()
    if not tags.exists():
        tags = ProductTag.objects.all()
    return JsonResponse({
        'tags': [{'id': tag.id, 'name': tag.name} for tag in tags]
    })

# --- NEW API VIEWS FOR POs ---

def api_get_open_pos_for_supplier(request: HttpRequest, supplier_id: int) -> JsonResponse:
    """
    API endpoint to get open Purchase Orders for a specific supplier.
    """
    open_pos = PurchaseOrder.objects.filter(
        supplier_id=supplier_id,
        status__in=[PurchaseOrder.Status.PENDING, PurchaseOrder.Status.PARTIALLY_RECEIVED]
    ).order_by('-order_date')
    
    data = [
        {'id': po.id, 'po_number': po.po_number, 'order_date': po.order_date}
        for po in open_pos
    ]
    return JsonResponse(data, safe=False)


def api_get_po_items(request: HttpRequest, po_id: int) -> JsonResponse:
    """
    API endpoint to get items for a specific Purchase Order, calculating remaining quantity.
    """
    po_items = PurchaseOrderItem.objects.filter(
        purchase_order_id=po_id
    ).select_related('product').prefetch_related('receipts').annotate(
        total_received=Coalesce(Sum('receipts__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        quantity_remaining=F('quantity_ordered') - F('total_received')
    ).filter(quantity_remaining__gt=0.001)

    data = [
        {
            'id': item.id,
            'product_id': item.product.id,
            'product_name': f"{item.product.name} ({item.product.code})",
            'quantity_remaining': item.quantity_remaining,
            'base_price_per_unit': item.base_price_per_unit,
            'vat_rate': item.vat_rate,
            'withholding_tax_rate': item.withholding_tax_rate
        } for item in po_items
    ]
    return JsonResponse(data, safe=False)


def api_get_sellable_stock(request: HttpRequest) -> JsonResponse:
    """API endpoint to get released, in-stock finished product batches."""
    
    # Subquery for total dispatched. This calculates the sum for each receipt in isolation.
    dispatched_subquery = FinishedProductDispatch.objects.filter(
        sales_order_item__finished_product_id=OuterRef('pk')
    ).values(
        'sales_order_item__finished_product_id'  # Group by receipt
    ).annotate(
        total=Sum('quantity')
    ).values('total')

    # Subquery for total adjusted. This also calculates the sum in isolation.
    adjusted_subquery = InventoryAdjustment.objects.filter(
        source_finished_product_id=OuterRef('pk')
    ).values(
        'source_finished_product_id'  # Group by receipt
    ).annotate(
        total=Sum('adjustment_quantity')
    ).values('total')

    # Main query to get sellable stock
    sellable_stock = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).annotate(
        total_dispatched=Coalesce(Subquery(dispatched_subquery), 0.0, output_field=DecimalField()),
        total_adjusted=Coalesce(Subquery(adjusted_subquery), 0.0, output_field=DecimalField())
    ).annotate(
        available_quantity=F('total_quantity_produced') - F('total_dispatched') - F('total_adjusted')
    ).filter(
        available_quantity__gt=0.001
    ).select_related('batch__template__final_product', 'batch')

    result = [
        {
            'id': stock.id,
            'product_name': stock.batch.template.final_product.name,
            'product_code': stock.batch.template.final_product.code,
            'batch_number': stock.batch.batch_number,
            'available_quantity': stock.available_quantity,
            'unit': stock.batch.template.final_product.unit,
            'unit_cost': stock.unit_cost
        } for stock in sellable_stock
    ]
    
    return JsonResponse(result, safe=False)


def api_get_unallocated_landed_cost_invoices(request):
    """
    API endpoint to get all 'Awaiting Allocation' landed cost invoices.
    """
    invoices = LandedCostInvoice.objects.filter(
        status=LandedCostInvoice.Status.AWAITING_ALLOCATION
    ).select_related('vendor').order_by('-invoice_date')

    data = [
        {
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'vendor_name': inv.vendor.name,
            'invoice_date': inv.invoice_date.strftime('%Y-%m-%d'),
            'total_amount': str(inv.total_amount.quantize(Decimal('0.001'))),
        } for inv in invoices
    ]
    return JsonResponse({'invoices': data})


def api_get_receipts_for_allocation(request):
    """
    API endpoint to get all 'Released' inventory receipts that are candidates
    for landed cost allocation.
    """
    # We only want to show receipts that haven't had any third-party costs allocated yet.
    # This prevents cluttering the UI with already-processed receipts.
    receipts = InventoryLog.objects.filter(
        status=InventoryLog.Status.RELEASED,
        landed_cost_allocations__isnull=True 
    ).select_related('product', 'company').order_by('-release_timestamp')

    data = [
        {
            'id': r.id,
            'release_timestamp': r.release_timestamp.strftime('%Y-%m-%d %H:%M'),
            'qc_no': r.qc_no,
            'product_name': r.product.name,
            'supplier_name': r.company.name if r.company else 'N/A',
            'quantity': r.quantity,
            'unit': r.product.unit,
            'total_value': str((r.costing_unit_price * Decimal(str(r.quantity))).quantize(Decimal('0.001')))
        } for r in receipts
    ]
    return JsonResponse({'receipts': data})

    # The main query now uses the subqueries, preventing the join multiplication bug.
    sellable_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).select_related(
        'batch__template__final_product'
    ).annotate(
        total_dispatched=Coalesce(Subquery(dispatched_subquery, output_field=FloatField()), 0.0),
        total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
    ).annotate(
        quantity_available=F('total_quantity_produced') - F('total_dispatched') + F('total_adjusted')
    ).filter(
        quantity_available__gt=0.001
    )

    data = [
        {
            'id': receipt.id,
            'product_name': receipt.batch.template.final_product.name,
            'batch_number': receipt.individual_batch_number,
            'available_qty': receipt.quantity_available,
            'unit': receipt.batch.template.final_product.unit
        } for receipt in sellable_receipts
    ]
    return JsonResponse(data, safe=False)


# --- CORRECTED API ENDPOINT ---
def api_get_available_stock(request: HttpRequest, product_pk: int) -> JsonResponse:
    """
    API endpoint to get all available, released stock logs for a given product.
    Used for the internal consumption form. Now uses subqueries for accuracy.
    """
    product = get_object_or_404(Product, pk=product_pk)
    
    # --- ROBUST SUBQUERY APPROACH FOR RAW MATERIALS ---
    consumed_prod_subquery = BatchItem.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('actual_quantity')).values('total')
    consumed_internal_subquery = InventoryConsumption.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity_consumed')).values('total')
    returned_subquery = ProductionReturn.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity')).values('total')
    adjusted_subquery = InventoryAdjustment.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('adjustment_quantity')).values('total')

    # Find all released logs for this product and calculate remaining quantity accurately
    released_logs = InventoryLog.objects.filter(
        product=product,
        status=InventoryLog.Status.RELEASED
    ).annotate(
        total_used_in_prod=Coalesce(Subquery(consumed_prod_subquery, output_field=FloatField()), 0.0),
        total_used_in_consumption=Coalesce(Subquery(consumed_internal_subquery, output_field=FloatField()), 0.0),
        total_returned=Coalesce(Subquery(returned_subquery, output_field=FloatField()), 0.0),
        total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
    ).annotate(
        remaining_quantity=F('quantity') - F('total_used_in_prod') - F('total_used_in_consumption') + F('total_returned') + F('total_adjusted')
    ).filter(
        remaining_quantity__gt=0.001  # Only show logs with stock left
    ).order_by('release_timestamp')

    data = [
        {
            'id': log.id,
            'display_text': f"QC: {log.qc_no or 'N/A'} | متاح: {log.remaining_quantity:.3f} | السعر: {log.costing_unit_price or 'N/A'}",
            'remaining_quantity': log.remaining_quantity,
            'costing_unit_price': log.costing_unit_price
        }
        for log in released_logs
    ]
    return JsonResponse(data, safe=False)


def api_get_stock_sources_for_product(request: HttpRequest, product_id: int) -> JsonResponse:
    """
    Returns a detailed list of all stock sources (InventoryLog and FinishedProductReceipt)
    for a given product, using robust subqueries to ensure accurate remaining quantity.
    """
    product = get_object_or_404(Product, pk=product_id)
    sources = []

    # 1. Get Raw Material / MRO sources from InventoryLog
    if product.product_type != Product.ProductType.FINAL_PRODUCT:
        # --- ROBUST SUBQUERY APPROACH FOR RAW MATERIALS ---
        consumed_prod_subquery = BatchItem.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('actual_quantity')).values('total')
        consumed_internal_subquery = InventoryConsumption.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity_consumed')).values('total')
        returned_subquery = ProductionReturn.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('quantity')).values('total')
        adjusted_subquery = InventoryAdjustment.objects.filter(source_log_id=OuterRef('pk')).values('source_log_id').annotate(total=Sum('adjustment_quantity')).values('total')

        logs = InventoryLog.objects.filter(
            product_id=product_id
        ).exclude(
            status__in=[InventoryLog.Status.REJECTED, InventoryLog.Status.SCRAPPED]
        ).annotate(
            total_consumed_prod=Coalesce(Subquery(consumed_prod_subquery, output_field=FloatField()), 0.0),
            total_consumed_internal=Coalesce(Subquery(consumed_internal_subquery, output_field=FloatField()), 0.0),
            total_returned=Coalesce(Subquery(returned_subquery, output_field=FloatField()), 0.0),
            total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
        ).annotate(
            remaining_quantity=F('quantity') - F('total_consumed_prod') - F('total_consumed_internal') + F('total_returned') + F('total_adjusted')
        ).order_by('release_timestamp')

        for log in logs:
            sources.append({
                'type': 'log',
                'id': log.id,
                'identifier': f"QC: {log.qc_no}",
                'date': log.release_timestamp.strftime('%Y-%m-%d') if log.release_timestamp else log.timestamp.strftime('%Y-%m-%d'),
                'original_quantity': log.quantity,
                'remaining_quantity': log.remaining_quantity,
                'status': log.status,
                'status_display': log.get_status_display(),
            })

    # 2. Get Finished Product sources from FinishedProductReceipt
    else:
        # --- ROBUST SUBQUERY APPROACH FOR FINISHED GOODS ---
        dispatched_subquery = FinishedProductDispatch.objects.filter(sales_order_item__finished_product_id=OuterRef('pk')).values('sales_order_item__finished_product_id').annotate(total=Sum('quantity')).values('total')
        adjusted_subquery = InventoryAdjustment.objects.filter(source_finished_product_id=OuterRef('pk')).values('source_finished_product_id').annotate(total=Sum('adjustment_quantity')).values('total')

        receipts = FinishedProductReceipt.objects.filter(
            batch__template__final_product_id=product_id
        ).exclude(
            status=FinishedProductReceipt.Status.REJECTED
        ).annotate(
            total_dispatched=Coalesce(Subquery(dispatched_subquery, output_field=FloatField()), 0.0),
            total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
        ).annotate(
            remaining_quantity=F('total_quantity_produced') - F('total_dispatched') + F('total_adjusted')
        ).order_by('release_date')

        for receipt in receipts:
            sources.append({
                'type': 'receipt',
                'id': receipt.id,
                'identifier': f"Batch: {receipt.individual_batch_number}",
                'date': receipt.release_date.strftime('%Y-%m-%d') if receipt.release_date else receipt.receipt_date.strftime('%Y-%m-%d'),
                'original_quantity': receipt.total_quantity_produced,
                'remaining_quantity': receipt.remaining_quantity,
                'status': receipt.status,
                'status_display': receipt.get_status_display(),
            })

    return JsonResponse({'sources': sources})


def api_get_uninvoiced_receipts(request: HttpRequest, supplier_id: int) -> JsonResponse:
    """
    API endpoint to get released, un-invoiced receipts for a specific supplier.
    """
    receipts = InventoryLog.objects.filter(
        company_id=supplier_id,
        status=InventoryLog.Status.RELEASED,
        invoice_item__isnull=True
    ).select_related('product').order_by('-release_timestamp')

    data = [
        {
            'id': receipt.id,
            'product_name': f"{receipt.product.name} ({receipt.product.code})",
            'qc_no': receipt.qc_no,
            'receipt_date': receipt.release_timestamp.strftime('%Y-%m-%d') if receipt.release_timestamp else '',
            'quantity': receipt.quantity,
            'total_cost': str(receipt.total_cost.quantize(Decimal('0.001')))
        } for receipt in receipts
    ]
    return JsonResponse(data, safe=False)


def api_get_uninvoiced_dispatches(request: HttpRequest, so_id: int) -> JsonResponse:
    """
    API endpoint to get un-invoiced dispatches for a specific Sales Order.
    """
    dispatches = FinishedProductDispatch.objects.filter(
        sales_order_item__sales_order_id=so_id,
        invoice_item__isnull=True
    ).select_related(
        'sales_order_item__finished_product__batch__template__final_product'
    ).order_by('dispatch_date')

    data = [
        {
            'id': dispatch.id,
            'product_name': dispatch.sales_order_item.finished_product.batch.template.final_product.name,
            'dispatch_date': dispatch.dispatch_date.strftime('%Y-%m-%d'),
            'quantity': dispatch.quantity,
            'total_value': str((Decimal(str(dispatch.quantity)) * dispatch.sales_order_item.base_price_per_unit).quantize(Decimal('0.001')))
        } for dispatch in dispatches
    ]
    return JsonResponse(data, safe=False)


def api_get_unsettled_transactions(request: HttpRequest, employee_id: int) -> JsonResponse:
    """
    Finds all InventoryLog and ExpenseLog transactions assigned to an employee
    that have not yet been used to settle any advance.
    """
    try:
        employee = get_object_or_404(Employee, pk=employee_id)

        # Get IDs of transactions already used in any settlement
        settled_inventory_ids = EmployeeAdvanceSettlement.objects.filter(
            content_type=ContentType.objects.get_for_model(InventoryLog)
        ).values_list('object_id', flat=True)
        
        settled_expense_ids = EmployeeAdvanceSettlement.objects.filter(
            content_type=ContentType.objects.get_for_model(ExpenseLog)
        ).values_list('object_id', flat=True)

        # Find un-settled inventory receipts
        unsettled_receipts = InventoryLog.objects.filter(
            employee=employee,
            status=InventoryLog.Status.RELEASED
        ).exclude(id__in=settled_inventory_ids)

        # Find un-settled general expenses
        unsettled_expenses = ExpenseLog.objects.filter(
            employee=employee
        ).exclude(id__in=settled_expense_ids)

        data = []
        for receipt in unsettled_receipts:
            data.append({
                'id': receipt.id,
                'type': 'inventorylog',
                'type_display': 'Receipt',
                'date': receipt.release_timestamp.strftime('%Y-%m-%d'),
                'description': f"Receipt for {receipt.product.name} (QC: {receipt.qc_no})",
                'amount': str(receipt.total_cost.quantize(Decimal('0.001')))
            })

        for expense in unsettled_expenses:
            data.append({
                'id': expense.id,
                'type': 'expenselog',
                'type_display': 'Expense',
                'date': expense.expense_date.strftime('%Y-%m-%d'),
                'description': expense.description,
                'amount': str(expense.amount.quantize(Decimal('0.001')))
            })
        
        # Sort by date
        data.sort(key=lambda x: x['date'])

        return JsonResponse({'transactions': data})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_get_journal_entry_details(request: HttpRequest, je_id: int) -> JsonResponse:
    """
    API endpoint to get the details of a single Journal Entry, including its lines.
    """
    try:
        je = get_object_or_404(JournalEntry.objects.prefetch_related('lines__account'), pk=je_id)
        
        lines_data = [
            {
                'account_name': line.account.name,
                'account_code': line.account.code,
                'amount': line.amount,
                'entry_type': line.entry_type,
            } for line in je.lines.all()
        ]
        
        data = {
            'id': je.id,
            'date': je.date,
            'description': je.description,
            'lines': lines_data,
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def api_get_undispatched_so_items(request: HttpRequest, so_id: int) -> JsonResponse:
    """
    API endpoint to get items for a specific Sales Order that have remaining quantities to be dispatched.
    """
    so_items = SalesOrderItem.objects.filter(
        sales_order_id=so_id
    ).select_related(
        'finished_product__batch__template__final_product'
    ).annotate(
        total_dispatched=Coalesce(Sum('dispatches__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        quantity_remaining=F('quantity_ordered') - F('total_dispatched')
    ).filter(
        quantity_remaining__gt=0.001
    )

    data = [
        {
            'id': item.id,
            'product_name': item.finished_product.batch.template.final_product.name,
            'batch_number': item.finished_product.individual_batch_number,
            'quantity_ordered': item.quantity_ordered,
            'quantity_remaining': item.quantity_remaining,
            'unit': item.finished_product.batch.template.final_product.unit,
        } for item in so_items
    ]
    return JsonResponse(data, safe=False)