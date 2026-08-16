# gipcco_project/inventory/services/reports/ar_reports.py
import logging
from django.db.models import Q, F, Sum, Case, When, Value, DecimalField, Subquery, OuterRef
from django.db.models.functions import Coalesce
from datetime import timedelta, date
from decimal import Decimal

from ...models import Customer, CustomerInvoice, Payment, CustomerPaymentApplication, CustomerCreditMemo

logger = logging.getLogger(__name__)

def get_ar_aging_data(as_of_date: date):
    """
    Generates Accounts Receivable aging data.

    This function calculates the outstanding balance for each customer and categorizes
    it into aging buckets based on the invoice due dates. It also accounts for
    unapplied payments and credits.

    Args:
        as_of_date: The date for which to calculate the aging report.

    Returns:
        A list of dictionaries, where each dictionary represents a customer's
        aging data with balances in different buckets (e.g., 'current', '1_30',
        'over_120', 'total', and 'unapplied_credits').
    """
    as_of_date = date.fromisoformat(as_of_date) if isinstance(as_of_date, str) else as_of_date

    # Subquery to calculate the total amount paid for each invoice up to the as_of_date
    payments_subquery = CustomerPaymentApplication.objects.filter(
        invoice=OuterRef('pk'),
        application_date__lte=as_of_date
    ).values('invoice').annotate(total_paid=Sum('amount_applied')).values('total_paid')

    # Get all invoices that were open at the as_of_date
    invoices = CustomerInvoice.objects.filter(
        invoice_date__lte=as_of_date,
        status__in=[
            CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT,
            CustomerInvoice.InvoiceStatus.PARTIALLY_PAID
        ]
    ).select_related('customer').annotate(
        paid_to_date=Coalesce(Subquery(payments_subquery, output_field=DecimalField()), Decimal('0.0'))
    )
    logger.debug(f"Found {invoices.count()} invoices to process.")

    aging_data = {}

    for invoice in invoices:
        balance_due = invoice.total_amount - invoice.paid_to_date
        if balance_due <= Decimal('0.001'):
            continue

        days_overdue = (as_of_date - invoice.due_date).days

        if days_overdue <= 0:
            bucket = 'current'
        elif days_overdue <= 30:
            bucket = '1_30'
        elif days_overdue <= 60:
            bucket = '31_60'
        elif days_overdue <= 90:
            bucket = '61_90'
        elif days_overdue <= 120:
            bucket = '91_120'
        else:
            bucket = 'over_120'

        customer_id = invoice.customer.id
        if customer_id not in aging_data:
            aging_data[customer_id] = {
                'customer': invoice.customer,
                'current': Decimal('0'), '1_30': Decimal('0'), '31_60': Decimal('0'),
                '61_90': Decimal('0'), '91_120': Decimal('0'), 'over_120': Decimal('0'),
                'total_due': Decimal('0'), 'unapplied_credits': Decimal('0')
            }

        aging_data[customer_id][bucket] += balance_due
        aging_data[customer_id]['total_due'] += balance_due
    
    logger.debug(f"Aging data after processing invoices: {aging_data}")

    # Calculate unapplied payments and credits for each customer
    unapplied_payments = Payment.objects.filter(
        payment_type=Payment.PaymentType.PAYMENT_IN,
        payment_date__lte=as_of_date,
        customer__isnull=False
    ).values('customer').annotate(
        total_paid=Sum('amount'),
        total_applied=Coalesce(Sum('customer_applications__amount_applied', filter=Q(customer_applications__application_date__lte=as_of_date)), Decimal('0.0'))
    ).filter(total_paid__gt=F('total_applied'))
    logger.debug(f"Found {len(unapplied_payments)} customers with unapplied payments.")

    for payment_summary in unapplied_payments:
        customer_id = payment_summary['customer']
        unapplied_amount = payment_summary['total_paid'] - payment_summary['total_applied']

        if customer_id not in aging_data:
             # Find the customer instance to display in the report
            customer = Customer.objects.get(pk=customer_id)
            aging_data[customer_id] = {
                'customer': customer,
                'current': Decimal('0'), '1_30': Decimal('0'), '31_60': Decimal('0'),
                '61_90': Decimal('0'), '91_120': Decimal('0'), 'over_120': Decimal('0'),
                'total_due': Decimal('0'), 'unapplied_credits': Decimal('0')
            }
        
        aging_data[customer_id]['unapplied_credits'] += unapplied_amount

    # --- NEW: Factor in unapplied Credit Memos ---
    unapplied_memos = CustomerCreditMemo.objects.filter(
        memo_date__lte=as_of_date,
        status__in=[CustomerCreditMemo.Status.OPEN, CustomerCreditMemo.Status.PARTIALLY_APPLIED]
    ).values('customer').annotate(
        total_unapplied=Sum('unapplied_amount')
    )
    logger.debug(f"Found {len(unapplied_memos)} customers with unapplied credit memos.")

    for memo_summary in unapplied_memos:
        customer_id = memo_summary['customer']
        unapplied_amount = memo_summary['total_unapplied']

        if customer_id not in aging_data:
            customer = Customer.objects.get(pk=customer_id)
            aging_data[customer_id] = {
                'customer': customer,
                'current': Decimal('0'), '1_30': Decimal('0'), '31_60': Decimal('0'),
                '61_90': Decimal('0'), '91_120': Decimal('0'), 'over_120': Decimal('0'),
                'total_due': Decimal('0'), 'unapplied_credits': Decimal('0')
            }
        
        aging_data[customer_id]['unapplied_credits'] += unapplied_amount

    # Final calculation of net balance
    report_list = list(aging_data.values())
    
    totals = {
        'current': sum(item['current'] for item in report_list),
        '1_30': sum(item['1_30'] for item in report_list),
        '31_60': sum(item['31_60'] for item in report_list),
        '61_90': sum(item['61_90'] for item in report_list),
        '91_120': sum(item['91_120'] for item in report_list),
        'over_120': sum(item['over_120'] for item in report_list),
        'total_due': sum(item['total_due'] for item in report_list),
        'unapplied_credits': sum(item['unapplied_credits'] for item in report_list),
    }
    
    for item in report_list:
        item['net_balance'] = item['total_due'] - item['unapplied_credits']
        
    totals['net_balance'] = totals['total_due'] - totals['unapplied_credits']

    return {
        'data': report_list,
        'totals': totals
    }


