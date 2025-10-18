from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  NEW ADJUSTING ENTRIES MODELS (PREPAID & ACCRUED)
# ==============================================================================

class CostPoolSplit(models.Model):
    """
    A generic linking table to split the cost of a source object (like a
    PrepaidExpense or AccruedExpense) across multiple cost pools by percentage.
    """
    percentage = models.DecimalField(
        max_digits=5, decimal_places=2, verbose_name=_("Percentage"),
        help_text=_("The percentage of the cost to allocate to this pool (e.g., 70.50).")
    )
    cost_pool = models.ForeignKey('CostPool', on_delete=models.CASCADE, verbose_name=_("Cost Pool"))

    # Generic Foreign Key to link to either PrepaidExpense or AccruedExpense
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = _("Cost Pool Split")
        verbose_name_plural = _("Cost Pool Splits")
        unique_together = ('content_type', 'object_id', 'cost_pool')

    def __str__(self):
        return f"{self.percentage}% to {self.cost_pool.name} for {self.source_object}"

    def clean(self):
        # Ensure percentages for a single source object do not exceed 100%
        with transaction.atomic():
            siblings = CostPoolSplit.objects.filter(
                content_type=self.content_type,
                object_id=self.object_id
            ).exclude(id=self.id)
            total_percentage = siblings.aggregate(total=Sum('percentage'))['total'] or Decimal('0.0')
            if total_percentage + self.percentage > 100:
                raise ValidationError(_("The total percentage for this item cannot exceed 100%."))


class PrepaidExpense(models.Model):
    """
    Represents a prepaid asset, which will be amortized over time.
    This is the Prepaid Expenses Sub-Ledger.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', _("Active")
        FULLY_AMORTIZED = 'amortized', _("Fully Amortized")
        WRITTEN_OFF = 'written_off', _("Written Off")

    description = models.CharField(max_length=255)
    initial_amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Initial Prepaid Amount"))
    amortization_start_date = models.DateField(verbose_name=_("Amortization Start Date"))
    amortization_end_date = models.DateField(verbose_name=_("Amortization End Date"))
    asset_account = models.ForeignKey('Account', on_delete=models.PROTECT, related_name='+', verbose_name=_("Asset Control Account"))
    expense_account = models.ForeignKey(
        'Account', on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Target Expense Account"),
        help_text=_("The expense account to debit during amortization (e.g., Insurance Expense).")
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name=_("Status"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='prepaid_expenses_created')
    
    # Unified source link using GenericForeignKey
    source_content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    source_object_id = models.PositiveIntegerField()
    source_content_object = GenericForeignKey('source_content_type', 'source_object_id')
    
    # Generic relation for cost pool splits
    cost_pool_splits = GenericRelation(CostPoolSplit)

    class Meta:
        verbose_name = _("Prepaid Expense")
        verbose_name_plural = _("Prepaid Expenses")

    def __str__(self):
        return f"Prepaid Asset ({self.initial_amount}) starting {self.amortization_start_date}"

    @property
    def remaining_balance(self):
        amortized_so_far = self.amortization_logs.aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        return self.initial_amount - amortized_so_far


class AmortizationLog(models.Model):
    """
    Logs a single amortization event for a prepaid asset for a specific period.
    """
    prepaid_expense = models.ForeignKey(
        PrepaidExpense, on_delete=models.CASCADE, related_name='amortization_logs', verbose_name=_("Prepaid Expense")
    )
    financial_period = models.ForeignKey(
        'FinancialPeriod', on_delete=models.PROTECT, related_name='amortization_logs', verbose_name=_("Financial Period")
    )
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amortized Amount"))
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Amortization Journal Entry")
    )

    class Meta:
        verbose_name = _("Amortization Log")
        verbose_name_plural = _("Amortization Logs")
        unique_together = ('prepaid_expense', 'financial_period')

    def __str__(self):
        return f"Amortization of {self.amount} for {self.prepaid_expense} in {self.financial_period.name}"


class AccruedExpense(models.Model):
    """
    Represents a recurring expense that is estimated and booked monthly,
    to be trued-up later when an invoice arrives.
    """
    class Status(models.TextChoices):
        ACTIVE = 'active', _("Active")
        INACTIVE = 'inactive', _("Inactive")

    description = models.CharField(max_length=255, verbose_name=_("Expense Description"))
    total_estimated_amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Total Estimated Amount"))
    accrual_start_date = models.DateField(verbose_name=_("Accrual Start Date"))
    accrual_end_date = models.DateField(verbose_name=_("Accrual End Date"))
    source_request = models.OneToOneField(
        'ExpenseRequest', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_accrual', verbose_name=_("Source Expense Request")
    )
    target_expense_account = models.ForeignKey(
        'Account', on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Target Expense Account"),
        help_text=_("The expense account to debit during the monthly accrual (e.g., Utilities Expense).")
    )
    target_liability_account = models.ForeignKey(
        'Account', on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Target Accrual Liability Account"),
        help_text=_("The liability account to credit (e.g., Accrued Expenses Payable).")
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name=_("Status"))

    # Generic relation for cost pool splits
    cost_pool_splits = GenericRelation(CostPoolSplit)

    class Meta:
        verbose_name = _("Accrued Expense")
        verbose_name_plural = _("Accrued Expenses")

    def __str__(self):
        return f"Accrual: {self.description} ({self.total_estimated_amount})"


class AccrualLog(models.Model):
    """
    Logs a single accrual event for a recurring expense for a specific period.
    """
    accrued_expense = models.ForeignKey(
        AccruedExpense, on_delete=models.CASCADE, related_name='accrual_logs', verbose_name=_("Accrued Expense")
    )
    financial_period = models.ForeignKey(
        'FinancialPeriod', on_delete=models.PROTECT, related_name='accrual_logs', verbose_name=_("Financial Period")
    )
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Accrued Amount"))
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("True-Up Journal Entry")
    )
    # --- NEW FIELDS FOR TRUE-UP ---
    settling_invoice = models.ForeignKey(
        'SupplierInvoice', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='settled_accruals', verbose_name=_("Settling Invoice")
    )
    true_up_journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("True-Up Journal Entry")
    )

    class Meta:
        verbose_name = _("Accrual Log")
        verbose_name_plural = _("Accrual Logs")
        unique_together = ('accrued_expense', 'financial_period')

    def __str__(self):
        return f"Accrual of {self.amount} for {self.accrued_expense} in {self.financial_period.name}"
