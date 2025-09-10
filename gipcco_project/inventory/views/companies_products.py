# gipcco_project/inventory/views/companies_products.py

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..models import Company, Product, ProductTag, Account


def companies(request: HttpRequest) -> HttpResponse:
    """
    Manages companies. Handles both displaying the list and adding a new company.
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        if name:
            company, created = Company.objects.get_or_create(name=name)
            if created:
                messages.success(request, f'تمت إضافة شركة "{name}" بنجاح.')
            else:
                messages.error(request, f'اسم الشركة "{name}" موجود بالفعل.')
        return redirect('inventory:companies')

    context = {
        'active_page': 'companies',
        'companies': Company.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/companies_content.html', context)
    return render(request, 'inventory/companies.html', context)


@require_POST
def edit_company(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing a company's name.
    """
    company = get_object_or_404(Company, pk=pk)
    name = request.POST.get('name')
    if name:
        if Company.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, "هذا الاسم مستخدم بالفعل.")
        else:
            company.name = name
            company.save()
            messages.success(request, "تم تعديل اسم الشركة بنجاح.")
    return redirect('inventory:companies')


@require_POST
def delete_company(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a company.
    """
    company = get_object_or_404(Company, pk=pk)
    company.delete()
    messages.info(request, 'تم حذف الشركة بنجاح.')
    return redirect('inventory:companies')


def products(request: HttpRequest) -> HttpResponse:
    """
    Manages products. Handles both displaying the list and adding a new product.
    """
    if request.method == 'POST':
        name = request.POST.get('name')
        code = request.POST.get('code')
        product_type = request.POST.get('product_type')
        unit = request.POST.get('unit')
        tag_ids = request.POST.getlist('tags') # Get selected tag IDs

        if Product.objects.filter(code=code).exists():
            messages.error(request, f'كود المنتج "{code}" موجود بالفعل.')
        else:
            product = Product.objects.create(name=name, code=code, product_type=product_type, unit=unit)
            if tag_ids:
                product.tags.set(tag_ids)
            messages.success(request, f'تمت إضافة المنتج "{name}" بنجاح.')
        return redirect('inventory:products')

    context = {
        'active_page': 'products',
        'products': Product.objects.prefetch_related('tags').order_by('name'),
        'product_type_choices': Product.ProductType.choices,
        'all_tags': ProductTag.objects.all(),
        # --- NEW: Pass accounts for override dropdowns ---
        'all_accounts': Account.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/products_content.html', context)
    return render(request, 'inventory/products.html', context)


@require_POST
def edit_product(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing product.
    """
    product = get_object_or_404(Product, pk=pk)
    name = request.POST.get('name')
    code = request.POST.get('code')
    p_type = request.POST.get('product_type')
    unit = request.POST.get('unit')
    tag_ids = request.POST.getlist('tags')
    
    # --- NEW: Get account override IDs from the form ---
    override_inventory_account_id = request.POST.get('override_inventory_account')
    override_cogs_expense_account_id = request.POST.get('override_cogs_expense_account')
    override_sales_revenue_account_id = request.POST.get('override_sales_revenue_account')

    if all([name, code, p_type, unit]):
        if Product.objects.filter(code=code).exclude(pk=pk).exists():
            messages.error(request, "كود المنتج موجود بالفعل لمنتج آخر.")
        else:
            product.name = name
            product.code = code
            product.product_type = p_type
            product.unit = unit
            
            # --- NEW: Set account override fields ---
            product.override_inventory_account_id = override_inventory_account_id if override_inventory_account_id else None
            product.override_cogs_expense_account_id = override_cogs_expense_account_id if override_cogs_expense_account_id else None
            product.override_sales_revenue_account_id = override_sales_revenue_account_id if override_sales_revenue_account_id else None

            product.save()
            product.tags.set(tag_ids)
            messages.success(request, "تم تعديل المنتج بنجاح.")
    return redirect('inventory:products')


@require_POST
def delete_product(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a product.
    """
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.info(request, 'تم حذف المنتج وجميع سجلاته بنجاح.')
    return redirect('inventory:products')


@require_POST
def create_tag(request: HttpRequest) -> HttpResponse:
    """
    Handles creating a new product tag and associating it with products.
    """
    name = request.POST.get('name')
    product_ids = request.POST.getlist('products')
    
    if not name:
        messages.error(request, 'يرجى إدخال اسم الوسم.')
        return redirect('inventory:products')
        
    tag, created = ProductTag.objects.get_or_create(name=name)
    if created:
        if product_ids:
            products = Product.objects.filter(id__in=product_ids)
            for product in products:
                product.tags.add(tag)
        messages.success(request, f'تمت إضافة الوسم "{name}" بنجاح.')
    else:
        messages.error(request, f'الوسم "{name}" موجود بالفعل.')
    
    return redirect('inventory:products')


@require_POST
def edit_tag(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles editing an existing product tag.
    """
    tag = get_object_or_404(ProductTag, pk=pk)
    name = request.POST.get('name')
    
    if not name:
        messages.error(request, 'يرجى إدخال اسم الوسم.')
        return redirect('inventory:products')
    
    if ProductTag.objects.filter(name=name).exclude(pk=pk).exists():
        messages.error(request, "هذا الاسم مستخدم بالفعل.")
    else:
        tag.name = name
        tag.save()
        messages.success(request, "تم تعديل الوسم بنجاح.")
    
    return redirect('inventory:products')


@require_POST
def delete_tag(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a product tag.
    """
    tag = get_object_or_404(ProductTag, pk=pk)
    name = tag.name
    tag.delete()
    messages.success(request, f'تم حذف الوسم "{name}" بنجاح.')
    return redirect('inventory:products')