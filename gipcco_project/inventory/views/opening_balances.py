# gipcco_project/inventory/views/opening_balances.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from ..models import OpeningBalance, Product
# --- NEW: Import costing helper ---
from .helpers import recalculate_cost_history_for_product


def opening_balances(request: HttpRequest) -> HttpResponse:
    """
    Manages opening balances. Handles listing and creating new entries.
    """
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = request.POST.get('quantity')
        balance_date_str = request.POST.get('balance_date')
        unit_cost_str = request.POST.get('unit_cost')
        
        if not all([product_id, quantity, balance_date_str, unit_cost_str]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول.")
        else:
            try:
                balance_date = timezone.make_aware(datetime.strptime(balance_date_str, '%Y-%m-%d'))
                OpeningBalance.objects.create(
                    product_id=product_id,
                    quantity=quantity,
                    balance_date=balance_date,
                    unit_cost=Decimal(unit_cost_str)
                )
                # --- COSTING ENGINE TRIGGER ---
                recalculate_cost_history_for_product(int(product_id), balance_date)
                messages.success(request, "تم حفظ الرصيد الافتتاحي وتحديث التكاليف بنجاح.")
            except Exception as e:
                messages.error(request, f"حدث خطأ: {e}")
        return redirect('inventory:opening_balances')

    context = {
        'active_page': 'opening_balances',
        'balances': OpeningBalance.objects.select_related('product').all(),
        'products': Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT)),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/opening_balances_content.html', context)
    return render(request, 'inventory/opening_balances.html', context)


@require_POST
def edit_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Edits an existing opening balance record and triggers recalculation.
    """
    balance = get_object_or_404(OpeningBalance, pk=pk)
    original_date = balance.balance_date
    product_id = balance.product_id

    try:
        quantity = request.POST.get('quantity')
        balance_date_str = request.POST.get('balance_date')
        unit_cost_str = request.POST.get('unit_cost')

        new_date = timezone.make_aware(datetime.strptime(balance_date_str, '%Y-%m-%d'))
        
        balance.quantity = float(quantity)
        balance.balance_date = new_date
        balance.unit_cost = Decimal(unit_cost_str)
        balance.save()

        # --- COSTING ENGINE TRIGGER ---
        start_recalc_date = min(original_date, new_date)
        recalculate_cost_history_for_product(product_id, start_recalc_date)

        messages.success(request, "تم تعديل الرصيد وتحديث التكاليف بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء التعديل: {e}")
    return redirect('inventory:opening_balances')


@require_POST
def delete_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Deletes an opening balance record and triggers recalculation.
    """
    balance = get_object_or_404(OpeningBalance, pk=pk)
    recalc_start_date = balance.balance_date
    product_id = balance.product_id

    balance.delete()

    # --- COSTING ENGINE TRIGGER ---
    recalculate_cost_history_for_product(product_id, recalc_start_date)
    
    messages.info(request, "تم حذف الرصيد الافتتاحي وتحديث التكاليف بنجاح.")
    return redirect('inventory:opening_balances')