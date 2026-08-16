from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  NEW BANK RECONCILIATION MODELS
# ==============================================================================

class BankReconciliation(models.Model):
    """
    Represents a single bank reconciliation period for a specific bank account.
    """
    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        RECONCILED = 'reconciled', _('Reconciled')
        
    bank_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, related_name='reconciliations',
        verbose_name=_("Bank Account")
    )
    statement_date = models.DateField(verbose_name=_("Statement Date"))
    statement_opening_balance = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Statement Opening Balance")
    )
    statement_closing_balance = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Statement Closing Balance")
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name=_("Status")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-statement_date']
        unique_together = ('bank_account', 'statement_date')
        db_table = 'bank_reconciliations'
        verbose_name = _("Bank Reconciliation")
        verbose_name_plural = _("Bank Reconciliations")

    def __str__(self):
        return f"{self.bank_account.name} - {self.statement_date.strftime('%Y-%m-%d')}"

    def unmatch_all_transactions(self):
        from .accounting_sub_ledger import BankTransfer
        """Resets all linked payments and transfers to an unreconciled state."""
        # Unlink Payments
        self.payments.update(reconciliation=None, cleared_date=None)
        
        # Unlink BankTransfers (both source and destination)
        BankTransfer.objects.filter(source_reconciliation=self).update(
            source_reconciliation=None, source_cleared_date=None
        )
        BankTransfer.objects.filter(destination_reconciliation=self).update(
            destination_reconciliation=None, destination_cleared_date=None
        )
        
        # Reset statement lines
        self.statement_lines.update(is_reconciled=False, reconciled_object_content_type=None, reconciled_object_id=None)


class BankStatementLine(models.Model):
    """
    Represents a single transaction line from an imported bank statement.
    """
    reconciliation = models.ForeignKey(
        BankReconciliation, on_delete=models.CASCADE, related_name='statement_lines',
        verbose_name=_("Reconciliation Period")
    )
    transaction_date = models.DateField(verbose_name=_("Transaction Date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Amount"),
        help_text=_("Positive for deposits, negative for withdrawals.")
    )
    is_reconciled = models.BooleanField(default=False, verbose_name=_("Is Reconciled"))

    # --- Generic FK to link to the matched internal transaction (Payment, BankTransfer, etc.) ---
    reconciled_object_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    reconciled_object_id = models.PositiveIntegerField(null=True, blank=True)
    reconciled_object = GenericForeignKey(
        'reconciled_object_content_type', 'reconciled_object_id'
    )

    class Meta:
        db_table = 'bank_statement_lines' # Explicitly set the table name
        ordering = ['transaction_date', 'pk']
        verbose_name = _("Bank Statement Line")
        verbose_name_plural = _("Bank Statement Lines")

    def __str__(self):
        return f"{self.transaction_date}: {self.description} ({self.amount})"
