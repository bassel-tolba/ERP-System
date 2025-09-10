# gipcco_project/inventory/models.py

from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError


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
        RAW_MATERIAL = 'مواد خام', _('مواد خام')
        PACKAGING = 'تعبئه و تغليف', _('تعبئه و تغليف')
        FINAL_PRODUCT = 'منتج نهائي', _('منتج نهائي')
        MRO = 'قطع غيار و صيانة', _('قطع غيار و صيانة')
        CONSUMABLE = 'مستهلكات', _('مستهلكات')

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
    
    class VatTreatment(models.TextChoices):
        RECOVERABLE = 'recoverable', _('ضريبة قابلة للخصم')
        CAPITALIZED = 'capitalized', _('تضاف للتكلفة')
        
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

    class Meta:
        db_table = 'inventory_log'
        verbose_name = _("Inventory Log")
        verbose_name_plural = _("Inventory Logs")
        ordering = ['-timestamp']

    def __str__(self):
        return f"Log #{self.id}: {self.quantity} {self.product.unit} of {self.product.name}"
    
    @property
    def costing_unit_price(self):
        """Calculates the unit price used for inventory valuation (MAC)."""
        if self.quantity == 0:
            return Decimal('0.000')
        
        total_base_price = self.base_unit_price * Decimal(str(self.quantity))
        
        if self.vat_treatment == self.VatTreatment.CAPITALIZED:
            total_cost = total_base_price + self.vat_amount
        else: # Recoverable
            total_cost = total_base_price
            
        return (total_cost / Decimal(str(self.quantity))).quantize(Decimal('0.001'))


class ShopOrderTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Template Name"))
    final_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='templates',
        verbose_name=_("Final Product")
    )

    class Meta:
        db_table = 'shop_order_templates'
        verbose_name = _("Shop Order Template")
        verbose_name_plural = _("Shop Order Templates")
        ordering = ['name']

    def __str__(self):
        return self.name


class TemplateItem(models.Model):
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
        db_table = 'template_items'
        verbose_name = _("Template Item")
        verbose_name_plural = _("Template Items")

    def __str__(self):
        return f"{self.theoretical_quantity} {self.primitive_product.unit} of {self.primitive_product.name} for {self.template.name}"


class Batch(models.Model):
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
    parent_batch = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='continuation_batches', verbose_name=_("Parent Batch (for continuations)")
    )

    class Meta:
        db_table = 'batches'
        verbose_name = _("Batch")
        verbose_name_plural = _("Batches")
        ordering = ['-creation_date', '-id']

    def __str__(self):
        return f"Batch {self.batch_number} (SO: {self.shop_order_number})"

    @property
    def number_of_batches_in_plan(self):
        parts = str(self.batch_number).split('-')
        try:
            start_str = parts[0]
            end_str = parts[-1]
            start = int(''.join(filter(str.isdigit, start_str)))
            end = int(''.join(filter(str.isdigit, end_str))) if len(parts) > 1 and parts[-1] else start
            
            if end >= start:
                return (end - start) + 1
            return 1
        except (ValueError, IndexError):
            return 1


class BatchItem(models.Model):
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
    cost_at_consumption = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True, verbose_name=_("Cost at Consumption")
    )

    class Meta:
        db_table = 'batch_items'
        verbose_name = _("Batch Item")
        verbose_name_plural = _("Batch Items")

    def __str__(self):
        return f"{self.actual_quantity or 0} {self.primitive_product.unit} of {self.primitive_product.name} in {self.batch}"


class OpeningBalance(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='opening_balances',
        verbose_name=_("Product")
    )
    quantity = models.FloatField(verbose_name=_("Quantity"))
    balance_date = models.DateTimeField(verbose_name=_("Balance Date"))
    total_value = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Total Value")
    )

    class Meta:
        db_table = 'opening_balances'
        verbose_name = _("Opening Balance")
        verbose_name_plural = _("Opening Balances")
        ordering = ['product__name', '-balance_date']

    def __str__(self):
        return f"Opening Balance for {self.product.name} on {self.balance_date.date()}: {self.quantity}"

    @property
    def unit_cost(self):
        if self.quantity > 0:
            return (self.total_value / Decimal(str(self.quantity))).quantize(Decimal('0.001'))
        return Decimal('0.000')


