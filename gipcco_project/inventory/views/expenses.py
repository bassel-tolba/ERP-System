# gipcco_project/inventory/views/expenses.py

from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from decimal import Decimal

from ..models import Product, InventoryLog, InventoryConsumption, ExpenseLog

def expenses_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Manages the logging of both internal inventory consumption and general expenses.
    Handles GET requests to display forms and POST requests to save data.
    """
    if request.method == 'POST':
        form_type = request.POST.get('form_type')
        
        # --- Handle Internal Consumption Form ---
        if form_type == 'inventory_consumption':
            try:
                with transaction.atomic():
                    product_id = request.POST.get('product_id')
                    source_log_id = request.POST.get('source_log_id')
                    quantity_str = request.POST.get('quantity_consumed')
                    date_str = request.POST.get('consumption_date')
                    department = request.POST.get('department')
                    notes = request.POST.get('notes', '')

                    if not all([product_id, source_log_id, quantity_str, date_str, department]):
                        raise ValueError("يرجى تعبئة جميع الحقول المطلوبة.")

                    log_entry = get_object_or_404(InventoryLog, pk=source_log_id, product_id=product_id)
                    quantity_consumed = float(quantity_str)
                    
                    # Create the consumption record
                    consumption = InventoryConsumption.objects.create(
                        product_id=product_id,
                        source_log=log_entry,
                        quantity_consumed=quantity_consumed,
                        consumption_date=timezone.make_aware(timezone.datetime.strptime(date_str, '%Y-%m-%d')),
                        department=department,
                        cost_at_consumption=(log_entry.unit_price or Decimal('0.0')) * Decimal(str(quantity_consumed)),
                        notes=notes
                    )
                    messages.success(request, f"تم تسجيل استهلاك {consumption.quantity_consumed} من '{consumption.product.name}' بنجاح.")

            except (ValueError, TypeError) as e:
                messages.error(request, f"خطأ في البيانات: {e}")
            except Exception as e:
                messages.error(request, f"حدث خطأ غير متوقع: {e}")
            
            return redirect('inventory:expenses_dashboard')

        # --- Handle General Expense Form ---
        elif form_type == 'general_expense':
            try:
                ExpenseLog.objects.create(
                    description=request.POST.get('description'),
                    expense_date=request.POST.get('expense_date'),
                    amount=Decimal(request.POST.get('amount')),
                    category=request.POST.get('category'),
                    classification=request.POST.get('classification'),
                    notes=request.POST.get('notes', '')
                )
                messages.success(request, "تم تسجيل المصروف العام بنجاح.")
            except (ValueError, TypeError) as e:
                messages.error(request, f"خطأ في البيانات: {e}")
            except Exception as e:
                messages.error(request, f"حدث خطأ غير متوقع: {e}")
            
            return redirect('inventory:expenses_dashboard')

    # --- Handle GET Request ---
    consumable_products = Product.objects.filter(
        Q(product_type=Product.ProductType.MRO) | Q(product_type=Product.ProductType.CONSUMABLE)
    )
    
    context = {
        'active_page': 'expenses_reports',
        'consumable_products': consumable_products,
        'departments': InventoryConsumption.Department.choices,
        'expense_categories': ExpenseLog.Category.choices,
        'expense_classifications': ExpenseLog.Classification.choices,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'all_consumptions': InventoryConsumption.objects.select_related('product').all()[:20],
        'all_general_expenses': ExpenseLog.objects.all()[:20],
    }
    
    template_name = 'inventory/expenses_dashboard.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/expenses_dashboard_content.html'
    return render(request, template_name, context)