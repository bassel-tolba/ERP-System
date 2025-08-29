from django.db import models
from django.utils.translation import gettext_lazy as _


class Company(models.Model):
    """
    Represents a company or supplier of materials.
    Maps to the 'companies' table.
    """
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Company Name"))

    class Meta:
        db_table = 'companies'  # Explicitly map to the existing table
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
        # CORRECTED: Set the display name to Arabic to match the UI.
        RAW_MATERIAL = 'مواد خام', _('مواد خام')
        PACKAGING = 'تعبئه و تغليف', _('تعبئه و تغليف')
        FINAL_PRODUCT = 'منتج نهائي', _('منتج نهائي')

    name = models.CharField(max_length=255, verbose_name=_("Product Name"))
    code = models.CharField(max_length=100, unique=True, verbose_name=_("Product Code"))
    product_type = models.CharField(
        max_length=50,
        choices=ProductType.choices,
        verbose_name=_("Product Type")
    )
    unit = models.CharField(max_length=50, verbose_name=_("Unit of Measurement"))

    class Meta:
        db_table = 'products'  # Explicitly map to the existing table
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class InventoryLog(models.Model):
    """
    Represents a single transaction in the inventory log, such as receiving materials.
    Maps to the 'inventory_log' table.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
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
    quantity = models.FloatField(verbose_name=_("Quantity"))
    timestamp = models.DateTimeField(verbose_name=_("Timestamp"))
    qc_no = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_("QC Number")
    )

    class Meta:
        db_table = 'inventory_log'  # Explicitly map to the existing table
        verbose_name = _("Inventory Log")
        verbose_name_plural = _("Inventory Logs")
        ordering = ['-timestamp']

    def __str__(self):
        return f"Log #{self.id}: {self.quantity} {self.product.unit} of {self.product.name}"


class ShopOrderTemplate(models.Model):
    """
    Represents a template or "recipe" for a final product.
    Maps to the 'shop_order_templates' table.
    """
    name = models.CharField(max_length=255, verbose_name=_("Template Name"))
    final_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='templates',
        verbose_name=_("Final Product")
    )

    class Meta:
        db_table = 'shop_order_templates'  # Explicitly map to the existing table
        verbose_name = _("Shop Order Template")
        verbose_name_plural = _("Shop Order Templates")
        ordering = ['name']

    def __str__(self):
        return self.name


class TemplateItem(models.Model):
    """
    Represents a single "ingredient" line item within a ShopOrderTemplate.
    Maps to the 'template_items' table.
    """
    template = models.ForeignKey(
        ShopOrderTemplate,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Template")
    )
    primitive_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='template_items',
        verbose_name=_("Primitive Product")
    )
    theoretical_quantity = models.FloatField(verbose_name=_("Theoretical Quantity"))

    class Meta:
        db_table = 'template_items'  # Explicitly map to the existing table
        verbose_name = _("Template Item")
        verbose_name_plural = _("Template Items")

    def __str__(self):
        return f"{self.theoretical_quantity} {self.primitive_product.unit} of {self.primitive_product.name} for {self.template.name}"


class Batch(models.Model):
    """
    Represents an actual production batch created from a ShopOrderTemplate.
    Maps to the 'batches' table.
    """
    template = models.ForeignKey(
        ShopOrderTemplate,
        on_delete=models.PROTECT,
        related_name='batches',
        verbose_name=_("Template")
    )
    shop_order_number = models.CharField(max_length=255, verbose_name=_("Shop Order Number"))
    batch_number = models.CharField(max_length=255, verbose_name=_("Batch Number"))
    creation_date = models.DateTimeField(verbose_name=_("Creation Date"))
    is_customized = models.BooleanField(default=False, verbose_name=_("Is Customized"))
    is_continuation = models.BooleanField(default=False, verbose_name=_("Is Continuation"))
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'batches'  # Explicitly map to the existing table
        verbose_name = _("Batch")
        verbose_name_plural = _("Batches")
        ordering = ['-creation_date', '-id']

    def __str__(self):
        return f"Batch {self.batch_number} (SO: {self.shop_order_number})"


class BatchItem(models.Model):
    """
    Represents an actual material used in a specific production Batch.
    Maps to the 'batch_items' table.
    """
    class SourceType(models.TextChoices):
        OPENING_BALANCE = 'opening_balance', _('Opening Balance')
        INVENTORY_LOG = 'inventory_log', _('Inventory Log')

    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Batch")
    )
    primitive_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='batch_items',
        verbose_name=_("Primitive Product")
    )
    theoretical_quantity = models.FloatField(verbose_name=_("Theoretical Quantity"))
    actual_quantity = models.FloatField(null=True, blank=True, verbose_name=_("Actual Quantity"))
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        verbose_name=_("Source Type")
    )
    source_log = models.ForeignKey(
        InventoryLog,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='batch_items',
        verbose_name=_("Source Inventory Log")
    )

    class Meta:
        db_table = 'batch_items'  # Explicitly map to the existing table
        verbose_name = _("Batch Item")
        verbose_name_plural = _("Batch Items")

    def __str__(self):
        return f"{self.actual_quantity or 0} {self.primitive_product.unit} of {self.primitive_product.name} in {self.batch}"


class OpeningBalance(models.Model):
    """
    Represents the starting inventory balance for a product on a specific date.
    Maps to the 'opening_balances' table.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='opening_balances',
        verbose_name=_("Product")
    )
    quantity = models.FloatField(verbose_name=_("Quantity"))
    balance_date = models.DateTimeField(verbose_name=_("Balance Date"))

    class Meta:
        db_table = 'opening_balances'  # Explicitly map to the existing table
        verbose_name = _("Opening Balance")
        verbose_name_plural = _("Opening Balances")
        ordering = ['product__name', '-balance_date']

    def __str__(self):
        return f"Opening Balance for {self.product.name} on {self.balance_date.date()}: {self.quantity}"


class ProductionReturn(models.Model):
    """
    Represents a quantity of material returned from production back to inventory.
    Maps to the 'production_returns' table.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='production_returns',
        verbose_name=_("Product")
    )
    source_log = models.ForeignKey(
        InventoryLog,
        on_delete=models.CASCADE,
        related_name='production_returns',
        verbose_name=_("Original Source Log")
    )
    quantity = models.FloatField(verbose_name=_("Quantity Returned"))
    return_date = models.DateTimeField(verbose_name=_("Return Date"))
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'production_returns'  # Explicitly map to the existing table
        verbose_name = _("Production Return")
        verbose_name_plural = _("Production Returns")
        ordering = ['-return_date']

    def __str__(self):
        return f"Return of {self.quantity} {self.product.unit} of {self.product.name}"