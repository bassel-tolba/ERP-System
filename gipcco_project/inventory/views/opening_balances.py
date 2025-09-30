# # gipcco_project/inventory/views/opening_balances.py

# from datetime import datetime, time
# from decimal import Decimal

# from django.contrib import messages
# from django.db import transaction
# from django.http import HttpRequest, HttpResponse
# from django.shortcuts import get_object_or_404, redirect, render
# from django.utils import timezone
# from django.views.decorators.http import require_POST

# from ..models import OpeningBalance, Product
# # --- MODIFIED: Import from the new costing service ---
# from ..services.costing_service import recalculate_cost_history_for_product


# def opening_balances(request: HttpRequest) -> HttpResponse:
#     """
#     Displays and handles the creation of opening balances.
#     """
#     if request.method == 'POST':
#         product_id = request.POST.get('product_id')
#         quantity_str = request.POST.get('quantity')
#         balance_date_str = request.POST.get('balance_date')
#         total_value_str = request.POST.get('total_value', '0.000')

#         if not all([product_id, quantity_str, balance_date_str, total_value_str]):
#             messages.error(request, "الرجاء تعبئة جميع الحقول المطلوبة.")
#             return redirect('inventory:opening_balances')

#         try:
#             with transaction.atomic():
#                 product = get_object_or_404(Product, pk=product_id)
#                 quantity = float(quantity_str)
#                 total_value = Decimal(total_value_str)
#                 balance_date = datetime.strptime(balance_date_str, '%Y-%m-%d')
#                 balance_datetime = timezone.make_aware(datetime.combine(balance_date.date(), time.min))

#                 OpeningBalance.objects.create(
#                     product=product,
#                     quantity=quantity,
#                     balance_date=balance_datetime,
#                     total_value=total_value
#                 )
                
#                 recalculate_cost_history_for_product(product.id, balance_datetime)
                
#             messages.success(request, f"تمت إضافة الرصيد الافتتاحي للمنتج '{product.name}' بنجاح.")
#         except Exception as e:
#             messages.error(request, f"حدث خطأ: {e}")
        
#         return redirect('inventory:opening_balances')

#     balances = OpeningBalance.objects.select_related('product').order_by('product__name', '-balance_date')
#     products = Product.objects.filter(product_type__in=['مواد خام', 'تعبئه و تغليف']).order_by('name')
    
#     context = {
#         'active_page': 'opening_balances',
#         'balances': balances,
#         'products': products,
#         'today_date': timezone.now().strftime('%Y-%m-%d'),
#     }
    
#     template_name = 'inventory/opening_balances.html'
#     if 'X-Partial-Request' in request.headers:
#         template_name = 'inventory/partials/opening_balances_content.html'
        
#     return render(request, template_name, context)

# @require_POST
# def edit_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
#     """
#     Handles editing an existing opening balance.
#     """
#     balance = get_object_or_404(OpeningBalance, pk=pk)
#     original_balance_date = balance.balance_date
    
#     quantity_str = request.POST.get('quantity')
#     balance_date_str = request.POST.get('balance_date')
#     total_value_str = request.POST.get('total_value', '0.000')

#     if not all([quantity_str, balance_date_str, total_value_str]):
#         messages.error(request, "الرجاء تعبئة جميع الحقول المطلوبة.")
#         return redirect('inventory:opening_balances')
    
#     try:
#         with transaction.atomic():
#             balance.quantity = float(quantity_str)
#             balance.total_value = Decimal(total_value_str)
            
#             new_balance_date = datetime.strptime(balance_date_str, '%Y-%m-%d')
#             balance.balance_date = timezone.make_aware(datetime.combine(new_balance_date.date(), time.min))
            
#             balance.save()

#             recalc_start_date = min(original_balance_date, balance.balance_date)
#             recalculate_cost_history_for_product(balance.product_id, recalc_start_date)

#         messages.success(request, f"تم تعديل الرصيد الافتتاحي للمنتج '{balance.product.name}' بنجاح.")
#     except Exception as e:
#         messages.error(request, f"حدث خطأ أثناء التعديل: {e}")
    
#     return redirect('inventory:opening_balances')

# @require_POST
# def delete_opening_balance(request: HttpRequest, pk: int) -> HttpResponse:
#     """
#     Handles deleting an opening balance.
#     """
#     balance = get_object_or_404(OpeningBalance, pk=pk)
#     product_id_to_recalc = balance.product_id
#     balance_date_to_recalc = balance.balance_date

#     try:
#         with transaction.atomic():
#             balance.delete()
#             recalculate_cost_history_for_product(product_id_to_recalc, balance_date_to_recalc)

#         messages.info(request, "تم حذف الرصيد الافتتاحي بنجاح.")
#     except Exception as e:
#         messages.error(request, f"حدث خطأ أثناء الحذف: {e}")

#     return redirect('inventory:opening_balances')