# gipcco_project/inventory/views/employees.py
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.contrib import messages
from django.utils import timezone
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, F, Value, DecimalField, ProtectedError
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal

from ..models import (
    Employee, EmployeeAdvance, EmployeeAdvanceSettlement, Payment, BankAccount,
    InventoryLog, ExpenseLog
)

def manage_employees(request: HttpRequest) -> HttpResponse:
    """
    Manages the Employee master list (Create, Read, Update, Delete).
    """
    if request.method == 'POST':
        action = request.POST.get('action')
        employee_pk = request.POST.get('employee_pk')

        try:
            with transaction.atomic():
                if action == 'delete':
                    employee = get_object_or_404(Employee, pk=employee_pk)
                    employee.delete()
                    messages.success(request, f"Employee '{employee.full_name}' has been deleted.")
                
                else: # Create or Edit
                    is_active_str = request.POST.get('is_active', 'off')
                    
                    employee_data = {
                        'employee_id': request.POST.get('employee_id').strip(),
                        'first_name': request.POST.get('first_name').strip(),
                        'last_name': request.POST.get('last_name').strip(),
                        'job_title': request.POST.get('job_title', '').strip(),
                        'is_active': True if is_active_str == 'on' else False
                    }

                    if not all([employee_data['employee_id'], employee_data['first_name'], employee_data['last_name']]):
                        raise ValueError("Employee ID, First Name, and Last Name are required.")

                    if action == 'edit':
                        employee = get_object_or_404(Employee, pk=employee_pk)
                        Employee.objects.filter(pk=employee_pk).update(**employee_data)
                        messages.success(request, f"Successfully updated details for '{employee.full_name}'.")
                    else: # Create
                        Employee.objects.create(**employee_data)
                        messages.success(request, "New employee created successfully.")

        except IntegrityError:
            messages.error(request, "An employee with this Employee ID already exists.")
        except ProtectedError:
            messages.error(request, "Cannot delete this employee as they have financial records attached. You can deactivate the employee instead.")
        except (ValueError, TypeError) as e:
            messages.error(request, f"Data Error: {e}")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
        
        return redirect('inventory:manage_employees')

    # GET request
    employees = Employee.objects.all().order_by('first_name', 'last_name')
    context = {
        'active_page': 'settings',
        'sub_page': 'manage_employees',
        'employees': employees,
    }
    
    template_name = 'inventory/manage_employees.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/manage_employees_content.html'
    return render(request, template_name, context)


def employee_financials_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Displays a list of all employees and their outstanding advance balances.
    """
    employees = Employee.objects.filter(is_active=True)
    
    context = {
        'active_page': 'employee_financials',
        'employees': employees,
    }
    
    template_name = 'inventory/employee_financials_dashboard.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/employee_financials_dashboard_content.html'
    return render(request, template_name, context)


def employee_advance_detail(request: HttpRequest, employee_id: int) -> HttpResponse:
    """
    Manages advances for a single employee.
    - GET: Displays existing advances and forms to create/settle.
    - POST: Handles creation of new advances.
    """
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                bank_account_id = request.POST.get('bank_account')
                amount_str = request.POST.get('amount')
                advance_date_str = request.POST.get('advance_date')
                notes = request.POST.get('notes', '')

                if not all([bank_account_id, amount_str, advance_date_str]):
                    raise ValueError("Please fill all required fields for the advance.")

                amount = Decimal(amount_str)
                if amount <= 0:
                    raise ValueError("Advance amount must be positive.")

                # 1. Create the underlying Payment transaction
                payment = Payment.objects.create(
                    payment_date=advance_date_str,
                    amount=amount,
                    bank_account_id=bank_account_id,
                    payment_type=Payment.PaymentType.PAYMENT_OUT,
                    description=f"Advance to employee: {employee.full_name}",
                    notes=notes
                )

                # 2. Create the EmployeeAdvance record, linking to the payment
                EmployeeAdvance.objects.create(
                    employee=employee,
                    advance_date=advance_date_str,
                    amount=amount,
                    source_payment=payment,
                    notes=notes
                )
                messages.success(request, f"Successfully created advance of {amount} for {employee.full_name}.")

        except (ValueError, TypeError) as e:
            messages.error(request, f"Data Error: {e}")
        except Exception as e:
            messages.error(request, f"An unexpected error occurred: {e}")
        
        return redirect('inventory:employee_advance_detail', employee_id=employee_id)

    # GET request logic
    advances = EmployeeAdvance.objects.filter(employee=employee).order_by('-advance_date')
    
    context = {
        'active_page': 'employee_financials',
        'employee': employee,
        'advances': advances,
        'bank_accounts': BankAccount.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    
    template_name = 'inventory/employee_advance_detail.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/employee_advance_detail_content.html'
    return render(request, template_name, context)


def settle_employee_advance(request: HttpRequest, advance_id: int) -> HttpResponse:
    """
    Handles the POST request to settle an advance with selected transactions.
    """
    if request.method != 'POST':
        return redirect('inventory:employee_financials_dashboard')

    advance = get_object_or_404(EmployeeAdvance, pk=advance_id)
    employee_id = advance.employee_id
    
    try:
        settlement_items_str = request.POST.get('settlement_items', '[]')
        settlement_items = json.loads(settlement_items_str)

        if not settlement_items:
            raise ValueError("No items were selected for settlement.")

        with transaction.atomic():
            total_settled_this_action = Decimal('0.0')
            
            for item in settlement_items:
                content_type_str = item.get('type')
                object_id = item.get('id')
                amount = Decimal(item.get('amount'))
                
                model_map = {
                    'inventorylog': InventoryLog,
                    'expenselog': ExpenseLog
                }
                model = model_map.get(content_type_str)
                
                if not model:
                    raise ValueError(f"Invalid transaction type: {content_type_str}")

                content_type = ContentType.objects.get_for_model(model)
                
                # Create the settlement record
                EmployeeAdvanceSettlement.objects.create(
                    advance=advance,
                    amount_settled=amount,
                    content_type=content_type,
                    object_id=object_id
                )
                total_settled_this_action += amount

            # Update the advance status after settlement
            advance.update_status()
            messages.success(request, f"Successfully settled {total_settled_this_action:.2f} against the advance.")

    except (ValueError, TypeError, json.JSONDecodeError) as e:
        messages.error(request, f"Settlement Error: {e}")
    except Exception as e:
        messages.error(request, f"An unexpected error occurred during settlement: {e}")

    return redirect('inventory:employee_advance_detail', employee_id=employee_id)
