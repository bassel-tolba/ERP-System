# gipcco_project/inventory/views/adjustments.py
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import ValidationError
import json

from ..models import InventoryCount, Product, InventoryAdjustment
from ..services.adjustment_service import start_inventory_count, create_adjustments_from_form, auto_distribute_finished_good_shortage, finalize_inventory_count

logger = logging.getLogger(__name__)

@login_required
def inventory_counts_list(request: HttpRequest) -> HttpResponse:
    """Displays a list of all inventory count events."""
    logger.debug(f"inventory_counts_list called by user {request.user.username}.")
    counts = InventoryCount.objects.select_related('created_by').all()
    context = {
        'active_page': 'inventory_counts',
        'counts': counts,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/inventory_counts_list_content.html', context)
    return render(request, 'inventory/inventory_counts_list.html', context)


@login_required
def create_inventory_count(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new inventory count event."""
    logger.debug(f"create_inventory_count called by user {request.user.username} with method {request.method}.")
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        product_ids = request.POST.getlist('products')
        include_quarantined = request.POST.get('include_quarantined') == 'true'
        logger.info(f"Attempting to create inventory count with reason: '{reason}' for product IDs: {product_ids}. Include Quarantined: {include_quarantined}")

        if not reason or not product_ids:
            messages.error(request, "يرجى تقديم سبب للجرد واختيار منتج واحد على الأقل.")
            logger.warning("Inventory count creation failed: Reason or product_ids missing.")
            return redirect('inventory:create_inventory_count')

        try:
            product_ids = [int(pid) for pid in product_ids]
            logger.debug("Calling start_inventory_count service...")
            count = start_inventory_count(
                product_ids=product_ids,
                reason=reason,
                user=request.user,
                include_quarantined=include_quarantined
            )
            messages.success(request, f"تم بدء الجرد بنجاح. يمكنك الآن إدخال الكميات المعدودة.")
            logger.info(f"Successfully created InventoryCount {count.pk}. Redirecting to manage page.")
            return redirect('inventory:manage_inventory_count', pk=count.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء بدء الجرد: {e}")
            logger.exception(f"Exception occurred during inventory count creation for user {request.user.username}.")
            return redirect('inventory:create_inventory_count')

    context = {
        'active_page': 'inventory_counts',
        'products': Product.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/inventory_count_create_content.html', context)
    return render(request, 'inventory/inventory_count_create.html', context)

@login_required
def manage_inventory_count(request: HttpRequest, pk: int) -> HttpResponse:
    """
    The main workspace for an inventory count. Handles both displaying the
    count sheet and submitting the counted quantities.
    """
    logger.debug(f"manage_inventory_count called by user {request.user.username} for count ID {pk} with method {request.method}.")
    inventory_count = get_object_or_404(
        InventoryCount.objects.prefetch_related('items__product'), 
        pk=pk
    )

    if request.method == 'POST':
        logger.info(f"Processing POST request for managing inventory count {pk}.")
        try:
            with transaction.atomic():
                for item in inventory_count.items.all():
                    counted_qty_str = request.POST.get(f'counted_quantity_{item.id}')
                    if counted_qty_str:
                        logger.debug(f"Updating item {item.id} with counted quantity: {counted_qty_str}.")
                        item.counted_quantity = float(counted_qty_str)
                        item.save(update_fields=['counted_quantity'])
            
            # Update the status to show counting is done and allocation is next
            inventory_count.status = InventoryCount.CountStatus.PENDING_ALLOCATION
            inventory_count.save(update_fields=['status'])
            logger.info(f"InventoryCount {pk} status updated to PENDING_ALLOCATION.")
            
            messages.success(request, "تم حفظ الكميات المعدودة. يرجى الآن تخصيص الفروقات.")
            return redirect('inventory:allocate_inventory_variances', pk=inventory_count.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء حفظ البيانات: {e}")
            logger.exception(f"Exception occurred while saving counted quantities for count {pk}.")
            return redirect('inventory:manage_inventory_count', pk=pk)


    context = {
        'active_page': 'inventory_counts',
        'count': inventory_count,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/inventory_count_manage_content.html', context)
    return render(request, 'inventory/inventory_count_manage.html', context)


@login_required
def allocate_inventory_variances(request: HttpRequest, pk: int) -> HttpResponse:
    """
    The workspace for allocating variances to specific stock sources.
    Also handles the final POST to create all adjustments.
    """
    logger.debug(f"allocate_inventory_variances called by user {request.user.username} for count ID {pk} with method {request.method}.")
    inventory_count = get_object_or_404(
        InventoryCount.objects.prefetch_related('items__product'), 
        pk=pk
    )

    if request.method == 'POST':
        logger.info(f"Processing POST for variance allocation for count {pk}.")
        try:
            # The JS will submit the final allocations in a JSON string
            final_allocations_str = request.POST.get('final_allocations')
            logger.debug(f"Received final_allocations JSON string: {final_allocations_str}")
            final_allocations = json.loads(final_allocations_str)
            
            with transaction.atomic():
                for item_id, data in final_allocations.items():
                    logger.info(f"Processing allocation for item {item_id}, type: {data.get('type')}.")
                    if data['type'] == 'manual':
                        logger.debug(f"Calling create_adjustments_from_form for item {item_id} with data: {data}")
                        create_adjustments_from_form(
                            count_item_id=int(item_id),
                            allocations=data['allocations'],
                            reason=data['reason'],
                            notes=data.get('notes', '')
                        )
                    # --- NEW: Handle the specific selection from the user ---
                    elif data['type'] == 'auto_selected':
                        logger.debug(f"Calling auto_distribute_finished_good_shortage for item {item_id} with user-selected receipt IDs: {data.get('receipt_ids')}")
                        auto_distribute_finished_good_shortage(
                            count_item_id=int(item_id),
                            reason=data['reason'],
                            notes=data.get('notes', ''),
                            receipt_ids=data.get('receipt_ids', []) # Pass the list of IDs
                        )
                
                logger.info(f"All allocations processed for count {pk}. Finalizing count...")
                finalize_inventory_count(inventory_count.id)

            messages.success(request, "تم تسجيل جميع تسويات الجرد بنجاح وتحديث تكاليف المنتجات.")
            logger.info(f"Successfully finalized inventory count {pk}. Redirecting to list page.")
            return redirect('inventory:inventory_counts_list')
        except ValidationError as e:
            messages.error(request, f"خطأ في التحقق: {e.message}")
            logger.warning(f"Validation error during variance allocation for count {pk}: {e.message}")
            return redirect('inventory:allocate_inventory_variances', pk=pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ فادح أثناء تسجيل التسويات: {e}")
            logger.exception(f"Critical exception during variance allocation for count {pk}.")
            return redirect('inventory:allocate_inventory_variances', pk=pk)


    # Filter for items that actually have a variance
    variance_items = [
        item for item in inventory_count.items.all() if item.variance_quantity != 0
    ]

    context = {
        'active_page': 'inventory_counts',
        'count': inventory_count,
        'variance_items': variance_items,
        'reason_codes': InventoryAdjustment.ReasonCode.choices,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/inventory_variance_allocation_content.html', context)
    return render(request, 'inventory/inventory_variance_allocation.html', context)
