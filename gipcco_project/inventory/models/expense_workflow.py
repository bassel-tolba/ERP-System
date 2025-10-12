from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  NEW EXPENSE WORKFLOW MODELS
# ==============================================================================

class ExpenseLog(models.Model):
    class Classification(models.TextChoices):
        MANUFACTURING_OVERHEAD = 'manufacturing_overhead', _('تكاليف صناعية غير مباشرة')
        SG_A = 'sg_a', _('مصاريف بيعية وعمومية وإدارية')

    class Category(models.TextChoices):
        SALARIES = 'salaries', _('رواتب وأجور')
        UTILITIES = 'utilities', _('كهرباء ومياه واتصالات')
        RENT = 'rent', _('إيجارات')
        MARKETING = 'marketing', _('تسويق وإعلان')
        TRANSPORT = 'transport', _('نقل وشحن')
        MAINTENANCE = 'maintenance', _('صيانة (خدمات خارجية)')
        FEES = 'fees', _('رسوم حكومية وتراخيص')
        OTHER = 'other', _('مصاريف أخرى')

    class SettlementStatus(models.TextChoices):
        UNSETTLED = 'UNSETTLED', _('Unsettled')
        SETTLED = 'SETTLED', _('Settled')

    description = models.CharField(max_length=255, verbose_name=_("Description"))
    expense_date = models.DateField(verbose_name=_("Expense Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        verbose_name=_("Category"),
        null=True, blank=True
    )
    classification = models.CharField(
        max_length=50,
        choices=Classification.choices,
        verbose_name=_("Classification"),
        null=True, blank=True
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    # --- NEW: Link to Employee ---
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='expenses_logged',
        verbose_name=_("Responsible Employee")
    )

    # --- NEW: Link to Cost Pool ---
    cost_pool = models.ForeignKey(
        'CostPool',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='expenses',
        verbose_name=_("Cost Pool")
    )
    # Generic FK to link to the source of the expense (e.g., an InventoryConsumption)
    source_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='expense_logs'
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_content_object = GenericForeignKey('source_content_type', 'source_object_id')


    source_request = models.ForeignKey(
        'ExpenseRequest',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='final_expense_logs'
    )

    settlement_status = models.CharField(
        max_length=20, choices=SettlementStatus.choices, default=SettlementStatus.UNSETTLED,
        verbose_name=_("Settlement Status")
    )
    settlement_content_type = models.ForeignKey(
        ContentType, on_delete=models.SET_NULL, null=True, blank=True
    )
    settlement_object_id = models.PositiveIntegerField(null=True, blank=True)
    settlement_object = GenericForeignKey('settlement_content_type', 'settlement_object_id')

    class Meta:
        db_table = 'expense_logs'
        verbose_name = _("General Expense Log")
        verbose_name_plural = _("General Expense Logs")
        ordering = ['-expense_date']

    def __str__(self):
        return f"Expense: {self.description} for {self.amount} on {self.expense_date}"


class ExpenseRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', _('Pending Approval')
        APPROVED = 'APPROVED', _('Approved')
        REJECTED = 'REJECTED', _('Rejected')
        CANCELLED = 'CANCELLED', _('Cancelled')

    class RequestType(models.TextChoices):
        DIRECT_EXPENSE = 'DIRECT_EXPENSE', _('Direct Expense')
        INVENTORY_EXPENSE = 'INVENTORY_EXPENSE', _('Inventory Consumption to Expense')
        INVENTORY_CAPITALIZE = 'INVENTORY_CAPITALIZE', _('Inventory Consumption to Capitalize')
        INVENTORY_PREPAID = 'INVENTORY_PREPAID', _('Inventory Consumption to Prepaid')
        INVOICE_PREPAID = 'INVOICE_PREPAID', _('Prepaid Expense from Invoice')
        ACCRUAL = 'ACCRUAL', _('Expense Accrual')

    class SettlementMethod(models.TextChoices):
        ACCRUE_AND_PAY_LATER = 'ACCRUE_AND_PAY_LATER', _('Accrue and Pay via Supplier Invoice')
        DIRECT_PAYMENT = 'DIRECT_PAYMENT', _('Direct Payment from Bank/Cash')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    request_type = models.CharField(max_length=30, choices=RequestType.choices, db_index=True)
    description = models.TextField()
    request_date = models.DateField(help_text=_("The intended date of the expense."))
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='expense_requests_made', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='expense_requests_processed', on_delete=models.PROTECT, null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    # Data Fields for All Types
    amount = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    category = models.CharField(max_length=50, choices=ExpenseLog.Category.choices, null=True, blank=True)
    classification = models.CharField(max_length=50, choices=ExpenseLog.Classification.choices, null=True, blank=True)
    product = models.ForeignKey('Product', on_delete=models.PROTECT, null=True, blank=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=3, null=True, blank=True)
    cost_pool = models.ForeignKey('CostPool', on_delete=models.PROTECT, null=True, blank=True)
    fixed_asset = models.ForeignKey('FixedAsset', on_delete=models.PROTECT, null=True, blank=True)
    source_invoice = models.ForeignKey('SupplierInvoice', on_delete=models.PROTECT, null=True, blank=True)
    asset_account = models.ForeignKey('Account', related_name='+', on_delete=models.PROTECT, null=True, blank=True)
    expense_account = models.ForeignKey('Account', related_name='+', on_delete=models.PROTECT, null=True, blank=True)
    amortization_start_date = models.DateField(null=True, blank=True)
    amortization_end_date = models.DateField(null=True, blank=True)

    # --- NEW SETTLEMENT FIELDS ---
    settlement_method = models.CharField(
        max_length=30, choices=SettlementMethod.choices, null=True, blank=True,
        help_text=_("Required for Direct Expense requests.")
    )
    supplier = models.ForeignKey(
        'Company', on_delete=models.PROTECT, null=True, blank=True,
        help_text=_("Required if settlement method is Accrue and Pay Later.")
    )
    bank_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, null=True, blank=True,
        help_text=_("Required if settlement method is Direct Payment.")
    )

    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
