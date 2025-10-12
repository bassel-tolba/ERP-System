from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  ACCOUNTING AUDIT MODELS
# ==============================================================================

class PeriodClosingAuditLog(models.Model):
    """Logs all status changes for a financial period for audit purposes."""
    class ActionType(models.TextChoices):
        CLOSE = 'close', _('Close Period')
        REOPEN = 'reopen', _('Re-open Period')
        LOCK = 'lock', _('Permanently Lock')

    financial_period = models.ForeignKey(
        'FinancialPeriod', on_delete=models.CASCADE,
        related_name='audit_logs', verbose_name=_("Financial Period")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        verbose_name=_("User"),
        help_text=_("The user who performed the action.")
    )
    action_timestamp = models.DateTimeField(auto_now_add=True, verbose_name=_("Action Timestamp"))
    action_type = models.CharField(
        max_length=20, choices=ActionType.choices, verbose_name=_("Action Type")
    )
    justification = models.TextField(
        blank=True, null=True, verbose_name=_("Justification"),
        help_text=_("Required when re-opening a closed period.")
    )

    class Meta:
        verbose_name = _("Period Closing Audit Log")
        verbose_name_plural = _("Period Closing Audit Logs")
        ordering = ['-action_timestamp']

    def __str__(self):
        return f"{self.get_action_type_display()} on {self.financial_period} by {self.user} at {self.timestamp}"


# ==============================================================================
#  NEW PERIOD CLOSING CHECKLIST MODEL
# ==============================================================================

class PeriodCloseChecklist(models.Model):
    """
    A comprehensive checklist to guide and validate the period-closing process.
    Each financial period will have one instance of this model.
    """
    financial_period = models.OneToOneField(
        'FinancialPeriod', on_delete=models.CASCADE,
        related_name='checklist', verbose_name=_("Financial Period")
    )

    # --- Calculated Flags (updated by services) ---
    all_banks_reconciled = models.BooleanField(default=False, verbose_name=_("All Bank Accounts Reconciled"))
    no_draft_manual_jes = models.BooleanField(default=False, verbose_name=_("No Draft Manual Journal Entries"))
    no_unposted_invoices = models.BooleanField(default=False, verbose_name=_("No Unposted Invoices"))

    # --- Process Flags (updated by running the specific process) ---
    is_depreciation_run = models.BooleanField(default=False, verbose_name=_("Monthly Depreciation Has Been Run"))
    is_overhead_posted = models.BooleanField(default=False, verbose_name=_("Overhead Allocation Has Been Posted"))
    is_inventory_valuation_run = models.BooleanField(
        default=True, verbose_name=_("Inventory Valuation is Finalized"),
        help_text=_("This is assumed to be true as valuation is perpetual.")
    )
    is_amortization_run = models.BooleanField(default=False, verbose_name=_("Prepaid Expense Amortization Has Been Run"))
    is_accruals_run = models.BooleanField(default=False, verbose_name=_("Expense Accruals Have Been Run"))


    # --- Manual Review Flags (to be checked by an accountant) ---
    is_ar_aging_reviewed = models.BooleanField(default=False, verbose_name=_("A/R Aging Report Reviewed"))
    is_ap_aging_reviewed = models.BooleanField(default=False, verbose_name=_("A/P Aging Report Reviewed"))
    is_inventory_reconciled = models.BooleanField(default=False, verbose_name=_("Inventory Reconciliation Reviewed"))
    is_fixed_assets_reviewed = models.BooleanField(default=False, verbose_name=_("Fixed Assets Review Completed"))

    class Meta:
        verbose_name = _("Period Close Checklist")
        verbose_name_plural = _("Period Close Checklists")

    def __str__(self):
        return f"Checklist for {self.financial_period.name}"

    @property
    def is_complete(self):
        """Returns True if all checklist items are marked as complete."""
        return all([
            self.is_depreciation_run,
            self.is_overhead_posted,
            self.all_banks_reconciled,
            self.no_draft_manual_jes,
            self.no_unposted_invoices,
            self.is_inventory_valuation_run,
        ])


class TransactionCorrection(models.Model):
    """
    An audit model that records when a transaction from a closed period is
    corrected. This links the original transaction to the adjusting journal entry.
    """
    # Generic FK to the source document being corrected
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    source_object = GenericForeignKey('content_type', 'object_id')

    # The new JE that corrects the original transaction
    adjusting_journal_entry = models.OneToOneField(
        'JournalEntry',
        on_delete=models.PROTECT,
        related_name='correction_for',
        verbose_name=_("Adjusting Journal Entry")
    )

    justification = models.TextField(verbose_name=_("Justification for Correction"))
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name=_("Corrected By")
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Correction Timestamp"))

    class Meta:
        db_table = 'transaction_corrections'
        verbose_name = _("Transaction Correction")
        verbose_name_plural = _("Transaction Corrections")
        ordering = ['-created_at']
        permissions = [
            ("can_create_transaction_correction", "Can create transaction corrections for posted documents"),
        ]

    def __str__(self):
        return f"Correction for {self.source_object} created at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
