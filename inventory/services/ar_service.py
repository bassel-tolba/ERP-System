from datetime import date
from decimal import Decimal
from typing import List, Dict, Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from ..models import (
    Customer, CustomerInvoice, Payment, CustomerCreditMemo, JournalEntry, JournalEntryLine, GeneralAccountingSettings,
    CustomerPaymentApplication, CustomerCreditMemoApplication
)
from .accounting._helpers import _check_period_is_open


def apply_customer_payments_and_credits(
    customer: Customer,
    application_date: date,
    applications: List[Dict[str, Any]]
):
    """
    Applies multiple payments and/or credit memos to multiple invoices for a single customer.
    This is the core logic for the A/R Cash Application Workbench.

    Args:
        customer: The Customer object for whom the applications are being made.
        application_date: The date to use for the application records and journal entry.
        applications: A list of dictionaries, each representing a single application.
            Example: [
                {'source_type': 'payment', 'source_id': 1, 'target_invoice_id': 101, 'amount': Decimal('100.00')},
                {'source_type': 'memo', 'source_id': 5, 'target_invoice_id': 101, 'amount': Decimal('50.00')},
                {'source_type': 'payment', 'source_id': 2, 'target_invoice_id': 102, 'amount': Decimal('200.00')}
            ]
    """
    if not applications:
        return

    _check_period_is_open(application_date)
    settings = GeneralAccountingSettings.load()

    with transaction.atomic():
        # 1. Aggregate IDs and fetch/lock all objects at once
        payment_ids = {app['source_id'] for app in applications if app['source_type'] == 'payment'}
        memo_ids = {app['source_id'] for app in applications if app['source_type'] == 'memo'}
        invoice_ids = {app['target_invoice_id'] for app in applications}

        payments = {p.id: p for p in Payment.objects.select_for_update().filter(id__in=payment_ids, customer=customer)}
        memos = {m.id: m for m in CustomerCreditMemo.objects.select_for_update().filter(id__in=memo_ids, customer=customer)}
        invoices = {i.id: i for i in CustomerInvoice.objects.select_for_update().filter(id__in=invoice_ids, customer=customer)}

        # 2. Validate all applications before making changes
        for app in applications:
            invoice = invoices.get(app['target_invoice_id'])
            if not invoice:
                raise ValidationError(_("Invoice with ID %(id)s not found or does not belong to this customer.") % {'id': app['target_invoice_id']})
            if app['amount'] > invoice.balance_due:
                raise ValidationError(_("Amount %(amount)s exceeds balance due %(balance)s for invoice #%(id)s.") % {
                    'amount': app['amount'], 'balance': invoice.balance_due, 'id': invoice.invoice_number
                })

            if app['source_type'] == 'payment':
                payment = payments.get(app['source_id'])
                if not payment:
                    raise ValidationError(_("Payment with ID %(id)s not found or does not belong to this customer.") % {'id': app['source_id']})
                if app['amount'] > payment.unapplied_amount:
                    raise ValidationError(_("Amount %(amount)s exceeds unapplied balance %(balance)s for payment #%(id)s.") % {
                        'amount': app['amount'], 'balance': payment.unapplied_amount, 'id': payment.id
                    })
            elif app['source_type'] == 'memo':
                memo = memos.get(app['source_id'])
                if not memo:
                    raise ValidationError(_("Credit Memo with ID %(id)s not found or does not belong to this customer.") % {'id': app['source_id']})
                if app['amount'] > memo.unapplied_amount:
                    raise ValidationError(_("Amount %(amount)s exceeds unapplied balance %(balance)s for credit memo #%(id)s.") % {
                        'amount': app['amount'], 'balance': memo.unapplied_amount, 'id': memo.id
                    })
            else:
                raise ValidationError(_("Invalid source type '%(type)s'.") % {'type': app['source_type']})

        # 3. Create application records and update balances
        total_application_amount = Decimal('0.000')
        debit_lines_data = []

        for app in applications:
            amount = app['amount']
            total_application_amount += amount
            invoice = invoices[app['target_invoice_id']]
            invoice.amount_paid += amount

            if app['source_type'] == 'payment':
                CustomerPaymentApplication.objects.create(
                    payment_id=app['source_id'], invoice=invoice, amount_applied=amount, application_date=application_date
                )
                debit_lines_data.append({'account': settings.customer_deposits_account, 'amount': amount})
            elif app['source_type'] == 'memo':
                CustomerCreditMemoApplication.objects.create(
                    credit_memo_id=app['source_id'], invoice=invoice, amount_applied=amount, application_date=application_date
                )
                debit_lines_data.append({'account': settings.sales_returns_account, 'amount': amount})

        # 4. Create a single consolidated Journal Entry for the entire run
        if total_application_amount > 0:
            je = JournalEntry.objects.create(
                date=application_date,
                description=_("Cash/Credit application for customer %(customer)s") % {'customer': customer.name},
                content_type=ContentType.objects.get_for_model(customer),
                object_id=customer.id
            )
            for line_data in debit_lines_data:
                JournalEntryLine.objects.create(
                    journal_entry=je, account=line_data['account'], amount=line_data['amount'],
                    entry_type='debit', sub_ledger_object=customer
                )
            JournalEntryLine.objects.create(
                journal_entry=je, account=settings.accounts_receivable, amount=total_application_amount,
                entry_type='credit', sub_ledger_object=customer
            )
            je.validate_balance()

        # 5. Final status updates after all applications are created
        for invoice in invoices.values():
            invoice.update_status(save=True)
        for memo in memos.values():
            memo.update_status(save=True)
