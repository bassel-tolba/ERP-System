# gipcco_project/inventory/views/financials/banking_views.py

from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import F, Q, Sum, Value, DecimalField
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.contrib.contenttypes.models import ContentType

from ...models import (
    Payment, BankAccount, BankTransfer, BankReconciliation, BankStatementLine, Account, JournalEntry, JournalEntryLine
)

def bank_accounts_dashboard(request: HttpRequest) -> HttpResponse:
    """Displays a list of bank accounts, their balances, and recent transactions."""
    if request.method == 'POST': # Handle Transfer creation
        source_id = request.POST.get('source_account')
        dest_id = request.POST.get('destination_account')
        amount = request.POST.get('amount')
        date_str = request.POST.get('transfer_date')
        description = request.POST.get('description')
        
        try:
            transfer = BankTransfer(
                source_account_id=source_id,
                destination_account_id=dest_id,
                amount=Decimal(amount),
                transfer_date=datetime.strptime(date_str, '%Y-%m-%d').date(),
                description=description or f"Transfer from {BankAccount.objects.get(pk=source_id).name}"
            )
            transfer.clean() # Manually call clean to validate
            transfer.save()
            messages.success(request, "تم تسجيل التحويل البنكي بنجاح.")
        except Exception as e:
            messages.error(request, f"حدث خطأ أثناء تسجيل التحويل: {e}")
        return redirect('inventory:bank_accounts_dashboard')
    
    # Calculate balances for all bank accounts
    bank_accounts = BankAccount.objects.annotate(
        total_debits=Coalesce(Sum('gl_account__journal_lines__amount', filter=Q(gl_account__journal_lines__entry_type='debit')), Value(0), output_field=DecimalField()),
        total_credits=Coalesce(Sum('gl_account__journal_lines__amount', filter=Q(gl_account__journal_lines__entry_type='credit')), Value(0), output_field=DecimalField())
    ).annotate(
        balance=F('total_debits') - F('total_credits')
    )

    transfers = BankTransfer.objects.select_related('source_account', 'destination_account').all()[:20]

    context = {
        'active_page': 'financials',
        'sub_page': 'banking',
        'bank_accounts': bank_accounts,
        'transfers': transfers,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/banking_dashboard_content.html', context)
    return render(request, 'inventory/banking_dashboard.html', context)


@require_POST
def create_bank_account(request: HttpRequest) -> HttpResponse:
    """Handles creation of a new bank account."""
    try:
        name = request.POST.get('name', '').strip()
        gl_account_id = request.POST.get('gl_account')
        if not name or not gl_account_id:
            raise ValueError("Name and GL Account are required.")
        BankAccount.objects.create(name=name, gl_account_id=gl_account_id)
        messages.success(request, f"Bank account '{name}' created successfully.")
    except Exception as e:
        messages.error(request, f"Error creating bank account: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def edit_bank_account(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing an existing bank account."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        name = request.POST.get('name', '').strip()
        gl_account_id = request.POST.get('gl_account')
        if not name or not gl_account_id:
            raise ValueError("Name and GL Account are required.")
        account.name = name
        account.gl_account_id = gl_account_id
        account.save()
        messages.success(request, f"Bank account '{name}' updated successfully.")
    except Exception as e:
        messages.error(request, f"Error updating bank account: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def delete_bank_account(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a bank account."""
    account = get_object_or_404(BankAccount, pk=pk)
    try:
        account_name = account.name
        account.delete()
        messages.success(request, f"Bank account '{account_name}' deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting bank account: {e}. It might be in use.")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def create_payment(request: HttpRequest) -> HttpResponse:
    """Handles creation of a standalone payment."""
    try:
        bank_account_id = request.POST.get('bank_account')
        payment_date_str = request.POST.get('payment_date')
        amount_str = request.POST.get('amount')
        payment_type = request.POST.get('payment_type')
        description = request.POST.get('description', '').strip()
        supplier_id = request.POST.get('supplier') or None
        customer_id = request.POST.get('customer') or None

        if not all([bank_account_id, payment_date_str, amount_str, payment_type, description]):
            raise ValueError("Please fill all required fields.")

        Payment.objects.create(
            bank_account_id=bank_account_id,
            payment_date=datetime.strptime(payment_date_str, '%Y-%m-%d').date(),
            amount=Decimal(amount_str),
            payment_type=payment_type,
            description=description,
            supplier_id=supplier_id,
            customer_id=customer_id
        )
        messages.success(request, "Payment created successfully.")
    except Exception as e:
        messages.error(request, f"Error creating payment: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def edit_payment(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles editing a standalone payment."""
    payment = get_object_or_404(Payment, pk=pk)
    try:
        bank_account_id = request.POST.get('bank_account')
        payment_date_str = request.POST.get('payment_date')
        amount_str = request.POST.get('amount')
        payment_type = request.POST.get('payment_type')
        description = request.POST.get('description', '').strip()
        supplier_id = request.POST.get('supplier') or None
        customer_id = request.POST.get('customer') or None

        if not all([bank_account_id, payment_date_str, amount_str, payment_type, description]):
            raise ValueError("Please fill all required fields.")

        payment.bank_account_id = bank_account_id
        payment.payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
        payment.amount = Decimal(amount_str)
        payment.payment_type = payment_type
        payment.description = description
        payment.supplier_id = supplier_id
        payment.customer_id = customer_id
        payment.save()
        messages.success(request, "Payment updated successfully.")
    except Exception as e:
        messages.error(request, f"Error updating payment: {e}")
    return redirect('inventory:bank_accounts_dashboard')

@require_POST
def delete_payment(request: HttpRequest, pk: int) -> HttpResponse:
    """Handles deleting a standalone payment."""
    payment = get_object_or_404(Payment, pk=pk)
    try:
        payment.delete()
        messages.success(request, "Payment deleted successfully.")
    except Exception as e:
        messages.error(request, f"Error deleting payment: {e}. It might be in use.")
    return redirect('inventory:bank_accounts_dashboard')


# ==============================================================================
#  BANK RECONCILIATION VIEWS
# ==============================================================================

def bank_reconciliations_list(request: HttpRequest) -> HttpResponse:
    """Lists all bank reconciliations with filtering."""
    bank_account_id = request.GET.get('bank_account')
    status = request.GET.get('status')
    
    reconciliations = BankReconciliation.objects.select_related('bank_account').all()
    if bank_account_id:
        reconciliations = reconciliations.filter(bank_account_id=bank_account_id)
    if status:
        reconciliations = reconciliations.filter(status=status)

    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'reconciliations': reconciliations,
        'bank_accounts': BankAccount.objects.all(),
        'statuses': BankReconciliation.Status.choices,
        'selected_bank_account': int(bank_account_id) if bank_account_id else None,
        'selected_status': status,
    }
    # For HTMX/partial requests
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_list_content.html', context)
    return render(request, 'inventory/reconciliation_list.html', context)


def create_bank_reconciliation(request: HttpRequest) -> HttpResponse:
    """Handles the creation of a new bank reconciliation period."""
    if request.method == 'POST':
        try:
            bank_account_id = request.POST.get('bank_account')
            statement_date_str = request.POST.get('statement_date')
            opening_balance_str = request.POST.get('statement_opening_balance')
            closing_balance_str = request.POST.get('statement_closing_balance')

            if not all([bank_account_id, statement_date_str, opening_balance_str, closing_balance_str]):
                messages.error(request, "يرجى تعبئة جميع الحقول.")
                return redirect('inventory:create_bank_reconciliation')

            statement_date = datetime.strptime(statement_date_str, '%Y-%m-%d').date()
            
            # --- ADDED VALIDATION ---
            if BankReconciliation.objects.filter(bank_account_id=bank_account_id, statement_date=statement_date).exists():
                messages.error(request, f"فترة تسوية لهذا الحساب في تاريخ {statement_date_str} موجودة بالفعل.")
                return redirect('inventory:create_bank_reconciliation')

            reconciliation = BankReconciliation.objects.create(
                bank_account_id=bank_account_id,
                statement_date=statement_date,
                statement_opening_balance=Decimal(opening_balance_str),
                statement_closing_balance=Decimal(closing_balance_str)
            )
            messages.success(request, "تم إنشاء فترة التسوية البنكية بنجاح.")
            return redirect('inventory:manage_bank_reconciliation', pk=reconciliation.pk)
        except Exception as e:
            messages.error(request, f"حدث خطأ: {e}")
            return redirect('inventory:create_bank_reconciliation')

    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'bank_accounts': BankAccount.objects.all(),
        'today_date': timezone.now().strftime('%Y-%m-%d'),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_create_content.html', context)
    return render(request, 'inventory/reconciliation_create.html', context)


def manage_bank_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """
    Displays the main reconciliation workspace for matching transactions.
    Also handles manual entry of statement lines.
    """
    reconciliation = get_object_or_404(BankReconciliation.objects.select_related('bank_account'), pk=pk)
    bank_account = reconciliation.bank_account

    if request.method == 'POST': # Handle manual line entry
        try:
            # Simple validation for manual entry
            line_date_str = request.POST.get('transaction_date')
            description = request.POST.get('description', '').strip()
            amount_str = request.POST.get('amount')
            
            if not all([line_date_str, description, amount_str]):
                raise ValueError("يرجى تعبئة جميع حقول السطر.")

            reconciliation.statement_lines.create(
                transaction_date=datetime.strptime(line_date_str, '%Y-%m-%d').date(),
                description=description,
                amount=Decimal(amount_str)
            )
            messages.success(request, "تم إضافة سطر كشف الحساب بنجاح.")
        except Exception as e:
            messages.error(request, f"خطأ في إضافة السطر: {e}")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)


    # --- Reconciliation Summary Calculations ---
    statement_lines = reconciliation.statement_lines.all()
    cleared_balance = reconciliation.statement_opening_balance + \
                      (statement_lines.filter(is_reconciled=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.0'))
    difference = reconciliation.statement_closing_balance - cleared_balance
    
    # --- Fetch Unreconciled Internal Transactions ---
    # Payments (in and out) for this bank account that are not yet cleared
    unreconciled_payments = Payment.objects.filter(
        bank_account=bank_account,
        reconciliation__isnull=True,
        cleared_date__isnull=True,
        payment_date__lte=reconciliation.statement_date
    ).order_by('payment_date')

    # Bank Transfers related to this account (both as source and destination)
    unreconciled_source_transfers = BankTransfer.objects.filter(
        source_account=bank_account,
        source_reconciliation__isnull=True,
        source_cleared_date__isnull=True,
        transfer_date__lte=reconciliation.statement_date
    )
    unreconciled_dest_transfers = BankTransfer.objects.filter(
        destination_account=bank_account,
        destination_reconciliation__isnull=True,
        destination_cleared_date__isnull=True,
        transfer_date__lte=reconciliation.statement_date
    )
    
    # Combine and sort all internal transactions
    internal_transactions = []
    for p in unreconciled_payments:
        amount = p.amount if p.payment_type == Payment.PaymentType.PAYMENT_IN else -p.amount
        internal_transactions.append({'obj': p, 'date': p.payment_date, 'amount': amount, 'type': 'Payment'})
    for t in unreconciled_source_transfers:
        internal_transactions.append({'obj': t, 'date': t.transfer_date, 'amount': -t.amount, 'type': 'Transfer'})
    for t in unreconciled_dest_transfers:
        internal_transactions.append({'obj': t, 'date': t.transfer_date, 'amount': t.amount, 'type': 'Transfer'})

    # Sort internal transactions by date, then by type (Payments first, then Transfers)
    internal_transactions.sort(key=lambda x: (x['date'], x['type'] == 'Transfer'))

    # --- Reconciliation View Context ---
    context = {
        'active_page': 'financials',
        'sub_page': 'reconciliation',
        'reconciliation': reconciliation,
        'unreconciled_statement_lines': statement_lines.filter(is_reconciled=False),
        'reconciled_statement_lines': statement_lines.filter(is_reconciled=True).select_related('reconciled_object_content_type'),
        'internal_transactions': internal_transactions,
        'bank_account': bank_account,
        'today_date': timezone.now().strftime('%Y-%m-%d'),
        'cleared_balance': cleared_balance,
        'difference': difference,
        'expense_accounts': list(Account.objects.filter(account_type=Account.AccountType.EXPENSE).order_by('code').values('id', 'name', 'code')),
        'income_accounts': list(Account.objects.filter(account_type=Account.AccountType.REVENUE).order_by('code').values('id', 'name', 'code')),
    }
    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/partials/reconciliation_manage_content.html', context)
    return render(request, 'inventory/reconciliation_manage.html', context)


@require_POST
def delete_bank_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """Deletes a bank reconciliation, but only if it is still open."""
    reconciliation = get_object_or_404(BankReconciliation, pk=pk)

    if reconciliation.status != BankReconciliation.Status.OPEN:
        messages.error(request, "لا يمكن حذف تسوية مغلقة.")
        return redirect('inventory:bank_reconciliations_list')

    try:
        with transaction.atomic():
            # Unmatch any linked transactions before deleting
            reconciliation.unmatch_all_transactions()
            reconciliation.delete()
            messages.success(request, "تم حذف فترة التسوية البنكية بنجاح.")
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء حذف التسوية: {e}")

    return redirect('inventory:bank_reconciliations_list')


# --- API Views for Reconciliation Matching ---

@require_POST
def api_unmatch_transaction(request: HttpRequest, pk: int) -> HttpResponse:
    """API endpoint to unmatch a previously reconciled transaction."""
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        
        if not line_id:
            raise ValueError("Missing line_id for unmatching.")

        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if not line.is_reconciled:
            raise ValueError("This statement line is not currently reconciled.")

        with transaction.atomic():
            internal_trx = line.reconciled_object
            if internal_trx:
                # Reset the internal transaction
                if isinstance(internal_trx, Payment):
                    internal_trx.reconciliation = None
                    internal_trx.cleared_date = None
                    internal_trx.save()
                elif isinstance(internal_trx, BankTransfer):
                    if internal_trx.source_reconciliation == reconciliation:
                        internal_trx.source_reconciliation = None
                        internal_trx.source_cleared_date = None
                    elif internal_trx.destination_reconciliation == reconciliation:
                        internal_trx.destination_reconciliation = None
                        internal_trx.destination_cleared_date = None
                    internal_trx.save()
            
            # Reset the statement line
            line.is_reconciled = False
            line.reconciled_object = None
            line.save()
        
        messages.success(request, "تم إلغاء مطابقة المعاملة بنجاح.")
    except Exception as e:
        messages.error(request, f"خطأ في إلغاء المطابقة: {e}")

    return redirect('inventory:manage_bank_reconciliation', pk=pk)


@require_POST
def api_create_adjustment_and_match(request: HttpRequest, pk: int) -> JsonResponse:
    """
    Creates a new journal entry for a bank adjustment (e.g., fee, interest)
    and matches it to a statement line.
    """
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        account_id = request.POST.get('account_id')
        description = request.POST.get('description', '').strip()

        if not all([line_id, account_id, description]):
            raise ValueError("Missing data for adjustment (line_id, account_id, description).")

        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if line.is_reconciled:
            raise ValueError("This statement line is already reconciled.")

        adjustment_account = get_object_or_404(Account, pk=account_id)
        bank_gl_account = reconciliation.bank_account.gl_account
        amount = abs(line.amount)

        with transaction.atomic():
            # 1. Create the Journal Entry for the adjustment
            je = JournalEntry.objects.create(
                date=line.transaction_date,
                description=description,
                # We can link it to the reconciliation for traceability
                source_object=reconciliation
            )

            # 2. Create the debit and credit lines
            if line.amount < 0: # It's a fee/expense
                # Debit the expense account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=adjustment_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.DEBIT
                )
                # Credit the bank account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=bank_gl_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )
            else: # It's interest/income
                # Debit the bank account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=bank_gl_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.DEBIT
                )
                # Credit the income account
                JournalEntryLine.objects.create(
                    journal_entry=je, account=adjustment_account, amount=amount,
                    entry_type=JournalEntryLine.EntryType.CREDIT
                )

            # 3. Link the statement line to the new Journal Entry
            line.is_reconciled = True
            line.reconciled_object = je
            line.save()

        return JsonResponse({'status': 'success', 'message': 'Adjustment created and matched successfully.'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def api_match_transactions(request: HttpRequest, pk: int) -> JsonResponse:
    """API endpoint to match a statement line with an internal transaction."""
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)
    try:
        reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
        line_id = request.POST.get('line_id')
        trx_id = request.POST.get('trx_id')
        trx_type = request.POST.get('trx_type') # 'Payment' or 'Transfer'

        if not all([line_id, trx_id, trx_type]):
            raise ValueError("Missing data for matching (line_id, trx_id, trx_type).")

        # Find the statement line
        line = get_object_or_404(reconciliation.statement_lines.all(), pk=line_id)
        if line.is_reconciled:
            raise ValueError("This statement line is already reconciled.")

        with transaction.atomic():
            target_model = None
            if trx_type == 'Payment':
                target_model = Payment
            elif trx_type == 'Transfer':
                target_model = BankTransfer
            else:
                raise ValueError(f"Invalid transaction type: {trx_type}")

            internal_trx = get_object_or_404(target_model, pk=trx_id)

            # Basic validation: Amounts must match
            line_amount = line.amount
            trx_amount = Decimal('0.0')
            if trx_type == 'Payment':
                trx_amount = internal_trx.amount if internal_trx.payment_type == Payment.PaymentType.PAYMENT_IN else -internal_trx.amount
            elif trx_type == 'Transfer':
                # Determine if it's a debit or credit for the account being reconciled
                if internal_trx.destination_account_id == reconciliation.bank_account_id:
                    trx_amount = internal_trx.amount
                else:
                    trx_amount = -internal_trx.amount
            
            if abs(line_amount - trx_amount) > Decimal('0.001'):
                 raise ValueError(f"Amounts do not match. Line: {line_amount}, Transaction: {trx_amount}")

            # Link them
            line.is_reconciled = True
            line.reconciled_object = internal_trx
            line.save()

            # Mark the internal transaction as cleared
            cleared_date = line.transaction_date
            if trx_type == 'Payment':
                internal_trx.reconciliation = reconciliation
                internal_trx.cleared_date = cleared_date
                internal_trx.save()
            elif trx_type == 'Transfer':
                if internal_trx.destination_account_id == reconciliation.bank_account_id:
                    internal_trx.destination_reconciliation = reconciliation
                    internal_trx.destination_cleared_date = cleared_date
                else:
                    internal_trx.source_reconciliation = reconciliation
                    internal_trx.source_cleared_date = cleared_date
                internal_trx.save()

        return JsonResponse({'status': 'success', 'message': 'Transaction matched successfully.'})
                
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
def finalize_reconciliation(request: HttpRequest, pk: int) -> HttpResponse:
    """Marks a reconciliation as complete if the difference is zero."""
    reconciliation = get_object_or_404(BankReconciliation, pk=pk, status=BankReconciliation.Status.OPEN)
    
    # Recalculate the difference to ensure it's zero before finalizing
    cleared_balance = reconciliation.statement_opening_balance + \
                      (reconciliation.statement_lines.filter(is_reconciled=True).aggregate(s=Sum('amount'))['s'] or Decimal('0.0'))
    difference = reconciliation.statement_closing_balance - cleared_balance

    if abs(difference) > Decimal('0.001'): # Use a small tolerance
        messages.error(request, "لا يمكن إتمام التسوية. لا يزال هناك فرق بين الرصيد المسوى والرصيد الدفتري.")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)

    try:
        with transaction.atomic():
            reconciliation.status = BankReconciliation.Status.RECONCILED
            reconciliation.save()
            messages.success(request, "تم إتمام التسوية البنكية بنجاح.")
            
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء إتمام التسوية: {e}")
        return redirect('inventory:manage_bank_reconciliation', pk=pk)

    return redirect('inventory:bank_reconciliations_list')
