from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

# ==============================================================================
#  OPERATIONAL MODELS
# ==============================================================================

class Company(models.Model):
    """
    Represents a company or supplier of materials.
    Maps to the 'companies' table.
    """
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Company Name"))

    class Meta:
        db_table = 'companies'
        verbose_name = _("Company")
        verbose_name_plural = _("Companies")
        ordering = ['name']

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Represents a product, which can be a raw material, packaging, or a final product.
    Maps to the 'products' table.
    """
    class ProductType(models.TextChoices):
        RAW_MATERIAL = 'RAW_MATERIAL', _('Raw Material')
        PACKAGING = 'PACKAGING', _('Packaging')
        FINAL_PRODUCT = 'FINAL_PRODUCT', _('Final Product')
        MRO = 'MRO', _('MRO (Maintenance, Repair, Operations)')
        CONSUMABLE = 'CONSUMABLE', _('Consumable')

    name = models.CharField(max_length=255, verbose_name=_("Product Name"))
    code = models.CharField(max_length=100, unique=True, verbose_name=_("Product Code"))
    product_type = models.CharField(
        max_length=50,
        choices=ProductType.choices,
        verbose_name=_("Product Type")
    )
    unit = models.CharField(max_length=50, verbose_name=_("Unit of Measurement"))
    tags = models.ManyToManyField('ProductTag', blank=True, verbose_name=_("Tags"))
    moving_average_cost = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Moving Average Cost")
    )

    # --- NEW ACCOUNTING OVERRIDE FIELDS ---
    override_inventory_account = models.ForeignKey(
        'Account', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Override Inventory Account")
    )
    override_cogs_expense_account = models.ForeignKey(
        'Account', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Override COGS/Expense Account")
    )
    # --- NEW FIELD ---
    override_sales_revenue_account = models.ForeignKey(
        'Account', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Override Sales Revenue Account")
    )

    # --- NEW FIELD ---
    is_amortizable = models.BooleanField(
        default=False,
        verbose_name=_("Is Amortizable"),
        help_text=_("If checked, consuming this item will create a prepaid asset to be amortized over time.")
    )

    class Meta:
        db_table = 'products'
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class ProductTag(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Tag Name"))

    class Meta:
        db_table = 'product_tags'
        verbose_name = _("Product Tag")
        verbose_name_plural = _("Product Tags")
        ordering = ['name']

    def __str__(self):
        return self.name


class InventoryLog(models.Model):
    class Status(models.TextChoices):
        QUARANTINED = 'quarantined', _('تحت الفحص')
        RELEASED = 'released', _('مفرج عنه')
        REJECTED = 'rejected', _('مرفوض')
        SCRAPPED = 'scrapped', _('خردة') # --- NEW STATUS ---
        VOIDED = 'voided', _('ملغي') # --- NEW STATUS ---
    
    class VatTreatment(models.TextChoices):
        RECOVERABLE = 'recoverable', _('ضريبة قابلة للخصم')
        CAPITALIZED = 'capitalized', _('تضاف للتكلفة')
        
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT, # Prevent deletion if referenced for data integrity
        related_name='inventory_logs',
        verbose_name=_("Product")
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_logs',
        verbose_name=_("Company")
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=4, verbose_name=_("Quantity"))
    timestamp = models.DateTimeField(verbose_name=_("Timestamp"))
    qc_no = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("QC Number")
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUARANTINED,
        verbose_name=_("Status")
    )
    release_timestamp = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Release Timestamp")
    )
    po_item = models.ForeignKey(
        'PurchaseOrderItem',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts',
        verbose_name=_("Purchase Order Item")
    )
    tags = models.ManyToManyField(
        'ProductTag',
        blank=True,
        verbose_name=_("Tags"),
        related_name='inventory_logs'
    )
    
    base_unit_price = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Base Unit Price (before VAT)")
    )
    vat_amount = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_("VAT Amount")
    )
    vat_treatment = models.CharField(
        max_length=20,
        choices=VatTreatment.choices,
        default=VatTreatment.RECOVERABLE,
        verbose_name=_("VAT Treatment")
    )
    withholding_tax_amount = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Withholding Tax Amount")
    )

    class Meta:
        db_table = 'inventory_log'
        verbose_name = _("Inventory Log")
        verbose_name_plural = _("Inventory Logs")
        ordering = ['-timestamp']

    def __str__(self):
        return f"Log #{self.id}: {self.quantity} {self.product.unit} of {self.product.name}"
    
    # --- NEW: Link to Employee ---
    employee = models.ForeignKey(
        'Employee',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='inventory_receipts',
        verbose_name=_("Responsible Employee")
    )

    # --- NEW: Stored cost fields for accurate, persistent costing ---
    costing_unit_price = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'),
        verbose_name=_("Costing Unit Price"),
        help_text=_("The final unit cost for inventory valuation, including capitalized VAT and landed costs.")
    )
    landed_cost_component = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'),
        verbose_name=_("Landed Cost Component"),
        help_text=_("The portion of the unit price that is from allocated landed costs.")
    )

    @property
    def total_cost(self):
        return (self.base_unit_price or Decimal('0.0')) * Decimal(str(self.quantity or 0.0))
