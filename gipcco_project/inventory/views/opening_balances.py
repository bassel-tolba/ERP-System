from datetime import datetime

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from ..models import OpeningBalance, Product


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
