# gipcco_project/inventory/views/financial_reports.py

import json
from datetime import datetime, time
from decimal import Decimal
from functools import lru_cache

from django.db.models import Sum, Q, F
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from ..models import Account, JournalEntryLine, JournalEntry, FinancialPeriod, Batch, Product, FinishedProductDispatch, InventoryConsumption, ProductionReturn, BatchItem, InventoryLog, GeneralAccountingSettings, BankAccount, Payment, BankTransfer, BankReconciliation
from ..services.costing_service import get_inventory_state_at_datetime

# ==============================================================================
#  HELPER FUNCTIONS
# ==============================================================================

def _get_date_range_from_request(request: HttpRequest):
    """
    Parses start_date and end_date from GET parameters, providing sensible defaults.
    """
    try:
        # Try to get the active financial period as the default range
        active_period = FinancialPeriod.objects.filter(is_closed=False).order_by('-start_date').first()
        if active_period:
            default_start_date = active_period.start_date
            default_end_date = active_period.end_date
        else:
            # Fallback if no periods are defined
            today = timezone.now().date()
            default_start_date = today.replace(day=1)
            default_end_date = today
    except Exception:
        today = timezone.now().date()
        default_start_date = today.replace(day=1)
        default_end_date = today

    start_date_str = request.GET.get('start_date', default_start_date.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', default_end_date.strftime('%Y-%m-%d'))
    
    start_date = timezone.make_aware(datetime.strptime(start_date_str, '%Y-%m-%d'))
    end_date = timezone.make_aware(datetime.combine(
        datetime.strptime(end_date_str, '%Y-%m-%d').date(),
        time.max
    ))
    
    return start_date, end_date, start_date_str, end_date_str



def _get_account_tree_with_balances(root_account_type: str, start_date, end_date, include_opening_balance=False):
    """
    A recursive function to build a hierarchical tree of accounts with their balances.
    - Caches results for performance within a single request.
    - Can optionally include opening balances for reports like the Balance Sheet.
    """
    @lru_cache(maxsize=None)
    def get_all_balances():
        """
        Fetches all debit and credit totals for all accounts in one query.
        This is heavily cached to prevent redundant DB hits.
        """
        accounts_data = {}
        
        # 1. Opening Balances (before the start_date)
        if include_opening_balance:
            opening_balances_qs = Account.objects.annotate(
                opening_debits=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='debit', journal_lines__journal_entry__date__lt=start_date)), Decimal('0.0')),
                opening_credits=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='credit', journal_lines__journal_entry__date__lt=start_date)), Decimal('0.0')),
            ).values('id', 'opening_debits', 'opening_credits')
            for item in opening_balances_qs:
                accounts_data[item['id']] = {
                    'opening_balance': item['opening_debits'] - item['opening_credits'],
                    'debits': Decimal('0.0'),
                    'credits': Decimal('0.0')
                }

        # 2. Period Movements (within the date range)
        period_movements_qs = Account.objects.annotate(
            period_debits=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='debit', journal_lines__journal_entry__date__range=(start_date, end_date))), Decimal('0.0')),
            period_credits=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='credit', journal_lines__journal_entry__date__range=(start_date, end_date))), Decimal('0.0')),
        ).values('id', 'period_debits', 'period_credits')

        for item in period_movements_qs:
            if item['id'] not in accounts_data:
                 accounts_data[item['id']] = {'opening_balance': Decimal('0.0')}
            accounts_data[item['id']]['debits'] = item['period_debits']
            accounts_data[item['id']]['credits'] = item['period_credits']
            
        return accounts_data

    all_balances = get_all_balances()

    def build_tree(parent_account=None):
        """Recursively builds the dictionary structure for the report."""
        if parent_account:
            children = Account.objects.filter(parent=parent_account).order_by('code')
        else:
            children = Account.objects.filter(parent__isnull=True, account_type=root_account_type).order_by('code')

        tree = []
        for account in children:
            balances = all_balances.get(account.id, {'opening_balance': Decimal('0.0'), 'debits': Decimal('0.0'), 'credits': Decimal('0.0')})
            
            node = {
                'account': account,
                'children': build_tree(account),
                'opening_balance': balances['opening_balance'],
                'debits': balances['debits'],
                'credits': balances['credits'],
                'total_debits': balances['debits'], # Start with own debits
                'total_credits': balances['credits'], # Start with own credits
            }
            
            # Sum up totals from children
            for child_node in node['children']:
                node['total_debits'] += child_node['total_debits']
                node['total_credits'] += child_node['total_credits']
                node['opening_balance'] += child_node['opening_balance'] # Opening balance also rolls up
            
            # Determine final balances for this node (including children)
            node['period_change'] = node['total_debits'] - node['total_credits']
            node['closing_balance'] = node['opening_balance'] + node['period_change']
            
            # Add final debit/credit balance fields for the template
            node['debit_balance'] = Decimal('0.0')
            node['credit_balance'] = Decimal('0.0')
            
            # For Trial Balance, we show the end-of-period balance for A/L/E accounts
            # and the period change for R/E accounts.
            if account.account_type in [Account.AccountType.ASSET, Account.AccountType.LIABILITY, Account.AccountType.EQUITY]:
                balance = node['closing_balance']
            else: # Revenue or Expense
                balance = node['period_change']

            # Assign to debit or credit column based on natural account type and balance sign
            if account.account_type in [Account.AccountType.ASSET, Account.AccountType.EXPENSE]:
                # Natural Debit accounts
                if balance > 0: node['debit_balance'] = balance
                else: node['credit_balance'] = -balance # Make positive
            else:
                # Natural Credit accounts (Liability, Equity, Revenue)
                # A credit balance means debits - credits is negative.
                if balance < 0: node['credit_balance'] = -balance # Make positive
                else: node['debit_balance'] = balance


            # Only include nodes with activity
            if node['closing_balance'] != 0 or node['debits'] != 0 or node['credits'] != 0:
                tree.append(node)
        
        return tree

    return build_tree()