def get_customer_ar_details(customer_id: int, as_of_date: date):
    """
    Generates a detailed breakdown of a single customer's AR aging,
    including individual invoices and unapplied payments.
    """
    as_of_date = date.fromisoformat(as_of_date) if isinstance(as_of_date, str) else as_of_date

    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        logger.warning(f"Attempted to generate AR detail report for non-existent customer_id: {customer_id}")
        return None

    # --- Invoices Breakdown ---
    payments_subquery = CustomerPaymentApplication.objects.filter(
        invoice=OuterRef('pk'),
        application_date__lte=as_of_date
    ).values('invoice').annotate(total_paid=Sum('amount_applied')).values('total_paid')

    invoices = CustomerInvoice.objects.filter(
        customer_id=customer_id,
        invoice_date__lte=as_of_date,
        status__in=[
            CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT,
            CustomerInvoice.InvoiceStatus.PARTIALLY_PAID
        ]
    ).annotate(
        paid_to_date=Coalesce(Subquery(payments_subquery, output_field=DecimalField()), Decimal('0.0'))
    ).order_by('due_date')

    invoices_by_bucket = {
        'current': [], '1_30': [], '31_60': [], '61_90': [], '91_120': [], 'over_120': []
    }
    for inv in invoices:
        inv.calculated_balance_due = inv.total_amount - inv.paid_to_date
        if inv.calculated_balance_due <= Decimal('0.001'):
            continue
        
        days_overdue = (as_of_date - inv.due_date).days
        
        if days_overdue <= 0: bucket = 'current'
        elif days_overdue <= 30: bucket = '1_30'
        elif days_overdue <= 60: bucket = '31_60'
        elif days_overdue <= 90: bucket = '61_90'
        elif days_overdue <= 120: bucket = '91_120'
        else: bucket = 'over_120'
        invoices_by_bucket[bucket].append(inv)

    # --- Unapplied Payments Breakdown ---
    unapplied_payments = Payment.objects.filter(
        customer_id=customer_id,
        payment_type=Payment.PaymentType.PAYMENT_IN,
        payment_date__lte=as_of_date
    ).annotate(
        total_applied=Coalesce(Sum('customer_applications__amount_applied', filter=Q(customer_applications__application_date__lte=as_of_date)), Decimal('0.0'))
    ).filter(amount__gt=F('total_applied'))

    for p in unapplied_payments:
        p.unapplied_amount = p.amount - p.total_applied

    # --- NEW: Unapplied Credit Memos Breakdown ---
    unapplied_memos = CustomerCreditMemo.objects.filter(
        customer_id=customer_id,
        memo_date__lte=as_of_date,
        status__in=[CustomerCreditMemo.Status.OPEN, CustomerCreditMemo.Status.PARTIALLY_APPLIED],
        unapplied_amount__gt=Decimal('0.001')
    )

    return {
        'customer': customer,
        'invoices_by_bucket': {k: v for k, v in invoices_by_bucket.items() if v}, # Return only non-empty buckets
        'unapplied_payments': unapplied_payments,
        'unapplied_memos': unapplied_memos
    }