class ProductionReturn(models.Model):
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
        db_table = 'production_returns'
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
    
    base_price_per_unit = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Base Price Per Unit")
    )
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("VAT Rate (e.g., 0.14 for 14%)")
    )
    withholding_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("Withholding Tax Rate (e.g., 0.01 for 1%)")
    )

    class Meta:
        db_table = 'purchase_order_items'
        verbose_name = _("Purchase Order Item")
        verbose_name_plural = _("Purchase Order Items")

    def __str__(self):
        return f"{self.quantity_ordered} of {self.product.name} for PO #{self.purchase_order.po_number}"


class FinishedProductReceipt(models.Model):
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

    def __str__(self):
        return f"Receipt for Batch #{self.individual_batch_number} from Plan {self.batch.shop_order_number}"


class ReceiptSubBatch(models.Model):
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
    

class Customer(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name=_("Customer Name"))
    address = models.TextField(blank=True, null=True, verbose_name=_("Address"))
    contact_info = models.TextField(blank=True, null=True, verbose_name=_("Contact Info"))

    class Meta:
        db_table = 'customers'
        verbose_name = _("Customer")
        verbose_name_plural = _("Customers")
        ordering = ['name']

    def __str__(self):
        return self.name


class SalesOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending Shipment')
        PARTIALLY_SHIPPED = 'partially_shipped', _('Partially Shipped')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='sales_orders',
        verbose_name=_("Customer")
    )
    order_date = models.DateField(verbose_name=_("Order Date"))
    so_number = models.CharField(max_length=100, unique=True, verbose_name=_("Sales Order Number"))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'sales_orders'
        verbose_name = _("Sales Order")
        verbose_name_plural = _("Sales Orders")
        ordering = ['-order_date']

    def __str__(self):
        return f"SO #{self.so_number} for {self.customer.name}"


class SalesOrderItem(models.Model):
    sales_order = models.ForeignKey(
        SalesOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name=_("Sales Order")
    )
    finished_product = models.ForeignKey(
        FinishedProductReceipt,
        on_delete=models.PROTECT,
        related_name='sales_items',
        verbose_name=_("Finished Product Batch")
    )
    quantity_ordered = models.FloatField(verbose_name=_("Quantity Ordered"))
    
    base_price_per_unit = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Base Price Per Unit"))
    vat_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'), verbose_name=_("VAT Rate (e.g., 0.14 for 14%)")
    )

    @property
    def total_price(self):
        return (Decimal(str(self.quantity_ordered)) * self.base_price_per_unit).quantize(Decimal('0.001'))

    class Meta:
        db_table = 'sales_order_items'
        verbose_name = _("Sales Order Item")
        verbose_name_plural = _("Sales Order Items")

    def __str__(self):
        return f"{self.quantity_ordered} of Batch #{self.finished_product.individual_batch_number} for {self.sales_order}"


class FinishedProductDispatch(models.Model):
    sales_order_item = models.ForeignKey(
        SalesOrderItem,
        on_delete=models.PROTECT,
        related_name='dispatches',
        verbose_name=_("Sales Order Item")
    )
    quantity = models.FloatField(verbose_name=_("Quantity Dispatched"))
    dispatch_date = models.DateTimeField(verbose_name=_("Dispatch Date"))
    cost_at_dispatch = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Cost at Dispatch")
    )

    class Meta:
        db_table = 'finished_product_dispatches'
        verbose_name = _("Finished Product Dispatch")
        verbose_name_plural = _("Finished Product Dispatches")
        ordering = ['-dispatch_date']

    def __str__(self):
        return f"Dispatched {self.quantity} for {self.sales_order_item}"


