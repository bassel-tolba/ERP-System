# gipcco_project/inventory/views/landed_cost_views.py

from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import permission_required

from ..services import purchasing_service

@permission_required('inventory.add_landedcostallocation')
def allocation_workspace(request: HttpRequest) -> HttpResponse:
    """
    Displays the main workspace for allocating third-party landed costs
    to inventory receipts and handles the allocation POST request.
    """
    if request.method == 'POST':
        try:
            invoice_ids = request.POST.getlist('invoice_ids')
            receipt_ids = request.POST.getlist('receipt_ids')

            if not invoice_ids or not receipt_ids:
                raise ValidationError("You must select at least one invoice and one receipt.")

            purchasing_service.allocate_landed_costs_from_invoice(
                landed_cost_invoice_ids=[int(i) for i in invoice_ids],
                receipt_log_ids=[int(r) for r in receipt_ids],
                user=request.user
            )
            messages.success(request, "Landed costs were successfully allocated to the selected receipts.")
        except ValidationError as e:
            messages.error(request, e.message)
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
        
        return redirect('inventory:landed_cost_workspace')

    context = {
        'active_page': 'purchasing',
        'sub_page': 'landed_cost_allocation',
    }
    return render(request, 'inventory/landed_cost_workspace.html', context)

