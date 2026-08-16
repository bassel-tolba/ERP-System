from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  OPENING BALANCE MIGRATION MODELS
# ==============================================================================

class OpeningBalanceEntry(models.Model):
    """
    Header for an opening balance data migration event.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', _("Draft")
        POSTED = 'posted', _("Posted")

    name = models.CharField(max_length=255, verbose_name=_("Migration Name / Event"))
    migration_date = models.DateField(verbose_name=_("Migration Go-Live Date"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, verbose_name=_("Status"))
    journal_entry = models.OneToOneField(
        'JournalEntry',
        on_delete=models.PROTECT,
        null=True, blank=True,
        related_name='opening_balance_entry',
        verbose_name=_("Resulting Journal Entry")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'opening_balance_entries'
        verbose_name = _("Opening Balance Entry")
        verbose_name_plural = _("Opening Balance Entries")
        ordering = ['-migration_date']

    def __str__(self):
        return self.name

class OpeningBalanceEntryLine(models.Model):
    """
    A single line in an opening balance entry, corresponding to one GL account.
    This line can be broken down into multiple sub-ledger entries.
    """
    class EntryType(models.TextChoices):
        DEBIT = 'debit', _("Debit")
        CREDIT = 'credit', _("Credit")

    opening_balance_entry = models.ForeignKey(
        OpeningBalanceEntry,
        on_delete=models.CASCADE,
        related_name='lines',
        verbose_name=_("Opening Balance Entry")
    )
    account = models.ForeignKey(
        'Account',
        on_delete=models.PROTECT,
        related_name='opening_balance_lines',
        verbose_name=_("GL Account")
    )
    entry_type = models.CharField(max_length=6, choices=EntryType.choices, verbose_name=_("Entry Type"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Total Amount for this Account"))

    class Meta:
        db_table = 'opening_balance_entry_lines'
        verbose_name = _("Opening Balance Entry Line")
        verbose_name_plural = _("Opening Balance Entry Lines")
        unique_together = ('opening_balance_entry', 'account')

    def __str__(self):
        return f"{self.account} - {self.total_amount} ({self.get_entry_type_display()})"

class OpeningBalanceSubLedgerDetail(models.Model):
    """
    Links a specific sub-ledger record (like a Customer or a specific batch of inventory)
    to an opening balance line, detailing how the total amount is composed.
    """
    line = models.ForeignKey(
        OpeningBalanceEntryLine,
        on_delete=models.CASCADE,
        related_name='sub_ledger_details',
        verbose_name=_("Opening Balance Line")
    )
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount for this Sub-Ledger item"))

    # Generic Foreign Key to the source sub-ledger record
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    sub_ledger_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'opening_balance_sub_ledger_details'
        verbose_name = _("Opening Balance Sub-Ledger Detail")
        verbose_name_plural = _("Opening Balance Sub-Ledger Details")
        unique_together = ('line', 'content_type', 'object_id')

    def __str__(self):
        return f"{self.sub_ledger_object}: {self.amount}"