class InventoryConsumption(models.Model):
    class Department(models.TextChoices):
        PRODUCTION = 'production', _('الإنتاج')
        ENGINEERING = 'engineering', _('الهندسة والصيانة')
        ADMIN = 'admin', _('الإدارة')
        QC = 'qc', _('الجودة')
        OTHER = 'other', _('أخرى')
        
    # --- NEW: Consumption Type for Capitalization vs. Expense ---
    class ConsumptionType(models.TextChoices):
        EXPENSE = 'expense', _('Expense (Repair)')
        CAPITALIZE = 'capitalize', _('Capitalize (Enhancement)')

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='consumptions',
        verbose_name=_("Product")
    )
    source_log = models.ForeignKey(
        InventoryLog,
        on_delete=models.PROTECT,
        related_name='consumptions',
        verbose_name=_("Source Inventory Log")
    )
    quantity_consumed = models.FloatField(verbose_name=_("Quantity Consumed"))
    consumption_date = models.DateTimeField(verbose_name=_("Consumption Date"))
    department = models.CharField(
        max_length=50,
        choices=Department.choices,
        verbose_name=_("Department")
    )
    cost_at_consumption = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Cost at Consumption")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    
    # --- NEW FIELDS TO SUPPORT ADVANCED LOGIC ---
    consumption_type = models.CharField(
        max_length=20, choices=ConsumptionType.choices, default=ConsumptionType.EXPENSE,
        verbose_name=_("Consumption Type")
    )
    fixed_asset = models.ForeignKey(
        'FixedAsset', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consumptions', verbose_name=_("Target Fixed Asset (if capitalized)")
    )
    
    class Meta:
        db_table = 'inventory_consumptions'
        verbose_name = _("Inventory Consumption")
        verbose_name_plural = _("Inventory Consumptions")
        ordering = ['-consumption_date']

    def __str__(self):
        return f"Consumed {self.quantity_consumed} of {self.product.name} by {self.get_department_display()}"
    
    def clean(self):
        # Enforce that a fixed asset must be selected if type is 'Capitalize'
        if self.consumption_type == self.ConsumptionType.CAPITALIZE and not self.fixed_asset:
            raise ValidationError({
                'fixed_asset': _("A fixed asset must be selected when the consumption type is 'Capitalize'.")
            })
        # Enforce that MRO/Consumable products are used
        if self.product and self.product.product_type not in [Product.ProductType.MRO, Product.ProductType.CONSUMABLE]:
             raise ValidationError({
                'product': _("Only MRO and Consumable products can be used in internal consumption.")
            })


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

    description = models.CharField(max_length=255, verbose_name=_("Description"))
    expense_date = models.DateField(verbose_name=_("Expense Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    category = models.CharField(
        max_length=50,
        choices=Category.choices,
        verbose_name=_("Category")
    )
    classification = models.CharField(
        max_length=50,
        choices=Classification.choices,
        verbose_name=_("Classification")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'expense_logs'
        verbose_name = _("General Expense Log")
        verbose_name_plural = _("General Expense Logs")
        ordering = ['-expense_date']

    def __str__(self):
        return f"Expense: {self.description} for {self.amount} on {self.expense_date}"
    
    
# ==============================================================================
#  NEW SUB-LEDGER & BANKING MODELS
# ==============================================================================

class FixedAsset(models.Model):
    """
    Represents an individual fixed asset. This is the Fixed Asset Sub-Ledger.
    """
    class AssetStatus(models.TextChoices):
        IN_SERVICE = 'in_service', _('In Service')
        UNDER_CONSTRUCTION = 'under_construction', _('Under Construction')
        IDLE = 'idle', _('Idle')
        SOLD = 'sold', _('Sold')
        RETIRED = 'retired', _('Retired/Scrapped')

    asset_tag = models.CharField(max_length=100, unique=True, verbose_name=_("Asset Tag / Barcode"))
    name = models.CharField(max_length=255, verbose_name=_("Asset Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    
    gl_account = models.ForeignKey(
        'Account',
        on_delete=models.PROTECT,
        limit_choices_to={'code__startswith': '101'}, # All Fixed Asset accounts start with 101
        related_name='fixed_assets',
        verbose_name=_("GL Control Account")
    )
    
    purchase_date = models.DateField(verbose_name=_("Purchase Date"))
    purchase_cost = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Original Purchase Cost"))
    depreciation_start_date = models.DateField(verbose_name=_("Depreciation Start Date"))
    useful_life_years = models.PositiveIntegerField(verbose_name=_("Useful Life (Years)"))
    salvage_value = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Salvage Value")
    )

    serial_number = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Serial Number"))
    location = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Location"))
    status = models.CharField(
        max_length=20,
        choices=AssetStatus.choices,
        default=AssetStatus.IN_SERVICE,
        verbose_name=_("Status")
    )

    class Meta:
        db_table = 'fixed_assets'
        verbose_name = _("Fixed Asset")
        verbose_name_plural = _("Fixed Assets")
        ordering = ['asset_tag']

    def __str__(self):
        return f"{self.asset_tag} - {self.name}"

class BankAccount(models.Model):
    """
    Represents a company bank account or a physical cash box (safe).
    """
    name = models.CharField(max_length=255, verbose_name=_("Bank/Cash Box Name"))
    currency = models.CharField(max_length=10, default='EGP', verbose_name=_("Currency"))
    
    gl_account = models.OneToOneField(
        'Account',
        on_delete=models.PROTECT,
        limit_choices_to={'code__startswith': '10201'}, # Cash and Banks accounts start with 10201
        verbose_name=_("GL Control Account")
    )

    class Meta:
        db_table = 'bank_accounts'
        verbose_name = _("Bank Account / Cash Box")
        verbose_name_plural = _("Bank Accounts / Cash Boxes")
        ordering = ['name']

    def __str__(self):
        return self.name

class Payment(models.Model):
    """
    Represents a payment transaction, either money in or money out.
    """
    class PaymentType(models.TextChoices):
        PAYMENT_OUT = 'out', _('Payment Made (to Supplier)')
        PAYMENT_IN = 'in', _('Payment Received (from Customer)')
        TRANSFER = 'transfer', _('Bank Transfer')
        OTHER = 'other', _('Other Transaction')

    payment_date = models.DateField(verbose_name=_("Payment Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='payments', verbose_name=_("Bank/Cash Account"))
    payment_type = models.CharField(max_length=10, choices=PaymentType.choices, verbose_name=_("Payment Type"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    
    supplier = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name=_("Supplier"))
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name=_("Customer"))
    
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'payments'
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment of {self.amount} on {self.payment_date}"

class Employee(models.Model):
    """
    Represents an employee, acts as a sub-ledger for employee-related accounts.
    """
    employee_id = models.CharField(max_length=50, unique=True, verbose_name=_("Employee ID"))
    first_name = models.CharField(max_length=100, verbose_name=_("First Name"))
    last_name = models.CharField(max_length=100, verbose_name=_("Last Name"))
    job_title = models.CharField(max_length=255, blank=True, null=True, verbose_name=_("Job Title"))
    is_active = models.BooleanField(default=True, verbose_name=_("Is Active"))

    class Meta:
        db_table = 'employees'
        verbose_name = _("Employee")
        verbose_name_plural = _("Employees")
        ordering = ['last_name', 'first_name']

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.full_name


# ==============================================================================
#  ACCOUNTING CORE MODELS
# ==============================================================================

class FinancialPeriod(models.Model):
    name = models.CharField(max_length=100, verbose_name=_("Period Name"))
    start_date = models.DateField(unique=True, verbose_name=_("Start Date"))
    end_date = models.DateField(unique=True, verbose_name=_("End Date"))
    is_closed = models.BooleanField(default=False, verbose_name=_("Is Closed"))

    class Meta:
        db_table = 'financial_periods'
        verbose_name = _("Financial Period")
        verbose_name_plural = _("Financial Periods")
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"

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

    class Meta:
        db_table = 'chart_of_accounts'
        verbose_name = _("Account")
        verbose_name_plural = _("Chart of Accounts")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

class JournalEntry(models.Model):
    date = models.DateTimeField(verbose_name=_("Date"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'journal_entries'
        verbose_name = _("Journal Entry")
        verbose_name_plural = _("Journal Entries")
        ordering = ['-date']

    def __str__(self):
        return f"JE-{self.id} on {self.date.strftime('%Y-%m-%d')}: {self.description}"

class JournalEntryLine(models.Model):
    class EntryType(models.TextChoices):
        DEBIT = 'debit', _('مدين')
        CREDIT = 'credit', _('دائن')

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name='lines', verbose_name=_("Journal Entry"))
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines', verbose_name=_("Account"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    entry_type = models.CharField(max_length=6, choices=EntryType.choices, verbose_name=_("Entry Type"))

    class Meta:
        db_table = 'journal_entry_lines'
        verbose_name = _("Journal Entry Line")
        verbose_name_plural = _("Journal Entry Lines")
        ordering = ['journal_entry', 'entry_type']

    def __str__(self):
        return f"JE-{self.journal_entry.id}: {self.get_entry_type_display()} {self.account} for {self.amount}"

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
        # Enforce that final products must have a revenue account set.
        if self.product_type == Product.ProductType.FINAL_PRODUCT and not self.sales_revenue_account:
            raise ValidationError({
                'sales_revenue_account': _("A default sales revenue account is required for the 'Final Product' type.")
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
        help_text=_("e.g., '1020205 - مخزون انتاج تحت التشغيل'")
    )
    # --- NEW FIELD ---
    finished_goods_inventory = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Finished Goods (FG) Inventory Account"),
        help_text=_("e.g., '1020206 - مخزون منتج نهائي'")
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