def get_customer_statement_data(customer_id: int, start_date: date, end_date: date):
    """
    Generates a detailed statement of account for a customer over a specified period,
    including opening/closing balances and a running balance.
    """
    try:
        customer = Customer.objects.get(pk=customer_id)
    except Customer.DoesNotExist:
        logger.warning(f"Attempted to generate statement for non-existent customer_id: {customer_id}")
        return None

    # --- 1. Calculate Opening Balance ---
    total_invoiced_before = CustomerInvoice.objects.filter(
        customer=customer,
        invoice_date__lt=start_date
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.0')

    total_paid_before = Payment.objects.filter(
        customer=customer,
        payment_date__lt=start_date,
        payment_type=Payment.PaymentType.PAYMENT_IN
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

    total_credited_before = CustomerCreditMemo.objects.filter(
        customer=customer, memo_date__lt=start_date
    ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.0')

    opening_balance = total_invoiced_before - total_paid_before - total_credited_before
    logger.debug(f"Customer {customer_id}: Opening balance at {start_date} is {opening_balance}")

    # --- 2. Get Transactions for the period ---
    invoices_qs = CustomerInvoice.objects.filter(
        customer=customer,
        invoice_date__range=(start_date, end_date)
    )

    payments_qs = Payment.objects.filter(
        customer=customer,
        payment_date__range=(start_date, end_date),
        payment_type=Payment.PaymentType.PAYMENT_IN
    )

    memos_qs = CustomerCreditMemo.objects.filter(
        customer=customer, memo_date__range=(start_date, end_date)
    )

    # --- 3. Combine and Sort Transactions ---
    transactions = []
    for inv in invoices_qs:
        transactions.append({
            'date': inv.invoice_date,
            'type': 'invoice',
            'obj': inv,
            'debit': inv.total_amount,
            'credit': Decimal('0.0')
        })

    for pmt in payments_qs:
        transactions.append({
            'date': pmt.payment_date,
            'type': 'payment',
            'obj': pmt,
            'debit': Decimal('0.0'),
            'credit': pmt.amount
        })

    for memo in memos_qs.order_by('memo_date'):
        transactions.append({
            'date': memo.memo_date,
            'type': 'credit_memo',
            'obj': memo,
            'debit': Decimal('0.0'),
            'credit': memo.total_amount # Credit memos reduce the balance
        })

    transactions.sort(key=lambda x: x['date'])

    # --- 4. Calculate Running Balance ---
    running_balance = opening_balance
    for t in transactions:
        running_balance += t['debit'] - t['credit']
        t['balance'] = running_balance
    
    closing_balance = running_balance
    logger.debug(f"Customer {customer_id}: Closing balance at {end_date} is {closing_balance}")

    return {
        'customer': customer,
        'start_date': start_date,
        'end_date': end_date,
        'opening_balance': opening_balance,
        'transactions': transactions,
        'closing_balance': closing_balance
    }
