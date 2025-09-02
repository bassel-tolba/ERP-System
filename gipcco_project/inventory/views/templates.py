from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.views.decorators.http import require_POST

from ..models import Product, ShopOrderTemplate, TemplateItem


def shop_order_templates(request: HttpRequest) -> HttpResponse:
    """
    Manages shop order templates. Handles creating and listing templates.
    """
    if request.method == 'POST':
        template_name = request.POST.get('template_name')
        final_product_id = request.POST.get('final_product_id')
        primitive_ids = request.POST.getlist('primitive_product_id')
        quantities = request.POST.getlist('theoretical_quantity')

        if not all([template_name, final_product_id, primitive_ids, quantities]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لإنشاء القالب.")
            return redirect('inventory:shop_order_templates')

        try:
            with transaction.atomic():
                template = ShopOrderTemplate.objects.create(
                    name=template_name,
                    final_product_id=final_product_id
                )
                items_to_create = []
                for pid, qty in zip(primitive_ids, quantities):
                    if pid and qty:
                        items_to_create.append(
                            TemplateItem(
                                template=template,
                                primitive_product_id=pid,
                                theoretical_quantity=qty
                            )
                        )
                TemplateItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم إنشاء قالب أمر التشغيل بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء إنشاء القالب: {e}")
        
        return redirect('inventory:shop_order_templates')
    
    source_template_data = None
    source_items_queryset = None
    copy_from_id = request.GET.get('copy_from')
    if copy_from_id:
        source_template_obj = get_object_or_404(ShopOrderTemplate.objects.prefetch_related('items'), pk=copy_from_id)
        source_items_queryset = source_template_obj.items.all()
        # Serialize the template object into a dictionary for json_script
        source_template_data = {
            'name': source_template_obj.name,
            'final_product_id': source_template_obj.final_product_id
        }

    primitive_products_qs = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))

    context = {
        'active_page': 'shop_orders',
        'templates': ShopOrderTemplate.objects.select_related('final_product').all(),
        'final_products': Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT),
        # CHANGE: Convert QuerySets to lists of dictionaries for JSON serialization.
        'primitive_products': list(primitive_products_qs.values('id', 'name', 'code')),
        'source_template': source_template_data,
        'source_items': list(source_items_queryset.values('primitive_product_id', 'theoretical_quantity')) if source_items_queryset else None,
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_templates_partial.html', context)
    return render(request, 'inventory/shop_order_templates.html', context)


@require_POST
def delete_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles deleting a shop order template.
    """
    template = get_object_or_404(ShopOrderTemplate, pk=pk)
    template.delete()
    messages.info(request, 'تم حذف القالب بنجاح.')
    return redirect('inventory:shop_order_templates')


def view_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the details of a single shop order template.
    """
    template = get_object_or_404(ShopOrderTemplate.objects.select_related('final_product'), pk=pk)
    # This line is crucial. It must not have .values()
    items = template.items.select_related('primitive_product').order_by('primitive_product__name')
    context = {
        'active_page': 'shop_orders',
        'template': template,
        'items': items,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_template_view_content.html', context)
    return render(request, 'inventory/shop_order_template_view.html', context)


def edit_shop_order_template(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Handles both displaying the form to edit a template and processing the submission.
    """
    template = get_object_or_404(ShopOrderTemplate, pk=pk)
    
    if request.method == 'POST':
        template_name = request.POST.get('template_name')
        final_product_id = request.POST.get('final_product_id')
        primitive_ids = request.POST.getlist('primitive_product_id')
        quantities = request.POST.getlist('theoretical_quantity')
        
        if not all([template_name, final_product_id, primitive_ids, quantities]):
            messages.warning(request, "الرجاء تعبئة جميع الحقول لتعديل القالب.")
            return redirect('inventory:edit_shop_order_template', pk=pk)
        
        try:
            with transaction.atomic():
                template.name = template_name
                template.final_product_id = final_product_id
                template.save()

                # Delete old items and create new ones
                template.items.all().delete()
                
                items_to_create = []
                for pid, qty in zip(primitive_ids, quantities):
                    if pid and qty:
                        items_to_create.append(
                            TemplateItem(
                                template=template,
                                primitive_product_id=pid,
                                theoretical_quantity=qty
                            )
                        )
                TemplateItem.objects.bulk_create(items_to_create)
            messages.success(request, "تم تحديث القالب بنجاح.")
            return redirect('inventory:view_shop_order_template', pk=pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تحديث القالب: {e}")
            return redirect('inventory:edit_shop_order_template', pk=pk)

    template_items_qs = template.items.all()
    primitive_products_qs = Product.objects.filter(~Q(product_type=Product.ProductType.FINAL_PRODUCT))

    context = {
        'active_page': 'shop_orders',
        'template': template,
        'final_products': Product.objects.filter(product_type=Product.ProductType.FINAL_PRODUCT),
        # CHANGE: Convert QuerySets to lists of dictionaries for JSON serialization.
        'template_items': list(template_items_qs.values('primitive_product_id', 'theoretical_quantity')),
        'primitive_products': list(primitive_products_qs.values('id', 'name', 'code')),
    }

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/shop_order_template_edit_partial.html', context)
    return render(request, 'inventory/shop_order_template_edit.html', context)