
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Sum, F, FloatField
from django.db.models.functions import Coalesce
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

# --- NEW VIEWS FOR EXPENSE MANAGEMENT ---

def manage_expenses(request: HttpRequest) -> HttpResponse:
    """
    Displays a unified page to manage (view, filter, edit, delete)
    both InventoryConsumption and ExpenseLog records.
    """
    # --- Filter Inventory Consumptions ---
    consumptions_qs = InventoryConsumption.objects.select_related('product', 'source_log').order_by('-consumption_date')
    
    c_query = request.GET.get('c_query', '')
    c_start_date = request.GET.get('c_start_date', '')
    c_end_date = request.GET.get('c_end_date', '')
    c_product = request.GET.get('c_product', '')
    c_department = request.GET.get('c_department', '')

    if c_query:
        consumptions_qs = consumptions_qs.filter(Q(notes__icontains=c_query) | Q(product__name__icontains=c_query))
    if c_start_date:
        consumptions_qs = consumptions_qs.filter(consumption_date__date__gte=c_start_date)
    if c_end_date:
        consumptions_qs = consumptions_qs.filter(consumption_date__date__lte=c_end_date)
    if c_product:
        consumptions_qs = consumptions_qs.filter(product_id=c_product)
    if c_department:
        consumptions_qs = consumptions_qs.filter(department=c_department)

    # --- Filter General Expenses ---
    general_expenses_qs = ExpenseLog.objects.order_by('-expense_date')

    g_query = request.GET.get('g_query', '')
    g_start_date = request.GET.get('g_start_date', '')
    g_end_date = request.GET.get('g_end_date', '')
    g_category = request.GET.get('g_category', '')
    g_classification = request.GET.get('g_classification', '')

    if g_query:
        general_expenses_qs = general_expenses_qs.filter(Q(description__icontains=g_query) | Q(notes__icontains=g_query))
    if g_start_date:
        general_expenses_qs = general_expenses_qs.filter(expense_date__gte=g_start_date)
    if g_end_date:
        general_expenses_qs = general_expenses_qs.filter(expense_date__lte=g_end_date)
    if g_category:
        general_expenses_qs = general_expenses_qs.filter(category=g_category)
    if g_classification:
        general_expenses_qs = general_expenses_qs.filter(classification=g_classification)
        
    consumable_products = Product.objects.filter(
        Q(product_type=Product.ProductType.MRO) | Q(product_type=Product.ProductType.CONSUMABLE)
    )

    context = {
        'active_page': 'expenses_reports',
        'consumptions': consumptions_qs,
        'general_expenses': general_expenses_qs,
        'consumable_products': consumable_products,
        'departments': InventoryConsumption.Department.choices,
        'expense_categories': ExpenseLog.Category.choices,
        'expense_classifications': ExpenseLog.Classification.choices,
        'filter_values': request.GET # Pass filter values back to template
    }
    
    template_name = 'inventory/manage_expenses.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/manage_expenses_content.html'
    return render(request, template_name, context)


def edit_inventory_consumption(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing an InventoryConsumption record."""
    if request.method != 'POST':
        return redirect('inventory:manage_expenses')

    consumption = get_object_or_404(InventoryConsumption, pk=pk)
    
    try:
        with transaction.atomic():
            new_quantity_str = request.POST.get('quantity_consumed')
            if not new_quantity_str:
                raise ValueError("الكمية حقل مطلوب.")
            
            new_quantity = float(new_quantity_str)
            if new_quantity <= 0:
                raise ValueError("يجب أن تكون الكمية أكبر من صفر.")
            
            # --- CRITICAL: STOCK VALIDATION ---
            source_log = consumption.source_log
            old_quantity = consumption.quantity_consumed
            
            # Calculate total consumed from this log, EXCLUDING the current record
            total_consumed_others = source_log.consumptions.exclude(pk=pk).aggregate(
                total=Coalesce(Sum('quantity_consumed'), 0.0, output_field=FloatField())
            )['total']
            
            available_stock_for_this_edit = source_log.quantity - total_consumed_others
            
            if new_quantity > available_stock_for_this_edit:
                raise ValueError(f"الكمية المطلوبة ({new_quantity}) تتجاوز المخزون المتاح من هذا المصدر ({available_stock_for_this_edit:.3f}).")

            # Update fields
            consumption.quantity_consumed = new_quantity
            consumption.department = request.POST.get('department')
            consumption.consumption_date = timezone.make_aware(timezone.datetime.strptime(request.POST.get('consumption_date'), '%Y-%m-%d'))
            consumption.notes = request.POST.get('notes', '')
            # Recalculate cost
            consumption.cost_at_consumption = (source_log.unit_price or Decimal('0.0')) * Decimal(str(new_quantity))
            
            consumption.save()
            messages.success(request, f"تم تحديث سجل الصرف للمنتج '{consumption.product.name}' بنجاح.")

    except ValueError as e:
        messages.error(request, f"خطأ في التحديث: {e}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")

    return redirect('inventory:manage_expenses')


def delete_inventory_consumption(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting an InventoryConsumption record."""
    if request.method != 'POST':
        return redirect('inventory:manage_expenses')
        
    consumption = get_object_or_404(InventoryConsumption, pk=pk)
    product_name = consumption.product.name
    
    try:
        consumption.delete()
        messages.success(request, f"تم حذف سجل الصرف للمنتج '{product_name}' بنجاح. تم إرجاع الكمية للمخزون.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء الحذف: {e}")

    return redirect('inventory:manage_expenses')


def edit_general_expense(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing an ExpenseLog record."""
    if request.method != 'POST':
        return redirect('inventory:manage_expenses')

    expense = get_object_or_404(ExpenseLog, pk=pk)
    
    try:
        amount_str = request.POST.get('amount')
        if not amount_str:
            raise ValueError("المبلغ حقل مطلوب.")
        
        expense.description = request.POST.get('description')
        expense.expense_date = request.POST.get('expense_date')
        expense.amount = Decimal(amount_str)
        expense.category = request.POST.get('category')
        expense.classification = request.POST.get('classification')
        expense.notes = request.POST.get('notes', '')
        
        expense.save()
        messages.success(request, f"تم تحديث المصروف العام '{expense.description}' بنجاح.")

    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في البيانات: {e}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")

    return redirect('inventory:manage_expenses')


def delete_general_expense(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting an ExpenseLog record."""
    if request.method != 'POST':
        return redirect('inventory:manage_expenses')

    expense = get_object_or_404(ExpenseLog, pk=pk)
    desc = expense.description

    try:
        expense.delete()
        messages.success(request, f"تم حذف المصروف العام '{desc}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء الحذف: {e}")

    return redirect('inventory:manage_expenses')