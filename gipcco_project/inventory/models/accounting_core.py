from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings
from .operational import Product


# ==============================================================================
#  ACCOUNTING CORE MODELS
# ==============================================================================

class FiscalYear(models.Model):
    """
    Represents a fiscal year, which contains multiple financial periods.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Fiscal Year Name"))
    start_date = models.DateField(unique=True, verbose_name=_("Start Date"))
    end_date = models.DateField(unique=True, verbose_name=_("End Date"))
    is_closed = models.BooleanField(default=False, verbose_name=_("Is Closed"))

    class Meta:
        db_table = 'fiscal_years'
        verbose_name = _("Fiscal Year")
        verbose_name_plural = _("Fiscal Years")
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Start date cannot be after end date."))


class FinancialPeriod(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        PENDING_CLOSE = 'pending_close', _('Pending Close')
        CLOSED = 'closed', _('Closed')
        PERMANENTLY_LOCKED = 'locked', _('Permanently Locked')

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT,
        related_name='periods', verbose_name=_("Fiscal Year")
    )
    name = models.CharField(max_length=100, verbose_name=_("Period Name"))
    start_date = models.DateField(unique=True, verbose_name=_("Start Date"))
    end_date = models.DateField(unique=True, verbose_name=_("End Date"))
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name=_("Status")
    )

    class Meta:
        db_table = 'financial_periods'
        verbose_name = _("Financial Period")
        verbose_name_plural = _("Financial Periods")
        ordering = ['-start_date']
        permissions = [
            ("can_reopen_period", "Can re-open a closed financial period"),
            ("can_permanently_lock_period", "Can permanently lock a financial period"),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date}) - {self.get_status_display()}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError(_("Start date cannot be after end date."))

class Account(models.Model):
    class AccountType(models.TextChoices):
        ASSET = 'asset', _('الأصول')
        LIABILITY = 'liability', _('الالتزامات')
        EQUITY = 'equity', _('حقوق الملكية')
        REVENUE = 'revenue', _('الإيرادات')
        EXPENSE = 'expense', _('المصروفات')

    name = models.CharField(max_length=255, verbose_name=_("Account Name"))
    code = models.CharField(max_length=20, unique=True, verbose_name=_("Account Code"))
    account_type = models.CharField(max_length=20, choices=AccountType.choices, verbose_name=_("Account Type"))
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='children', verbose_name=_("Parent Account")
    )
    # --- NEW FIELDS ---
    is_control_account = models.BooleanField(
        default=False,
        verbose_name=_("Is Control Account"),
        help_text=_("Designates if this account requires a sub-ledger entry (e.g., A/R, A/P).")
    )
    sub_ledger_model = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        null=True, blank=True,
        verbose_name=_("Sub-Ledger Model"),
        help_text=_("The model that acts as the sub-ledger for this account (e.g., Customer, Company).")
    )

    class Meta:
        db_table = 'chart_of_accounts'
        verbose_name = _("Account")
        verbose_name_plural = _("Chart of Accounts")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.is_control_account and not self.sub_ledger_model:
            raise ValidationError({
                'sub_ledger_model': _("A Sub-Ledger Model must be specified for control accounts.")
            })
        if not self.is_control_account and self.sub_ledger_model:
            raise ValidationError({
                'sub_ledger_model': _("Sub-Ledger Model should only be set for control accounts.")
            })

class JournalEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        POSTED = 'posted', _('Posted')

    date = models.DateTimeField(verbose_name=_("Date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.POSTED, verbose_name=_("Status")
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'journal_entries'
        verbose_name_plural = _("Journal Entries")
        ordering = ['-date']

    def __str__(self):
        return f"JE-{self.id} on {self.date.strftime('%Y-%m-%d')}: {self.description}"

    def is_balanced(self):
        """Checks if the sum of debits equals the sum of credits."""
        debits = self.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        credits = self.lines.filter(entry_type='credit').aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        return debits == credits

    def validate_balance(self):
        """
        Explicitly checks if the entry is balanced.
        This MUST be called by services after creating an entry and all its lines.
        """
        debits = self.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        credits = self.lines.filter(entry_type='credit').aggregate(total=Sum('amount'))['total'] or Decimal('0.0')

        if not abs(debits - credits) < Decimal('0.001'):
            raise ValidationError(
                _("The journal entry is not balanced. Debits (%(debits)s) do not equal Credits (%(credits)s).") % {
                    'debits': debits.quantize(Decimal('0.001')),
                    'credits': credits.quantize(Decimal('0.001'))
                }
            )

    def clean(self):
        """
        Validation for Django Admin and ModelForms.
        """
        super().clean()
        # This check is only useful if the instance has been saved and has lines.
        if self.pk and self.lines.exists():
            self.validate_balance()
                
    def get_description(self):
        """
        Provides a translated, user-friendly description of the journal entry's purpose
        based on its source object.
        """
        if not self.source_object:
            return self.description

        model_name = self.source_object._meta.model_name
        
        if model_name == 'inventorylog':
            return f"إثبات استلام مواد خام: {self.source_object.product.name} من {self.source_object.company.name} (فحص جودة: {self.source_object.qc_no})"
        
        if model_name == 'batch':
            return f"صرف مواد خام لدفعة إنتاج: {self.source_object.template.final_product.name} (أمر تشغيل: {self.source_object.shop_order_number})"

        if model_name == 'inventoryconsumption':
            return f"صرف داخلي: {self.source_object.quantity_consumed} {self.source_object.product.unit} من {self.source_object.product.name} إلى قسم {self.source_object.get_department_display()}"

        if model_name == 'finishedproductreceipt':
            return f"استلام منتج نهائي: {self.source_object.total_quantity_produced} {self.source_object.batch.template.final_product.unit} من {self.source_object.batch.template.final_product.name} (دفعة: {self.source_object.individual_batch_number})"

        if model_name == 'productionreturn':
            return f"مرتجع من الإنتاج: {self.source_object.quantity} {self.source_object.product.unit} من {self.source_object.product.name}"

        if model_name == 'finishedproductdispatch':
            return f"إثبات بيع وتسليم منتج نهائي: {self.source_object.quantity} {self.source_object.sales_order_item.finished_product.batch.template.final_product.unit} إلى {self.source_object.sales_order_item.sales_order.customer.name}"

        if model_name == 'payment':
            if self.source_object.payment_type == 'out':
                return f"سداد مورد: {self.source_object.supplier.name} بمبلغ {self.source_object.amount}"
            elif self.source_object.payment_type == 'in':
                return f"تحصيل من عميل: {self.source_object.customer.name} بمبلغ {self.source_object.amount}"

        if model_name == 'banktransfer':
            return f"تحويل بنكي من {self.source_object.from_account.name} إلى {self.source_object.to_account.name}"
            
        return self.description # Fallback to the original description

class JournalEntryLine(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = 'debit', _('مدين')
        CREDIT = 'credit', _('دائن')

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines', verbose_name=_("Journal Entry"))
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines', verbose_name=_("Account"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    entry_type = models.CharField(max_length=6, choices=EntryType.choices, verbose_name=_("Entry Type"))

    # --- NEW: Generic FK for Sub-Ledger ---
    sub_ledger_content_type = models.ForeignKey(
        ContentType, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Sub-Ledger Type")
    )
    sub_ledger_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name=_("Sub-Ledger ID"))
    sub_ledger_object = GenericForeignKey('sub_ledger_content_type', 'sub_ledger_object_id')

    class Meta:
        db_table = 'journal_entry_lines'
        verbose_name = _("Journal Entry Line")
        verbose_name_plural = _("Journal Entry Lines")
        ordering = ['journal_entry', 'entry_type']

    def __str__(self):
        return f"JE-{self.journal_entry.id}: {self.get_entry_type_display()} {self.account} for {self.amount}"

    def clean(self):
        super().clean()
        if self.account and self.account.is_control_account:
            # 1. A sub-ledger object must be provided.
            if not self.sub_ledger_object_id:
                raise ValidationError({
                    'sub_ledger_object_id': _("A sub-ledger entry is required for the control account '{account}'.")
                    .format(account=self.account.name)
                })
            
            # 2. The provided sub-ledger object's type must match the account's specified sub_ledger_model.
            if self.sub_ledger_content_type != self.account.sub_ledger_model:
                raise ValidationError({
                    'sub_ledger_content_type': _("The selected sub-ledger type '{provided_type}' does not match the required type '{required_type}' for the account '{account}'.")
                    .format(
                        provided_type=self.sub_ledger_content_type,
                        required_type=self.account.sub_ledger_model,
                        account=self.account.name
                    )
                })

class ProductTypeAccountingSettings(models.Model):
    product_type = models.CharField(
        max_length=50, choices=Product.ProductType.choices,
        unique=True, verbose_name=_("Product Type")
    )
    inventory_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        related_name='+', verbose_name=_("Default Inventory Account")
    )
    cogs_or_expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT,
        related_name='+', verbose_name=_("Default COGS/Expense Account")
    )
    # --- NEW FIELD ---
    sales_revenue_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name='+', verbose_name=_("Default Sales Revenue Account"),
        help_text=_("Required for 'Final Product' types.")
    )

    class Meta:
        db_table = 'product_type_acct_settings'
        verbose_name = _("Product Type Accounting Setting")
        verbose_name_plural = _("Product Type Accounting Settings")

    def __str__(self):
        return f"Settings for {self.get_product_type_display()}"

    def clean(self):
        """
        Ensures that if the product type is 'Final Product', a sales revenue
        account is provided.
        """
        if self.product_type == Product.ProductType.FINAL_PRODUCT and not self.sales_revenue_account:
            raise ValidationError({
                'sales_revenue_account': _("A default sales revenue account is required for 'Final Product' types.")
            })
        


# --- NEW ---
class GeneralAccountingSettings(models.Model):
    """
    A singleton model to hold system-wide accounting configuration.
    This prevents hardcoding account codes in the business logic.
    """
    accounts_payable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', 
        verbose_name=_("Default Accounts Payable (A/P) Account"),
        help_text=_("e.g., '20201 - حسابات الموردين (ذمم دائنة)'")
    )
    accounts_receivable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', 
        verbose_name=_("Default Accounts Receivable (A/R) Account"),
        help_text=_("e.g., '10203 - حسابات العملاء (ذمم مدينة)'")
    )
    vat_receivable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', 
        verbose_name=_("VAT on Inputs (Receivable) Account"),
        help_text=_("e.g., '1020404 - ضريبة القيمة المضافة (المدخلات)'")
    )
    vat_payable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', 
        verbose_name=_("VAT on Outputs (Payable) Account"),
        help_text=_("The liability account for VAT collected from sales.")
    )
    wip_inventory = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', 
        verbose_name=_("Work-in-Progress (WIP) Inventory Account"),
        help_text=_("e.g., '102020205 - مخزون انتاج تحت التشغيل'")
    )
    withholding_tax_payable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Withholding Tax Payable Account"),
        help_text=_("The liability account for withholding tax deducted from supplier payments."),
        null=True, blank=True
    )
    # --- NEW FIELD ---
    finished_goods_inventory = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Finished Goods (FG) Inventory Account"),
        help_text=_("e.g., '1020206 - مخزون منتج نهائي'")
    )
    # --- NEW INVENTORY ADJUSTMENT ACCOUNTS ---
    inventory_adjustment_loss_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Inventory Adjustment Loss Account"),
        help_text=_("The expense account for inventory shortages/shrinkage."),
        null=True, blank=True
    )
    inventory_adjustment_gain_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Inventory Adjustment Gain Account"),
        help_text=_("The revenue/other income account for inventory overages."),
        null=True, blank=True
    )
    purchase_returns_clearing_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Purchase Returns Clearing Account"),
        help_text=_("e.g., '20207 - تسوية مرتجعات موردين'"),
        null=True, blank=True
    )
    # --- NEW: EMPLOYEE ADVANCES CONTROL ACCOUNT ---
    employee_advances_receivable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Employee Advances Receivable Account"),
        help_text=_("The asset account for tracking money given to employees."),
        null=True, blank=True
    )
    # --- NEW FIELDS FOR ADVANCED TRANSACTIONS ---
    customer_deposits_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Customer Deposits / Deferred Revenue Account")
    )
    sales_returns_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Sales Returns & Allowances Account")
    )
    # --- NEW: CLEARING ACCOUNTS ---
    landed_costs_clearing_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Landed Costs Clearing Account"),
        help_text=_("A temporary account to hold landed costs before they are allocated to inventory.")
    )
    purchase_returns_clearing_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Purchase Returns Clearing Account"),
        help_text=_("A temporary account to hold the value of returned goods before a debit memo is issued.")
    )
    sales_returns_clearing_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Sales Returns Clearing Account"),
        help_text=_("A temporary account to balance COGS reversal and final disposition of returns.")
    )
    prepaid_expenses_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Prepaid Expenses Account")
    )
    accrued_expenses_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Accrued Expenses Account")
    )
    damaged_goods_expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Damaged Goods / Scrap Expense Account")
    )
    # --- NEW: GRNI & PPV ACCOUNTS ---
    goods_received_not_invoiced_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Goods Received Not Invoiced (GRNI) Account"),
        help_text=_("A temporary liability account for received goods before the supplier invoice is posted.")
    )
    purchase_price_variance_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Purchase Price Variance (PPV) Account"),
        help_text=_("An expense account to record differences between PO price and actual invoice price.")
    )
    landed_costs_clearing_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+', null=True, blank=True,
        verbose_name=_("Landed Costs Clearing Account"),
        help_text=_("A temporary account to hold third-party landed costs before they are allocated to inventory.")
    )

    class Meta:
        db_table = 'general_accounting_settings'
        verbose_name = _("General Accounting Setting")
        verbose_name_plural = _("General Accounting Settings")

    def __str__(self):
        return str(_("General Accounting Settings"))

    def save(self, *args, **kwargs):
        # Enforce that only one instance of this model can exist
        if not self.pk and GeneralAccountingSettings.objects.exists():
            raise ValidationError(_('There can only be one instance of General Accounting Settings.'))
        return super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        # Convenience method to get the single instance
        with transaction.atomic():
            # Use a fixed pk to ensure singleton behavior
            obj, created = cls.objects.get_or_create(pk=1)
        return obj
