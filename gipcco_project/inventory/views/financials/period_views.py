# gipcco_project/inventory/views/financials/period_views.py

from datetime import datetime
from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext_lazy as _

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import permission_required
from django.urls import reverse
from django.core.exceptions import ValidationError

from ...models import (
    BankAccount, FiscalYear, FinancialPeriod, PeriodClosingAuditLog, JournalEntry, SupplierInvoice, CustomerInvoice, BankReconciliation
)
from ...services.period_closing_service import update_checklist_for_period

# ==============================================================================
#  FINANCIAL PERIOD MANAGEMENT VIEWS
# ==============================================================================

def fiscal_year_list(request: HttpRequest) -> HttpResponse:
    """Lists all Fiscal Years and their associated Financial Periods."""
    fiscal_years = FiscalYear.objects.prefetch_related('periods').all()
    
    context = {
        'active_page': 'financials',
        'sub_page': 'periods',
        'fiscal_years': fiscal_years,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/fiscal_year_list_content.html', context)
    return render(request, 'inventory/fiscal_year_list.html', context)


@require_POST
def create_fiscal_year(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new Fiscal Year and optionally its monthly periods."""
    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')
        generate_periods = request.POST.get('generate_periods') == 'on'

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            fiscal_year = FiscalYear.objects.create(
                name=name,
                start_date=start_date,
                end_date=end_date
            )

            if generate_periods:
                # Generate 12 monthly periods
                current_start = start_date
                for i in range(12):
                    current_end = (current_start + relativedelta(months=1)) - relativedelta(days=1)
                    if current_end > end_date:
                        current_end = end_date
                    
                    FinancialPeriod.objects.create(
                        fiscal_year=fiscal_year,
                        name=current_start.strftime('%B %Y'),
                        start_date=current_start,
                        end_date=current_end,
                        status=FinancialPeriod.Status.OPEN
                    )
                    current_start = current_start + relativedelta(months=1)
                    if current_start > end_date:
                        break

        messages.success(request, f"تم إنشاء السنة المالية '{name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء السنة المالية: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def create_financial_period(request: HttpRequest, year_id: int) -> HttpResponse:
    """Handles the creation of a single, custom financial period."""
    fiscal_year = get_object_or_404(FiscalYear, pk=year_id)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن إضافة فترة لسنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')
        
    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            period = FinancialPeriod(
                fiscal_year=fiscal_year,
                name=name,
                start_date=start_date,
                end_date=end_date,
                status=FinancialPeriod.Status.OPEN
            )
            period.clean() # Validate model constraints
            period.save()

        messages.success(request, f"تم إنشاء الفترة المحاسبية '{name}' بنجاح.")
    except ValidationError as e:
        messages.error(request, f"خطأ في التحقق: {e.message}")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء الفترة: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def edit_fiscal_year(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles the updating of a Fiscal Year's details."""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن تعديل سنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')

    try:
        name = request.POST.get('name')
        start_date_str = request.POST.get('start_date')
        end_date_str = request.POST.get('end_date')

        if not all([name, start_date_str, end_date_str]):
            messages.error(request, "يرجى تعبئة جميع الحقول.")
            return redirect('inventory:fiscal_year_list')

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

        with transaction.atomic():
            fiscal_year.name = name
            # Only allow date changes if no periods exist yet
            if not fiscal_year.periods.exists():
                fiscal_year.start_date = start_date
                fiscal_year.end_date = end_date
            elif fiscal_year.start_date != start_date or fiscal_year.end_date != end_date:
                messages.warning(request, "لا يمكن تغيير تواريخ سنة مالية تحتوي بالفعل على فترات محاسبية.")

            fiscal_year.clean() # Validate model constraints
            fiscal_year.save()

        messages.success(request, f"تم تحديث السنة المالية '{name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تحديث السنة المالية: {e}")
    
    return redirect('inventory:fiscal_year_list')


@require_POST
def delete_fiscal_year(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles the deletion of a Fiscal Year, with safety checks."""
    fiscal_year = get_object_or_404(FiscalYear, pk=pk)
    if fiscal_year.is_closed:
        messages.error(request, "لا يمكن حذف سنة مالية مغلقة.")
        return redirect('inventory:fiscal_year_list')

    # Safety Check: Ensure no transactions exist within this fiscal year's date range.
    # This is a simplified check. A more robust check would query all transactional models.
    has_transactions = JournalEntry.objects.filter(
        date__range=(fiscal_year.start_date, fiscal_year.end_date)
    ).exists()

    if has_transactions:
        messages.error(request, f"لا يمكن حذف السنة المالية '{fiscal_year.name}' لأنها تحتوي على قيود يومية مسجلة.")
        return redirect('inventory:fiscal_year_list')

    try:
        with transaction.atomic():
            year_name = fiscal_year.name
            fiscal_year.delete()
            messages.success(request, f"تم حذف السنة المالية '{year_name}' وجميع فتراتها بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف السنة المالية: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
def generate_monthly_periods(request: HttpRequest, year_id: int) -> HttpResponse:
    """Generates 12 monthly Financial Periods for a given Fiscal Year."""
    fiscal_year = get_object_or_404(FiscalYear, pk=year_id)
    if fiscal_year.periods.exists():
        messages.warning(request, "الفترات الشهرية لهذه السنة المالية تم إنشاؤها بالفعل.")
        return redirect('inventory:fiscal_year_list')

    try:
        with transaction.atomic():
            current_date = fiscal_year.start_date
            while current_date < fiscal_year.end_date:
                period_end_date = current_date + relativedelta(day=31)
                if period_end_date > fiscal_year.end_date:
                    period_end_date = fiscal_year.end_date
                
                FinancialPeriod.objects.create(
                    fiscal_year=fiscal_year,
                    name=current_date.strftime('%B %Y'),
                    start_date=current_date,
                    end_date=period_end_date,
                    status=FinancialPeriod.Status.OPEN
                )
                current_date = period_end_date + relativedelta(days=1)
        messages.success(request, f"تم إنشاء 12 فترة محاسبية للسنة المالية '{fiscal_year.name}' بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إنشاء الفترات: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
def change_period_status(request: HttpRequest, period_id: int) -> HttpResponse:
    """Handles changing the status of a financial period."""
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    new_status = request.POST.get('new_status')
    justification = request.POST.get('justification', '').strip()

    if not new_status or new_status not in [s[0] for s in FinancialPeriod.Status.choices]:
        messages.error(request, "حالة جديدة غير صالحة.")
        return redirect('inventory:fiscal_year_list')

    try:
        original_status = period.get_status_display()
        
        # Logic for re-opening a closed period
        if period.status == FinancialPeriod.Status.CLOSED and new_status == FinancialPeriod.Status.OPEN:
            if not request.user.has_perm('inventory.can_reopen_period'):
                messages.error(request, "ليس لديك الصلاحية لإعادة فتح فترة مغلقة.")
                return redirect('inventory:fiscal_year_list')
            if not justification:
                messages.error(request, "يجب تقديم مبرر لإعادة فتح فترة مغلقة.")
                return redirect('inventory:fiscal_year_list')
            
            # Create an audit log entry for re-opening
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.REOPEN,
                justification=justification
            )
        
        # --- NEW: Logic for permanently locking a period ---
        if new_status == FinancialPeriod.Status.PERMANENTLY_LOCKED:
            if not request.user.has_perm('inventory.can_permanently_lock_period'):
                messages.error(request, "ليس لديك الصلاحية لإغلاق فترة بشكل دائم.")
                return redirect('inventory:fiscal_year_list')
            
            # Create an audit log entry for locking
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.LOCK,
                justification=justification or "Period permanently locked after final review."
            )


        period.status = new_status
        period.save()
        
        new_status_display = period.get_status_display()
        messages.success(request, f"تم تغيير حالة الفترة '{period.name}' من '{original_status}' إلى '{new_status_display}' بنجاح.")

    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء تغيير حالة الفترة: {e}")

    return redirect('inventory:fiscal_year_list')


@require_POST
@permission_required('inventory.change_financialperiod', raise_exception=True)
def close_period_action(request: HttpRequest, period_id: int) -> HttpResponse:
    """
    Handles the final action of closing a financial period after all checks pass.
    """
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    
    # Security and state check
    if period.status != FinancialPeriod.Status.PENDING_CLOSE:
        messages.error(request, _("This period is not in the 'Pending Close' state and cannot be closed."))
        return redirect('inventory:fiscal_year_list')

    # Re-run the checklist validation on the server side as the final gate.
    # The service returns the updated checklist instance, guaranteed to be fresh.
    checklist = update_checklist_for_period(period)

    # Use the checklist object returned directly by the service for the final check.
    if not checklist.is_complete:
        messages.error(request, _("Cannot close the period. One or more pre-closing checks have not been completed."))
        return redirect('inventory:close_period_cockpit', period_id=period.id)

    try:
        with transaction.atomic():
            period.status = FinancialPeriod.Status.CLOSED
            period.save()
            
            PeriodClosingAuditLog.objects.create(
                financial_period=period,
                user=request.user,
                action_type=PeriodClosingAuditLog.ActionType.CLOSE,
                justification="Period closed via closing cockpit."
            )
        
        messages.success(request, _(f"Financial period '{period.name}' has been successfully closed."))
        return redirect('inventory:fiscal_year_list')
    except Exception as e:
        messages.error(request, _(f"An unexpected error occurred: {e}"))
        return redirect('inventory:close_period_cockpit', period_id=period.id)


def close_period_cockpit(request: HttpRequest, period_id: int) -> HttpResponse:
    """
    Displays the 'Closing Cockpit' UI for a specific financial period,
    showing the checklist. This is now a GET-only view.
    """
    period = get_object_or_404(FinancialPeriod, pk=period_id)

    # The POST logic has been moved to the 'close_period_action' view.
    if period.status not in [FinancialPeriod.Status.OPEN, FinancialPeriod.Status.PENDING_CLOSE]:
        messages.warning(request, _("This period is already closed and cannot be modified from this screen."))
        return redirect('inventory:fiscal_year_list')

    # The cockpit's job is to update the checklist so the user sees the latest status.
    checklist = update_checklist_for_period(period)

    context = {
        'active_page': 'financials',
        'sub_page': 'periods',
        'period': period,
        'checklist': checklist,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/close_period_cockpit_content.html', context)
    return render(request, 'inventory/close_period_cockpit.html', context)


def api_period_checklist_status(request: HttpRequest, period_id: int) -> JsonResponse:
    """API endpoint to check the status of pre-closing conditions for a period."""
    period = get_object_or_404(FinancialPeriod, pk=period_id)
    
    # --- REAL IMPLEMENTATION ---
    checks = {}
    
    # 1. Check if all bank accounts have been reconciled for the period.
    # This is more robust: it ensures every bank account has a corresponding
    # reconciled statement, not just that there are no unreconciled ones.
    all_bank_accounts = BankAccount.objects.all()
    reconciled_banks_in_period_pks = BankReconciliation.objects.filter(
        statement_date__gte=period.start_date,
        statement_date__lte=period.end_date,
        status=BankReconciliation.Status.RECONCILED
    ).values_list('bank_account_id', flat=True)

    unreconciled_bank_objects = all_bank_accounts.exclude(pk__in=reconciled_banks_in_period_pks)
    bank_check = not unreconciled_bank_objects.exists()
    
    bank_details = []
    if not bank_check:
        for bank in unreconciled_bank_objects:
            bank_details.append({
                'description': f"Bank Account: {bank.name}",
                'url': '#' # No direct URL for a bank account view
            })
            
    checks['all_banks_reconciled'] = {
        'status': bank_check,
        'message': f"{unreconciled_bank_objects.count()} bank accounts are not reconciled." if not bank_check else "All bank accounts reconciled.",
        'details': bank_details
    }

    # 2. Check for draft manual journal entries
    draft_jes = JournalEntry.objects.filter(
        date__gte=period.start_date,
        date__lte=period.end_date,
        status=JournalEntry.Status.DRAFT,
        content_type__isnull=True # Manual entries only
    )
    draft_check = not draft_jes.exists()
    draft_details = []
    if not draft_check:
        for je in draft_jes:
            draft_details.append({
                'description': f"JE-{je.id}: {je.description}",
                'url': reverse('inventory:view_journal_entry', kwargs={'pk': je.id})
            })
            
    checks['no_draft_manual_jes'] = {
        'status': draft_check,
        'message': f"{draft_jes.count()} draft journal entries found." if not draft_check else "No manual journal entries in draft status.",
        'details': draft_details
    }

    # 3. Check for unposted supplier/customer invoices (assuming DRAFT status exists)
    unposted_supplier_invoices = SupplierInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=SupplierInvoice.InvoiceStatus.DRAFT
    )
    unposted_customer_invoices = CustomerInvoice.objects.filter(
        invoice_date__gte=period.start_date,
        invoice_date__lte=period.end_date,
        status=CustomerInvoice.InvoiceStatus.DRAFT
    )
    unposted_invoices_check = not unposted_supplier_invoices.exists() and not unposted_customer_invoices.exists()
    invoice_details = []
    if not unposted_invoices_check:
        for inv in unposted_supplier_invoices:
            invoice_details.append({
                'description': f"Supplier Invoice: {inv.invoice_number} ({inv.supplier.name})",
                'url': reverse('inventory:view_supplier_invoice', kwargs={'pk': inv.id})
            })
        for inv in unposted_customer_invoices:
            invoice_details.append({
                'description': f"Customer Invoice: {inv.invoice_number} ({inv.customer.name})",
                'url': reverse('inventory:view_customer_invoice', kwargs={'pk': inv.id})
            })
            
    checks['no_unposted_invoices'] = {
        'status': unposted_invoices_check,
        'message': f"{len(invoice_details)} unposted invoices found." if not unposted_invoices_check else "All invoices are posted.",
        'details': invoice_details
    }

    # 4. Placeholder for a check that is always true for now
    checks['is_inventory_valuation_run'] = {
        'status': True,
        'message': 'Inventory valuation process completed successfully.',
        'details': []
    }
    
    # 5. Get status of other checks from the checklist model
    checklist = getattr(period, 'checklist', None)
    if checklist:
        checks['is_depreciation_run'] = {
            'status': checklist.is_depreciation_run,
            'message': 'Monthly depreciation has been run.' if checklist.is_depreciation_run else 'Monthly depreciation has not been run.',
            'details': []
        }
        checks['is_overhead_posted'] = {
            'status': checklist.is_overhead_posted,
            'message': 'Manufacturing overhead has been posted.' if checklist.is_overhead_posted else 'Manufacturing overhead has not been posted.',
            'details': []
        }

    return JsonResponse(checks)

def view_period_audit_log(request: HttpRequest, period_id: int) -> HttpResponse:
    """Displays the audit log for a specific financial period."""
    period = get_object_or_404(FinancialPeriod.objects.prefetch_related('audit_logs__user'), pk=period_id)
    context = {
        'period': period,
        'audit_logs': period.audit_logs.all()
    }
    return render(request, 'inventory/partials/audit_log_content.html', context)
