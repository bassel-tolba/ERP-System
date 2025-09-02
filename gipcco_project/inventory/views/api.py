from django.db.models import Sum, F, FloatField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404

from ..models import Batch, BatchItem, Product, ProductTag


# --- API Views ---

def get_used_qc_sources(request: HttpRequest, product_pk: int) -> JsonResponse:
    """
    API endpoint to get inventory sources that have been consumed for a product.
    """
    get_object_or_404(Product, pk=product_pk)
    
    # Get all inventory logs that have been used as a source at least once for this product.
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