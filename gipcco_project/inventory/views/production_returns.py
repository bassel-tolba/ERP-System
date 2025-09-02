from datetime import datetime

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Q

from ..models import BatchItem, Product, ProductionReturn


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