# ==============================================================================
#  REPORT VIEWS
# ==============================================================================

def general_ledger(request: HttpRequest) -> HttpResponse:
    """
    Generates a General Ledger report for a specific account and date range.
    Shows the detailed, chronological list of all transactions affecting an account.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)
    account_id = request.GET.get('account_id')
    
    account = None
    account_tree = None

    if account_id:
        account = get_object_or_404(Account, pk=account_id)

        def _get_account_ledger_tree(current_account, level=0):
            """
            Recursively builds a hierarchical ledger for an account and its children.
            """
            # 1. Get direct transactions for the current account
            direct_lines = JournalEntryLine.objects.filter(
                account=current_account, journal_entry__date__range=(start_date, end_date)
            ).select_related('journal_entry').order_by('journal_entry__date', 'id')

            direct_transactions = []
            direct_debits = Decimal('0.0')
            direct_credits = Decimal('0.0')
            for line in direct_lines:
                debit = line.amount if line.entry_type == 'debit' else Decimal('0.0')
                credit = line.amount if line.entry_type == 'credit' else Decimal('0.0')
                direct_transactions.append({
                    'date': line.journal_entry.date,
                    'je_id': line.journal_entry.id,
                    'description': line.journal_entry.get_description(),
                    'debit': debit,
                    'credit': credit,
                })
                direct_debits += debit
                direct_credits += credit

            # 2. Recursively process children
            children_nodes = []
            children_total_opening = Decimal('0.0')
            children_total_debits = Decimal('0.0')
            children_total_credits = Decimal('0.0')
            
            for child in current_account.children.order_by('code'):
                child_node = _get_account_ledger_tree(child, level + 1)
                if child_node: # Only add children with activity
                    children_nodes.append(child_node)
                    children_total_opening += child_node['opening_balance']
                    children_total_debits += child_node['total_debits']
                    children_total_credits += child_node['total_credits']

            # 3. Calculate opening balance for the current account ONLY
            ob_debits = JournalEntryLine.objects.filter(
                account=current_account, entry_type='debit', journal_entry__date__lt=start_date
            ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
            ob_credits = JournalEntryLine.objects.filter(
                account=current_account, entry_type='credit', journal_entry__date__lt=start_date
            ).aggregate(total=Coalesce(Sum('amount'), Decimal('0.0')))['total']
            direct_opening_balance = ob_debits - ob_credits

            # 4. Aggregate totals for the current node
            total_opening_balance = direct_opening_balance + children_total_opening
            total_debits = direct_debits + children_total_debits
            total_credits = direct_credits + children_total_credits
            total_closing_balance = total_opening_balance + total_debits - total_credits

            # Only return a node if it or its children have any activity
            if not direct_transactions and not children_nodes and total_opening_balance == 0:
                return None

            return {
                'account': current_account,
                'level': level,
                'opening_balance': total_opening_balance,
                'total_debits': total_debits,
                'total_credits': total_credits,
                'closing_balance': total_closing_balance,
                'direct_transactions': direct_transactions,
                'children': children_nodes,
                'has_children_with_activity': any(c is not None for c in children_nodes)
            }

        account_tree = _get_account_ledger_tree(account)


    context = {
        'active_page': 'expenses_reports',
        'accounts': Account.objects.order_by('code'),
        'selected_account': account,
        'account_tree': account_tree,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    
    template_name = 'inventory/reports/general_ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/general_ledger_content.html'
        
    return render(request, template_name, context)


def trial_balance(request: HttpRequest) -> HttpResponse:
    """
    Generates a hierarchical Trial Balance report.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)
    
    # Build a tree for each root account type
    asset_tree = _get_account_tree_with_balances(Account.AccountType.ASSET, start_date, end_date, include_opening_balance=True)
    liability_tree = _get_account_tree_with_balances(Account.AccountType.LIABILITY, start_date, end_date, include_opening_balance=True)
    equity_tree = _get_account_tree_with_balances(Account.AccountType.EQUITY, start_date, end_date, include_opening_balance=True)
    revenue_tree = _get_account_tree_with_balances(Account.AccountType.REVENUE, start_date, end_date, include_opening_balance=True)
    expense_tree = _get_account_tree_with_balances(Account.AccountType.EXPENSE, start_date, end_date, include_opening_balance=True)
    
    # ====== START OF CORRECTION ======
    # Calculate grand totals by summing the pre-calculated debit/credit balances from the root nodes.
    # This is much simpler and guarantees that the totals match the displayed data.
    grand_total_debits = sum(node['debit_balance'] for node in asset_tree) + \
                         sum(node['debit_balance'] for node in liability_tree) + \
                         sum(node['debit_balance'] for node in equity_tree) + \
                         sum(node['debit_balance'] for node in revenue_tree) + \
                         sum(node['debit_balance'] for node in expense_tree)

    grand_total_credits = sum(node['credit_balance'] for node in asset_tree) + \
                          sum(node['credit_balance'] for node in liability_tree) + \
                          sum(node['credit_balance'] for node in equity_tree) + \
                          sum(node['credit_balance'] for node in revenue_tree) + \
                          sum(node['credit_balance'] for node in expense_tree)
    # ====== END OF CORRECTION ======

    is_balanced = abs(grand_total_debits - grand_total_credits) < Decimal('0.001')

    context = {
        'active_page': 'expenses_reports',
        'asset_tree': asset_tree,
        'liability_tree': liability_tree,
        'equity_tree': equity_tree,
        'revenue_tree': revenue_tree,
        'expense_tree': expense_tree,
        'grand_total_debits': grand_total_debits,
        'grand_total_credits': grand_total_credits,
        'is_balanced': is_balanced,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }

    template_name = 'inventory/reports/trial_balance.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/trial_balance_content.html'
        
    return render(request, template_name, context)


