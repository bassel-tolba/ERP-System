
# gipcco_project/inventory/views/api.py
from decimal import Decimal
from django.db.models import Sum, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404

from ..models import Batch, BatchItem, Product, ProductTag, PurchaseOrder, PurchaseOrderItem


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
            # --- MODIFIED: Use the effective_unit_price property from the model ---
            'unit_price': item.effective_unit_price
        } for item in po_items
    ]
    return JsonResponse(data, safe=False)