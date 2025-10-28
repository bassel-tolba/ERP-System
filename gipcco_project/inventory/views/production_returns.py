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
from django.core.exceptions import ValidationError, PermissionDenied

from django.core.exceptions import ValidationError, PermissionDenied

from ..models import BatchItem, Product, ProductionReturn
from ..services import production_returns_service


# --- Production Returns Views ---

def production_returns(request: HttpRequest) -> HttpResponse:
    """
    Manages production returns. Handles listing returns and adding a new one.
    """
    if request.method == 'POST':
        try:
            quantity = float(request.POST.get('quantity'))
            return_date = timezone.make_aware(datetime.strptime(request.POST.get('return_date'), '%Y-%m-%d'))
            batch_id_str = request.POST.get('batch_id')
            
            production_returns_service.create_production_return(
                product_id=request.POST.get('product_id'),
                source_log_id=request.POST.get('source_log_id'),
                quantity=quantity,
                return_date=return_date,
                notes=request.POST.get('notes', ''),
                batch_id=int(batch_id_str) if batch_id_str else None
            )
            messages.success(request, "تم تسجيل المرتجع بنجاح.")
        except (ValidationError, ValueError) as e:
            messages.error(request, f"حدث خطأ أثناء الحفظ: {e}")
        except Exception as e:
            messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
        return redirect('inventory:production_returns')

    status_filter = request.GET.get('status', 'all')
    returns_query = ProductionReturn.objects.select_related('product', 'source_log')

    if status_filter == 'posted':
        returns_query = returns_query.filter(status=ProductionReturn.Status.POSTED)
    elif status_filter == 'cancelled':
        returns_query = returns_query.filter(status=ProductionReturn.Status.CANCELLED)

    context = {
        'active_page': 'production_returns',
        'returns': returns_query.all(),
        'products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'is_partial_request': 'X-Partial-Request' in request.headers,
        'active_filter': status_filter
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/production_returns_content.html', context)
    return render(request, 'inventory/production_returns.html', context)



@require_POST
def cancel_production_return_view(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles cancelling a production return non-destructively by calling the production service.
    """
    pr_return = get_object_or_404(ProductionReturn, pk=pk)
    justification = request.POST.get('justification', '')

    if not justification:
        messages.error(request, "سبب الإلغاء مطلوب.")
        return redirect('inventory:production_returns')

    try:
        production_returns_service.cancel_production_return(
            prod_return=pr_return,
            user=request.user,
            justification=justification
        )
        messages.info(request, 'تم إلغاء سجل الإرجاع وتحديث التكاليف بنجاح.')
    except (ValidationError, PermissionError) as e:
        messages.error(request, f"خطأ في الإلغاء: {e}")

    return redirect('inventory:production_returns')