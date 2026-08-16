# gipcco_project/inventory/views/financials/overhead_views.py

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpRequest, HttpResponse

from ...models import (
    FinancialPeriod, CostPool, AllocationDriver, OverheadAllocationRun
)
from ...services.overhead_service import execute_overhead_allocation_run, apply_overhead_to_finished_goods
from ...services.accounting_service import create_je_for_overhead_allocation, create_je_for_overhead_application

# ==============================================================================
#  OVERHEAD ALLOCATION VIEWS
# ==============================================================================

def overhead_allocation_workspace(request: HttpRequest) -> HttpResponse:
    """
    Manages the period-end overhead allocation process.
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'create_run':
                period_id = request.POST.get('financial_period')
                pool_id = request.POST.get('cost_pool')
                driver_id = request.POST.get('allocation_driver')
                OverheadAllocationRun.objects.create(
                    financial_period_id=period_id,
                    cost_pool_id=pool_id,
                    allocation_driver_id=driver_id
                )
                messages.success(request, "New overhead allocation run created successfully.")
            
            elif action == 'calculate_rate':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                execute_overhead_allocation_run(run)
                messages.success(request, f"Successfully calculated overhead rate for run #{run.id}.")

            elif action == 'post_to_gl':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                create_je_for_overhead_allocation(run)
                messages.success(request, f"Successfully posted overhead for run #{run.id} to the General Ledger.")

            elif action == 'apply_to_inventory':
                run_id = request.POST.get('run_id')
                run = get_object_or_404(OverheadAllocationRun, pk=run_id)
                # This service function calculates and applies the cost, returning the total.
                total_applied_cost = apply_overhead_to_finished_goods(run)
                # This service function creates the corresponding JE.
                create_je_for_overhead_application(run, total_applied_cost)
                messages.success(request, f"Successfully applied {total_applied_cost:,.2f} from run #{run.id} to Finished Goods inventory.")

        except Exception as e:
            messages.error(request, f"An error occurred: {e}")
        
        return redirect('inventory:overhead_allocation_workspace')

    # For GET request
    runs = OverheadAllocationRun.objects.select_related(
        'financial_period', 'cost_pool', 'allocation_driver', 'journal_entry', 'application_journal_entry'
    ).all()

    context = {
        'active_page': 'financials',
        'sub_page': 'overhead_allocation',
        'runs': runs,
        'financial_periods': FinancialPeriod.objects.filter(status=FinancialPeriod.Status.OPEN),
        'cost_pools': CostPool.objects.all(),
        'allocation_drivers': AllocationDriver.objects.all(),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/overhead_allocation_workspace_content.html', context)
    return render(request, 'inventory/overhead_allocation_workspace.html', context)
