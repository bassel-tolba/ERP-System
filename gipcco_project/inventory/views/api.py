# gipcco_project/inventory/views/api.py
from decimal import Decimal
from django.db.models import Sum, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404

from ..models import Batch, BatchItem, Product, ProductTag, PurchaseOrder, PurchaseOrderItem, FinishedProductReceipt, InventoryLog


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
                'source_qc_no': 'رصيد افتتاحي' if item.source_type == 'opening_balance' else (item.source_log.qc_no if item.source_log else 'N/A')
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
            'base_price_per_unit': item.base_price_per_unit
        } for item in po_items
    ]
    return JsonResponse(data, safe=False)


def api_get_sellable_stock(request: HttpRequest) -> JsonResponse:
    """API endpoint to get released, in-stock finished product batches."""
    sellable_receipts = FinishedProductReceipt.objects.filter(
        status=FinishedProductReceipt.Status.RELEASED
    ).select_related(
        'batch__template__final_product'
    ).annotate(
        total_dispatched=Coalesce(Sum('sales_items__dispatches__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        quantity_available=F('total_quantity_produced') - F('total_dispatched')
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
def api_get_available_stock(request, product_pk):
    """
    API endpoint to get all available, released stock logs for a given product.
    Used for the internal consumption form.
    """
    product = get_object_or_404(Product, pk=product_pk)
    
    # Find all released logs for this product
    released_logs = InventoryLog.objects.filter(
        product=product,
        status=InventoryLog.Status.RELEASED
    ).annotate(
        # Calculate total used from production batches
        total_used_in_prod=Coalesce(Sum('batch_items__actual_quantity'), 0.0, output_field=FloatField()),
        # Calculate total used from internal consumptions
        total_used_in_consumption=Coalesce(Sum('consumptions__quantity_consumed'), 0.0, output_field=FloatField()),
        # Calculate total returned from production
        total_returned=Coalesce(Sum('production_returns__quantity'), 0.0, output_field=FloatField())
    ).annotate(
        # Calculate final remaining quantity
        remaining_quantity=F('quantity') - F('total_used_in_prod') - F('total_used_in_consumption') + F('total_returned')
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



# ===== START OF NEW VIEW =====
def api_batch_details(request: HttpRequest, batch_pk: int) -> JsonResponse:
    """
    Returns key details for a specific batch, used for the 'continuation' feature.
    """
    try:
        batch = get_object_or_404(
            Batch.objects.select_related('template__final_product'), 
            pk=batch_pk
        )
        
        # Parse the batch number to get the 'from' part
        batch_from_str = str(batch.batch_number).split('-')[0]

        data = {
            'shop_order_number': batch.shop_order_number,
            'batch_number_from': batch_from_str, # Use the parsed 'from' part
            'template_id': batch.template.id,
            'template_name': f"{batch.template.name} ({batch.template.final_product.name})"
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=404)