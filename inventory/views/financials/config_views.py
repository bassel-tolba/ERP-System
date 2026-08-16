# gipcco_project/inventory/views/financials/config_views.py

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ...models import (
    CostPool, AllocationDriver, Account
)

# ==============================================================================
#  OVERHEAD CONFIGURATION VIEWS
# ==============================================================================

def cost_pools_list(request: HttpRequest) -> HttpResponse:
    """
    Manages the Cost Pool hierarchy (listing, creation, editing, and deletion).
    """
    if request.method == 'POST':
        try:
            action = request.POST.get('action', 'save') # Default to 'save' for backward compatibility

            if action == 'delete':
                pool_id = request.POST.get('pool_id')
                pool_to_delete = get_object_or_404(CostPool, pk=pool_id)

                # Safety Check 1: Cannot delete if it has children
                if pool_to_delete.children.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has sub-pools. Please delete or reassign them first.")
                    return redirect('inventory:cost_pools_list')

                # Safety Check 2: Cannot delete if it has associated expenses
                if pool_to_delete.expenses.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has expenses logged against it.")
                    return redirect('inventory:cost_pools_list')
                
                # Safety Check 3: Cannot delete if used in an allocation run
                if pool_to_delete.allocation_runs.exists():
                    messages.error(request, f"Cannot delete '{pool_to_delete.name}' because it has been used in an overhead allocation run.")
                    return redirect('inventory:cost_pools_list')

                pool_name = pool_to_delete.name
                pool_to_delete.delete()
                messages.success(request, f"Cost Pool '{pool_name}' has been deleted successfully.")

            elif action == 'save':
                pool_id = request.POST.get('pool_id')
                name = request.POST.get('name', '').strip()
                parent_id = request.POST.get('parent') or None
                gl_account_id = request.POST.get('gl_account') or None

                if not name:
                    raise ValueError("Cost Pool Name cannot be empty.")

                if pool_id: # This is an Edit operation
                    pool = get_object_or_404(CostPool, pk=pool_id)
                    pool.name = name
                    pool.parent_id = parent_id
                    pool.gl_account_id = gl_account_id
                    pool.save()
                    messages.success(request, f"Cost Pool '{name}' updated successfully.")
                else: # This is a Create operation
                    CostPool.objects.create(
                        name=name,
                        parent_id=parent_id,
                        gl_account_id=gl_account_id
                    )
                    messages.success(request, f"Cost Pool '{name}' created successfully.")
        
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:cost_pools_list')

    # For GET request
    all_pools = CostPool.objects.select_related('parent', 'gl_account').all()
    expense_accounts = Account.objects.filter(account_type=Account.AccountType.EXPENSE).order_by('code')
    
    # Build a hierarchical structure for display
    root_pools = [pool for pool in all_pools if not pool.parent]
    for pool in root_pools:
        pool.children_list = [child for child in all_pools if child.parent_id == pool.id]

    context = {
        'active_page': 'financials',
        'sub_page': 'cost_pools',
        'all_pools': all_pools,
        'root_pools': root_pools,
        'expense_accounts': expense_accounts,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/cost_pools_list_content.html', context)
    return render(request, 'inventory/cost_pools_list.html', context)


def allocation_drivers_list(request: HttpRequest) -> HttpResponse:
    """
    Manages the Allocation Driver master list (listing, creation, editing).
    """
    if request.method == 'POST':
        try:
            driver_id = request.POST.get('driver_id')
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()

            if not name:
                raise ValueError("Driver name cannot be empty.")

            if driver_id: # Editing - Only description can be edited
                driver = get_object_or_404(AllocationDriver, pk=driver_id)
                driver.description = description
                driver.save()
                messages.success(request, f"Allocation Driver '{driver.get_name_display()}' description updated successfully.")
            else: # Creating
                AllocationDriver.objects.create(name=name, description=description)
                messages.success(request, f"Allocation Driver created successfully.")
        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:allocation_drivers_list')

    # --- NEW: Get existing driver names to exclude them from the choices in the create form ---
    existing_driver_names = list(AllocationDriver.objects.values_list('name', flat=True))
    available_choices = [
        (value, label) for value, label in AllocationDriver.DriverChoices.choices 
        if value not in existing_driver_names
    ]

    context = {
        'active_page': 'financials',
        'sub_page': 'allocation_drivers',
        'drivers': AllocationDriver.objects.all(),
        'available_choices': available_choices, # NEW
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/allocation_drivers_list_content.html', context)
    return render(request, 'inventory/allocation_drivers_list.html', context)