def profit_and_loss_statement(request: HttpRequest) -> HttpResponse:
    """
    Generates a hierarchical Profit & Loss (Income) Statement.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)

    revenue_tree = _get_account_tree_with_balances(Account.AccountType.REVENUE, start_date, end_date)
    expense_tree = _get_account_tree_with_balances(Account.AccountType.EXPENSE, start_date, end_date)
    
    # ====== START OF CORRECTION ======
    # Correctly calculate total revenue and expense as positive numbers.
    # Note: Revenue has a natural credit balance (credits > debits), so its period_change (debits-credits)
    # will be negative. We negate it here to get a positive total revenue.
    total_revenue = sum(-node['period_change'] for node in revenue_tree)
    # Expenses have a natural debit balance (debits > credits), so their period_change is already positive.
    total_expense = sum(node['period_change'] for node in expense_tree)

    net_profit = total_revenue - total_expense
    # ====== END OF CORRECTION ======

    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'revenue_tree': revenue_tree,
        'expense_tree': expense_tree,
        'total_revenue': total_revenue,
        'total_expense': total_expense,
        'net_profit': net_profit,
    }

    template_name = 'inventory/reports/profit_and_loss_statement.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/profit_and_loss_statement_content.html'
        
    return render(request, template_name, context)


def balance_sheet(request: HttpRequest) -> HttpResponse:
    """
    Generates a hierarchical Balance Sheet.
    This report shows the company's financial position at a single point in time.
    """
    end_date_str = request.GET.get('end_date', timezone.now().strftime('%Y-%m-%d'))
    end_date = timezone.make_aware(datetime.combine(
        datetime.strptime(end_date_str, '%Y-%m-%d').date(),
        time.max
    ))
    
    # For a balance sheet, the "period" is from the beginning of time up to the end_date.
    # So we set start_date to a very early date.
    start_of_time = timezone.make_aware(datetime(1900, 1, 1))

    # --- Calculate Net Profit for the period to include in Equity ---
    revenue_balance = Account.objects.filter(account_type=Account.AccountType.REVENUE).aggregate(
        balance=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='credit', journal_lines__journal_entry__date__lte=end_date)), Decimal('0.0')) -
                Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='debit', journal_lines__journal_entry__date__lte=end_date)), Decimal('0.0'))
    )['balance']
    
    expense_balance = Account.objects.filter(account_type=Account.AccountType.EXPENSE).aggregate(
        balance=Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='debit', journal_lines__journal_entry__date__lte=end_date)), Decimal('0.0')) -
                Coalesce(Sum('journal_lines__amount', filter=Q(journal_lines__entry_type='credit', journal_lines__journal_entry__date__lte=end_date)), Decimal('0.0'))
    )['balance']

    retained_earnings = revenue_balance - expense_balance

    # --- Build Account Trees ---
    # We use a dummy start_date because the helper calculates opening balance up to the "real" start date.
    # In this case, our "period" is just a single point in time (the end_date).
    # So, we pass end_date as both start and end to the helper, which will put all history into the 'opening_balance' field.
    asset_tree = _get_account_tree_with_balances(Account.AccountType.ASSET, end_date, end_date, include_opening_balance=True)
    liability_tree = _get_account_tree_with_balances(Account.AccountType.LIABILITY, end_date, end_date, include_opening_balance=True)
    equity_tree = _get_account_tree_with_balances(Account.AccountType.EQUITY, end_date, end_date, include_opening_balance=True)
    
    # --- Calculate Totals ---
    # For a balance sheet, we only care about the final closing balance.
    total_assets = sum(node['closing_balance'] for node in asset_tree)
    total_liabilities = sum(-node['closing_balance'] for node in liability_tree) # Invert sign for liabilities
    total_equity_base = sum(-node['closing_balance'] for node in equity_tree) # Invert sign for equity
    total_equity = total_equity_base + retained_earnings
    
    total_liabilities_and_equity = total_liabilities + total_equity
    
    is_balanced = abs(total_assets - total_liabilities_and_equity) < Decimal('0.001')

    context = {
        'active_page': 'expenses_reports',
        'end_date': end_date_str,
        'asset_tree': asset_tree,
        'liability_tree': liability_tree,
        'equity_tree': equity_tree,
        'retained_earnings': retained_earnings,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_and_equity': total_liabilities_and_equity,
        'is_balanced': is_balanced,
    }
    
    template_name = 'inventory/reports/balance_sheet.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/balance_sheet_content.html'
        
    return render(request, template_name, context)


def tax_reconciliation_report(request: HttpRequest) -> HttpResponse:
    """
    Generates a dedicated report for tax reconciliation, summarizing VAT and Withholding Tax.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)

    try:
        settings = GeneralAccountingSettings.load()
        vat_receivable_acc = settings.vat_receivable
        vat_payable_acc = settings.vat_payable
        wht_payable_acc = settings.withholding_tax_payable
    except GeneralAccountingSettings.DoesNotExist:
        context = {'error': "General Accounting Settings are not configured."}
        return render(request, 'inventory/reports/tax_reconciliation_report.html', context)

    # Helper to get balance components for an account
    def get_account_balance_details(account):
        if not account:
            return {'opening': Decimal('0.0'), 'debits': Decimal('0.0'), 'credits': Decimal('0.0'), 'closing': Decimal('0.0')}
        
        opening_debits = JournalEntryLine.objects.filter(account=account, entry_type='debit', journal_entry__date__lt=start_date).aggregate(s=Coalesce(Sum('amount'), Decimal('0.0')))['s']
        opening_credits = JournalEntryLine.objects.filter(account=account, entry_type='credit', journal_entry__date__lt=start_date).aggregate(s=Coalesce(Sum('amount'), Decimal('0.0')))['s']
        opening_balance = opening_debits - opening_credits

        period_debits = JournalEntryLine.objects.filter(account=account, entry_type='debit', journal_entry__date__range=(start_date, end_date)).aggregate(s=Coalesce(Sum('amount'), Decimal('0.0')))['s']
        period_credits = JournalEntryLine.objects.filter(account=account, entry_type='credit', journal_entry__date__range=(start_date, end_date)).aggregate(s=Coalesce(Sum('amount'), Decimal('0.0')))['s']
        
        closing_balance = opening_balance + period_debits - period_credits
        
        return {
            'account': account,
            'opening': opening_balance,
            'debits': period_debits,
            'credits': period_credits,
            'closing': closing_balance
        }

    vat_receivable_data = get_account_balance_details(vat_receivable_acc)
    vat_payable_data = get_account_balance_details(vat_payable_acc)
    wht_payable_data = get_account_balance_details(wht_payable_acc)

    # VAT is a liability, so a positive balance is owed. We expect payable > receivable.
    # The balance for payable accounts is naturally negative (credits > debits), so we invert it.
    net_vat_due = -vat_payable_data['closing'] - vat_receivable_data['closing']

    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'vat_receivable': vat_receivable_data,
        'vat_payable': vat_payable_data,
        'wht_payable': wht_payable_data,
        'net_vat_due': net_vat_due,
    }

    template_name = 'inventory/reports/tax_reconciliation_report.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/tax_reconciliation_report_content.html'
        
    return render(request, template_name, context)


