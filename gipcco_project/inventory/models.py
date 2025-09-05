

from django.db import models
from django.utils.translation import gettext_lazy as _
from decimal import Decimal

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
    tags = models.ManyToManyField('ProductTag', blank=True, verbose_name=_("Tags"))
    # --- NEW FIELD ---
    moving_average_cost = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Moving Average Cost")
    )

    class Meta:
        db_table = 'products'  # Explicitly map to the existing table
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class ProductTag(models.Model):
    """
    Represents a tag that can be assigned to products.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Tag Name"))

    class Meta:
        db_table = 'product_tags'
        verbose_name = _("Product Tag")
        verbose_name_plural = _("Product Tags")
        ordering = ['name']

    def __str__(self):
        return self.name


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
    # --- NEW FIELD ---
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True, verbose_name=_("Unit Price")
    )
    # --- NEW FIELD ---
    po_item = models.ForeignKey(
        'PurchaseOrderItem',
        on_delete=models.SET_NULL, # Set to PROTECT after data migration
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

    # --- NEW PROPERTY ---
    @property
    def number_of_batches_in_plan(self):
        """Calculates how many individual batches are represented by this record."""
        parts = str(self.batch_number).split('-')
        try:
            # Handle non-numeric parts gracefully if they exist but are not part of the range
            start_str = parts[0]
            end_str = parts[-1]
            start = int(''.join(filter(str.isdigit, start_str)))
            end = int(''.join(filter(str.isdigit, end_str))) if len(parts) > 1 and parts[-1] else start
            
            if end >= start:
                return (end - start) + 1
            return 1 # Fallback for malformed ranges like 105-101
        except (ValueError, IndexError):
            return 1 # If parsing fails, assume it's a single batch


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

    # --- NEW FIELD ---
    cost_at_consumption = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True, verbose_name=_("Cost at Consumption")
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

    # --- MODIFIED FIELD ---
    total_value = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Total Value")
    )

    class Meta:
        db_table = 'opening_balances'  # Explicitly map to the existing table
        verbose_name = _("Opening Balance")
        verbose_name_plural = _("Opening Balances")
        ordering = ['product__name', '-balance_date']

    def __str__(self):
        return f"Opening Balance for {self.product.name} on {self.balance_date.date()}: {self.quantity}"
    # --- NEW PROPERTY ---
    @property
    def unit_cost(self):
        """Calculates the effective unit cost from the total value and quantity."""
        if self.quantity > 0:
            return (self.total_value / Decimal(str(self.quantity))).quantize(Decimal('0.001'))
        return Decimal('0.000')


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
    
    
class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PARTIALLY_RECEIVED = 'partially_received', _('Partially Received')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    po_number = models.CharField(max_length=100, unique=True, verbose_name=_("PO Number"))
    supplier = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name='purchase_orders',
        verbose_name=_("Supplier")
    )
    order_date = models.DateField(verbose_name=_("Order Date"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Status")
    )

    class Meta:
        db_table = 'purchase_orders'
        verbose_name = _("Purchase Order")
        verbose_name_plural = _("Purchase Orders")
        ordering = ['-order_date']

    def __str__(self):
        return f"PO #{self.po_number} from {self.supplier.name}"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Purchase Order")
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='po_items',
        verbose_name=_("Product")
    )
    quantity_ordered = models.FloatField(verbose_name=_("Quantity Ordered"))
    
    total_price = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Total Price")
    )

    class Meta:
        db_table = 'purchase_order_items'
        verbose_name = _("Purchase Order Item")
        verbose_name_plural = _("Purchase Order Items")

    def __str__(self):
        return f"{self.quantity_ordered} of {self.product.name} for PO #{self.purchase_order.po_number}"

    @property
    def effective_unit_price(self):
        """
        Calculates the unit price based on the total price and total quantity received.
        This is the value that should be used for inventory costing.
        """
        total_quantity_received = InventoryLog.objects.filter(po_item=self).aggregate(total=models.Sum('quantity'))['total'] or 0.0
        
        if total_quantity_received > 0:
            return (self.total_price / Decimal(str(total_quantity_received))).quantize(Decimal('0.001'))
        
        if self.quantity_ordered > 0:
             return (self.total_price / Decimal(str(self.quantity_ordered))).quantize(Decimal('0.001'))
        
        return Decimal('0.000')

# --- NEW FINISHED PRODUCT MODELS ---

class FinishedProductReceipt(models.Model):
    """
    Represents the receipt of a finished product from a production run.
    """
    class MarketType(models.TextChoices):
        LOCAL = 'local', _('محلي')
        EXPORT = 'export', _('تصدير')

    class Status(models.TextChoices):
        QUARANTINED = 'quarantined', _('تحت الفحص')
        RELEASED = 'released', _('مفرج عنه')
        REJECTED = 'rejected', _('مرفوض')

    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        related_name='receipts',
        verbose_name=_("Production Plan")
    )
    individual_batch_number = models.CharField(
        max_length=255, verbose_name=_("Individual Batch Number")
    )
    receipt_date = models.DateField(verbose_name=_("Receipt Date"))
    total_cost = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Total Cost of Batch")
    )
    total_quantity_produced = models.FloatField(
        verbose_name=_("Total Quantity Produced")
    )
    market_type = models.CharField(
        max_length=10,
        choices=MarketType.choices,
        default=MarketType.LOCAL,
        verbose_name=_("Market Type")
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUARANTINED,
        verbose_name=_("Status")
    )
    release_date = models.DateField(
        null=True, blank=True, verbose_name=_("Release Date")
    )
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'finished_product_receipts'
        verbose_name = _("Finished Product Receipt")
        verbose_name_plural = _("Finished Product Receipts")
        ordering = ['-receipt_date', '-id']
        unique_together = ['batch', 'individual_batch_number']

    def __str__(self):
        return f"Receipt for Batch #{self.individual_batch_number} from Plan {self.batch.shop_order_number}"


class ReceiptSubBatch(models.Model):
    """

    Represents a physical sub-batch (e.g., a pallet or container) of a finished product receipt.
    """
    receipt = models.ForeignKey(
        FinishedProductReceipt,
        on_delete=models.CASCADE,
        related_name='sub_batches',
        verbose_name=_("Parent Receipt")
    )
    sub_batch_identifier = models.CharField(
        max_length=100, verbose_name=_("Sub-Batch Identifier")
    )
    quantity = models.FloatField(verbose_name=_("Quantity in Sub-Batch"))

    class Meta:
        db_table = 'receipt_sub_batches'
        verbose_name = _("Receipt Sub-Batch")
        verbose_name_plural = _("Receipt Sub-Batches")

    def __str__(self):
        return f"{self.quantity} units in {self.sub_batch_identifier} for {self.receipt}"