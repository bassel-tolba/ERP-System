# gipcco_project/inventory/views/financials/gl_views.py

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import permission_required

from ...models import (
    JournalEntry, JournalEntryLine, FixedAsset, DepreciationLog
)
from ...forms import JournalEntryForm, JournalEntryLineFormSet

def journal_entries(request: HttpRequest) -> HttpResponse:
    """Lists manually created journal entries and provides a link to create new ones."""
    # MODIFIED: Prefetch lines and accounts for efficient display in the new accordion view.
    manual_entries = JournalEntry.objects.filter(
        content_type__isnull=True
    ).prefetch_related(
        'lines__account'
    ).annotate(
        total_amount=Sum('lines__amount', filter=Q(lines__entry_type='debit'))
    ).order_by('-date')
    
    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'journal_entries': manual_entries
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entries_content.html', context)
    return render(request, 'inventory/journal_entries.html', context)


@require_POST
@permission_required('inventory.change_journalentry', raise_exception=True)
def post_journal_entry(request: HttpRequest, pk: int) -> HttpResponse:
    """Posts a single draft journal entry."""
    entry = get_object_or_404(JournalEntry, pk=pk, status=JournalEntry.Status.DRAFT)
    try:
        entry.status = JournalEntry.Status.POSTED
        entry.save(update_fields=['status'])
        messages.success(request, f"تم ترحيل قيد اليومية رقم {entry.id} بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء ترحيل القيد: {e}")
    return redirect('inventory:journal_entries')


def create_journal_entry(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new journal entry using formsets."""
    if request.method == 'POST':
        form = JournalEntryForm(request.POST)
        formset = JournalEntryLineFormSet(request.POST, prefix='lines')
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    journal_entry = form.save(commit=False)
                    # Manually created entries are drafts until posted.
                    journal_entry.status = JournalEntry.Status.DRAFT
                    journal_entry.save()
                    formset.instance = journal_entry
                    formset.save()
                    messages.success(request, "تم حفظ مسودة قيد اليومية بنجاح.")
                    return redirect('inventory:journal_entries')
            except Exception as e:
                messages.error(request, f"حدث خطأ: {e}")
    else:
        form = JournalEntryForm()
        formset = JournalEntryLineFormSet(prefix='lines', queryset=JournalEntryLine.objects.none())

    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'form': form,
        'formset': formset,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entry_create_content.html', context)
    return render(request, 'inventory/journal_entry_create.html', context)


def view_journal_entry(request: HttpRequest, pk: int) -> HttpResponse:
    """Displays the details of a single journal entry."""
    entry = get_object_or_404(
        JournalEntry.objects.select_related('content_type').prefetch_related('lines__account', 'lines__sub_ledger_object'), 
        pk=pk
    )
    
    context = {
        'active_page': 'financials',
        'sub_page': 'journal_entries',
        'entry': entry,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/journal_entry_view_content.html', context)
    return render(request, 'inventory/journal_entry_view.html', context)


def fixed_assets_dashboard(request: HttpRequest) -> HttpResponse:
    """Displays a list of fixed assets and their depreciation status."""
    assets = FixedAsset.objects.all()
    logs = DepreciationLog.objects.select_related('asset', 'journal_entry').all()[:20]

    context = {
        'active_page': 'financials',
        'sub_page': 'assets',
        'assets': assets,
        'depreciation_logs': logs,
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/fixed_assets_dashboard_content.html', context)
    return render(request, 'inventory/fixed_assets_dashboard.html', context)