def batch_production_variance_report(request: HttpRequest) -> HttpResponse:
    """
    Generates a report comparing theoretical vs. actual material consumption for production batches.
    Includes main batches and their continuation batches.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)

    # Fetch all main batches within the date range, ordered by creation date
    main_batches = Batch.objects.filter(
        creation_date__range=(start_date, end_date),
        parent_batch__isnull=True # Only main batches
    ).select_related('template__final_product').prefetch_related('continuation_batches__items__primitive_product', 'items__primitive_product')

    report_data = []
    grand_total_theoretical_qty = Decimal('0.0')
    grand_total_actual_qty = Decimal('0.0')
    grand_total_variance_qty = Decimal('0.0')
    grand_total_variance_cost = Decimal('0.0')

    final_product_type_totals = {}
    
    # Aggregation for charts
    primitive_product_totals = {}

    for main_batch in main_batches:
        all_related_batches = [main_batch] + list(main_batch.continuation_batches.all())
        
        # Aggregate theoretical and actual quantities for each primitive product across all related batches
        aggregated_product_data = {}

        for batch in all_related_batches:
            for item in batch.items.all():
                product_id = item.primitive_product.id
                if product_id not in aggregated_product_data:
                    aggregated_product_data[product_id] = {
                        'product_name': item.primitive_product.name,
                        'unit': item.primitive_product.unit,
                        'theoretical_quantity': Decimal('0.0'),
                        'actual_quantity': Decimal('0.0'),
                        'cost_at_consumption': Decimal(str(item.cost_at_consumption or 0.0)),
                    }
                aggregated_product_data[product_id]['theoretical_quantity'] += Decimal(str(item.theoretical_quantity))
                aggregated_product_data[product_id]['actual_quantity'] += Decimal(str(item.actual_quantity or 0.0))
        
        batch_total_theoretical_qty = Decimal('0.0')
        batch_total_actual_qty = Decimal('0.0')
        batch_total_variance_qty = Decimal('0.0')
        batch_total_variance_cost = Decimal('0.0')

        detailed_items = []
        for prod_id, data in aggregated_product_data.items():
            variance_qty = data['actual_quantity'] - data['theoretical_quantity']
            variance_cost = variance_qty * data['cost_at_consumption']
            
            batch_total_theoretical_qty += data['theoretical_quantity']
            batch_total_actual_qty += data['actual_quantity']
            batch_total_variance_qty += variance_qty
            batch_total_variance_cost += variance_cost

            # Populate primitive product totals for charts
            product_name = data['product_name']
            if product_name not in primitive_product_totals:
                primitive_product_totals[product_name] = {
                    'variance_qty': Decimal('0.0'),
                    'variance_cost': Decimal('0.0'),
                }
            primitive_product_totals[product_name]['variance_qty'] += variance_qty
            primitive_product_totals[product_name]['variance_cost'] += variance_cost

            detailed_items.append({
                'product_name': data['product_name'],
                'unit': data['unit'],
                'theoretical_quantity': data['theoretical_quantity'].quantize(Decimal('0.001')),
                'actual_quantity': data['actual_quantity'].quantize(Decimal('0.001')),
                'variance_quantity': variance_qty.quantize(Decimal('0.001')),
                'cost_at_consumption': data['cost_at_consumption'].quantize(Decimal('0.001')),
                'variance_cost': variance_cost.quantize(Decimal('0.001')),
            })
        
        report_data.append({
            'main_batch': main_batch,
            'detailed_items': detailed_items,
            'batch_total_theoretical_qty': batch_total_theoretical_qty.quantize(Decimal('0.001')),
            'batch_total_actual_qty': batch_total_actual_qty.quantize(Decimal('0.001')),
            'batch_total_variance_qty': batch_total_variance_qty.quantize(Decimal('0.001')),
            'batch_total_variance_cost': batch_total_variance_cost.quantize(Decimal('0.001')),
        })

        grand_total_theoretical_qty += batch_total_theoretical_qty
        grand_total_actual_qty += batch_total_actual_qty
        grand_total_variance_qty += batch_total_variance_qty
        grand_total_variance_cost += batch_total_variance_cost

        # Aggregate for final product type totals
        if main_batch.template and main_batch.template.final_product:
            final_product_type = main_batch.template.final_product.product_type
            if final_product_type not in final_product_type_totals:
                final_product_type_totals[final_product_type] = {
                    'theoretical_qty': Decimal('0.0'),
                    'actual_qty': Decimal('0.0'),
                    'variance_qty': Decimal('0.0'),
                    'variance_cost': Decimal('0.0'),
                }
            final_product_type_totals[final_product_type]['theoretical_qty'] += batch_total_theoretical_qty
            final_product_type_totals[final_product_type]['actual_qty'] += batch_total_actual_qty
            final_product_type_totals[final_product_type]['variance_qty'] += batch_total_variance_qty
            final_product_type_totals[final_product_type]['variance_cost'] += batch_total_variance_cost

    # Prepare data for Chart.js
    # Sort by absolute cost variance to show most impactful items first
    sorted_primitive_totals = sorted(primitive_product_totals.items(), key=lambda item: abs(item[1]['variance_cost']), reverse=True)

    chart_data = {
        'labels': [item[0] for item in sorted_primitive_totals],
        'variance_qty_data': [float(item[1]['variance_qty']) for item in sorted_primitive_totals],
        'variance_cost_data': [float(item[1]['variance_cost']) for item in sorted_primitive_totals],
    }

    context = {
        'active_page': 'expenses_reports',
        'start_date': start_date_str,
        'end_date': end_date_str,
        'report_data': report_data,
        'grand_total_theoretical_qty': grand_total_theoretical_qty.quantize(Decimal('0.001')),
        'grand_total_actual_qty': grand_total_actual_qty.quantize(Decimal('0.001')),
        'grand_total_variance_qty': grand_total_variance_qty.quantize(Decimal('0.001')),
        'grand_total_variance_cost': grand_total_variance_cost.quantize(Decimal('0.001')),
        'final_product_type_totals': final_product_type_totals,
        'chart_data': json.dumps(chart_data),
    }

    template_name = 'inventory/reports/batch_production_variance_report.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/batch_production_variance_report_content.html'
        
    return render(request, template_name, context)


# ==============================================================================
#  NEW RECONCILIATION REPORT
# ==============================================================================

def reconciliation_report(request: HttpRequest) -> HttpResponse:
    """
    Generates a report showing the status of bank reconciliations and lists
    outstanding (uncleared) transactions.
    """
    bank_account_id = request.GET.get('bank_account')
    
    reconciliations = BankReconciliation.objects.filter(status=BankReconciliation.Status.RECONCILED)
    
    outstanding_payments = Payment.objects.filter(
        cleared_date__isnull=True
    ).select_related('bank_account', 'supplier', 'customer').order_by('payment_date')
    
    outstanding_transfers = BankTransfer.objects.filter(
        Q(source_cleared_date__isnull=True) | Q(destination_cleared_date__isnull=True)
    ).select_related('source_account', 'destination_account').order_by('transfer_date')

    if bank_account_id:
        reconciliations = reconciliations.filter(bank_account_id=bank_account_id)
        outstanding_payments = outstanding_payments.filter(bank_account_id=bank_account_id)
        outstanding_transfers = outstanding_transfers.filter(
            Q(source_account_id=bank_account_id, source_cleared_date__isnull=True) |
            Q(destination_account_id=bank_account_id, destination_cleared_date__isnull=True)
        )

    context = {
        'active_page': 'expenses_reports',
        'bank_accounts': BankAccount.objects.all(),
        'selected_bank_account': int(bank_account_id) if bank_account_id else None,
        'reconciliations': reconciliations,
        'outstanding_payments': outstanding_payments,
        'outstanding_transfers': outstanding_transfers,
    }
    
    template_name = 'inventory/reports/reconciliation_report.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/reconciliation_report_content.html'
        
    return render(request, template_name, context)


# ==============================================================================
#  NEW PRODUCT LEDGER REPORT
# ==============================================================================

def product_ledger(request: HttpRequest) -> HttpResponse:
    """
    Generates a detailed report showing the complete lifecycle of a single product
    within a specified date range, including a running stock balance and value.
    """
    start_date, end_date, start_date_str, end_date_str = _get_date_range_from_request(request)
    product_id = request.GET.get('product_id')
    
    product = None
    transactions = []
    opening_balance_qty = Decimal('0.0')
    opening_balance_val = Decimal('0.0')
    closing_balance_qty = Decimal('0.0')
    closing_balance_val = Decimal('0.0')
    total_in_qty = Decimal('0.0')
    total_out_qty = Decimal('0.0')

    if product_id:
        product = get_object_or_404(Product, pk=product_id)

        # 1. Calculate Opening Balance (state before start_date)
        opening_state = get_inventory_state_at_datetime(product.id, start_date)
        opening_balance_qty = opening_state['quantity']
        opening_balance_val = opening_state['value']
        
        # 2. Get all transactions within the period
        receipts = InventoryLog.objects.filter(
            product=product, status=InventoryLog.Status.RELEASED,
            release_timestamp__range=(start_date, end_date)
        ).select_related('company', 'po_item__purchase_order')

        prod_consumptions = BatchItem.objects.filter(
            primitive_product=product, batch__creation_date__range=(start_date, end_date)
        ).select_related('batch__template__final_product')

        returns = ProductionReturn.objects.filter(
            product=product, return_date__range=(start_date, end_date)
        ).select_related('source_log')

        internal_consumptions = InventoryConsumption.objects.filter(
            product=product, consumption_date__range=(start_date, end_date)
        ).select_related('source_log')

        dispatches = FinishedProductDispatch.objects.filter(
            sales_order_item__finished_product__batch__template__final_product=product,
            dispatch_date__range=(start_date, end_date)
        ).select_related('sales_order_item__sales_order__customer', 'sales_order_item__finished_product')

        # 3. Combine and sort all transactions chronologically
        all_transactions = []
        for r in receipts:
            all_transactions.append({'date': r.release_timestamp, 'type': 'IN', 'obj': r, 'sort_key': 1})
        for pc in prod_consumptions:
            all_transactions.append({'date': pc.batch.creation_date, 'type': 'OUT', 'obj': pc, 'sort_key': 2})
        for ret in returns:
            all_transactions.append({'date': ret.return_date, 'type': 'IN', 'obj': ret, 'sort_key': 1})
        for ic in internal_consumptions:
            all_transactions.append({'date': ic.consumption_date, 'type': 'OUT', 'obj': ic, 'sort_key': 2})
        for d in dispatches:
            all_transactions.append({'date': d.dispatch_date, 'type': 'OUT', 'obj': d, 'sort_key': 2})
            
        sorted_transactions = sorted(all_transactions, key=lambda x: (x['date'], x['sort_key']))
        
        # 4. Process transactions to build the ledger
        running_qty = opening_balance_qty
        running_val = opening_balance_val
        
        for trx_data in sorted_transactions:
            trx = trx_data['obj']
            current_mac = (running_val / running_qty) if running_qty > 0 else Decimal('0.0')
            
            entry = {'date': trx_data['date'], 'in_qty': Decimal('0.0'), 'out_qty': Decimal('0.0')}

            if isinstance(trx, InventoryLog):
                qty = Decimal(str(trx.quantity))
                val = qty * trx.costing_unit_price
                entry.update({
                    'type': 'استلام', 'description': f"شراء من {trx.company.name} (أمر شراء: {trx.po_item.purchase_order.po_number if trx.po_item else 'غير متاح'}, فحص جودة: {trx.qc_no})",
                    'in_qty': qty, 'unit_cost': trx.costing_unit_price, 'total_val': val
                })
                running_qty += qty
                running_val += val
                total_in_qty += qty
            
            elif isinstance(trx, ProductionReturn):
                qty = Decimal(str(trx.quantity))
                cost = trx.source_log.costing_unit_price if trx.source_log else current_mac
                val = qty * cost
                entry.update({
                    'type': 'مرتجع إنتاج', 'description': f"مرتجع من الإنتاج. ملاحظات: {trx.notes or 'لا يوجد'}",
                    'in_qty': qty, 'unit_cost': cost, 'total_val': val
                })
                running_qty += qty
                running_val += val
                total_in_qty += qty

            elif isinstance(trx, BatchItem):
                qty = Decimal(str(trx.actual_quantity or 0.0))
                cost = trx.cost_at_consumption or current_mac
                val = qty * cost
                entry.update({
                    'type': 'استخدام في الإنتاج', 'description': f"استخدام في أمر تشغيل: {trx.batch.shop_order_number} لإنتاج {trx.batch.template.final_product.name}",
                    'out_qty': qty, 'unit_cost': cost, 'total_val': -val
                })
                running_qty -= qty
                running_val -= val
                total_out_qty += qty

            elif isinstance(trx, InventoryConsumption):
                qty = Decimal(str(trx.quantity_consumed))
                val = trx.cost_at_consumption
                cost = (val / qty) if qty > 0 else Decimal('0.0')
                entry.update({
                    'type': 'استخدام داخلي', 'description': f"صرف إلى قسم {trx.get_department_display()}. ملاحظات: {trx.notes or 'لا يوجد'}",
                    'out_qty': qty, 'unit_cost': cost, 'total_val': -val
                })
                running_qty -= qty
                running_val -= val
                total_out_qty += qty

            elif isinstance(trx, FinishedProductDispatch):
                qty = Decimal(str(trx.quantity))
                val = trx.cost_at_dispatch
                cost = (val / qty) if qty > 0 else Decimal('0.0')
                entry.update({
                    'type': 'مبيعات', 'description': f"بيع إلى {trx.sales_order_item.sales_order.customer.name} (أمر بيع: {trx.sales_order_item.sales_order.so_number})",
                    'out_qty': qty, 'unit_cost': cost, 'total_val': -val
                })
                running_qty -= qty
                running_val -= val
                total_out_qty += qty

            entry['running_qty'] = running_qty
            entry['running_val'] = running_val
            transactions.append(entry)

        closing_balance_qty = running_qty
        closing_balance_val = running_val

    context = {
        'active_page': 'analysis', # Match the sidebar section
        'products': Product.objects.order_by('name'),
        'selected_product': product,
        'transactions': transactions,
        'opening_balance_qty': opening_balance_qty,
        'opening_balance_val': opening_balance_val,
        'closing_balance_qty': closing_balance_qty,
        'closing_balance_val': closing_balance_val,
        'total_in_qty': total_in_qty,
        'total_out_qty': total_out_qty,
        'start_date': start_date_str,
        'end_date': end_date_str,
    }
    
    template_name = 'inventory/reports/product_ledger.html'
    if 'X-Partial-Request' in request.headers:
        template_name = 'inventory/partials/reports/product_ledger_content.html'
        
    return render(request, template_name, context)