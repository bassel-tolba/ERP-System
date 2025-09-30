# gipcco_project/inventory/models.py

from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
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

    @property
    def total_cost(self):
        return (self.base_unit_price or Decimal('0.0')) * Decimal(str(self.quantity or 0.0))

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
    # --- NEW: Field for bottle size ---
    bottle_size_ml = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Bottle Size (mL)"),
        help_text=_("For overhead allocation based on volume, enter the size of a single bottle/unit in milliliters.")
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
    """
    IMPORTANT LOGIC NOTES FOR DEVELOPERS:
    This model represents a production plan or "Shop Order". It can be a standard plan
    or a "continuation" of a previous plan.

    - `is_continuation` & `parent_batch`:
      - If `is_continuation` is True, this batch represents an additional consumption
        of raw materials for a production plan that was already started.
      - The `parent_batch` field MUST be set to the original Batch this one continues.
      - Continuation batches share the same Shop Order Number as their parent.

    - Business Logic Constraints:
      1. RECEIVING FINISHED GOODS: Finished products should ONLY be received against the
         original (parent) batch, i.e., where `is_continuation` is False. Continuation
         batches are only for tracking extra material costs. The backend logic for
         receiving finished goods MUST enforce this by checking `batch.is_continuation`.
      2. COSTING: The total cost of producing a finished good from a plan is the sum of
         the costs of the parent batch PLUS all of its `continuation_batches`.
         Reports and costing logic must aggregate these costs when calculating the
         final unit cost of the produced goods.
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
    parent_batch = models.ForeignKey(
        'self', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='continuation_batches', verbose_name=_("Parent Batch (for continuations)")
    )
    # --- NEW: Field for capturing allocation driver data ---
    machine_hours_consumed = models.FloatField(
        null=True, blank=True, verbose_name=_("Machine Hours Consumed"),
        help_text=_("Enter the actual machine hours used for this production run.")
    )
    # --- NEW: Field for labor hours ---
    labor_hours_consumed = models.FloatField(
        null=True, blank=True, verbose_name=_("Labor Hours Consumed"),
        help_text=_("Enter the actual labor hours used for this production run.")
    )

    class Meta:
        verbose_name = _("Production Plan")
        verbose_name_plural = _("Production Plans")
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
    """
    Represents the receipt of finished goods from a production batch.

    DEVELOPER NOTE ON CALCULATING REMAINING STOCK:
    A common requirement is to calculate the remaining (sellable) quantity
    of a finished product receipt. The correct formula is:
    `remaining = total_quantity_produced - total_dispatched + total_adjusted`

    A naive attempt to calculate this using Django's ORM might look like:
    ```python
    # !!! BUGGY - DO NOT USE !!!
    FinishedProductReceipt.objects.annotate(
        total_dispatched=Sum('sales_items__dispatches__quantity'),
        total_adjusted=Sum('adjustments__adjustment_quantity')
    )
    ```
    This approach is **WRONG** and will produce incorrect results due to the nature
    of SQL JOINs. If a receipt has multiple dispatches AND multiple adjustments,
    the database join will create a Cartesian product, causing each sum to be
    multiplied and massively inflated.

    THE CORRECT APPROACH is to use Subqueries to calculate each sum in isolation,
    preventing the join multiplication bug. Example:
    ```python
    from django.db.models import Subquery, OuterRef, Sum, FloatField
    from django.db.models.functions import Coalesce

    dispatched_subquery = FinishedProductDispatch.objects.filter(
        sales_order_item__finished_product_id=OuterRef('pk')
    ).values('sales_order_item__finished_product_id').annotate(total=Sum('quantity')).values('total')

    adjusted_subquery = InventoryAdjustment.objects.filter(
        source_finished_product_id=OuterRef('pk')
    ).values('source_finished_product_id').annotate(total=Sum('adjustment_quantity')).values('total')

    receipts = FinishedProductReceipt.objects.annotate(
        total_dispatched=Coalesce(Subquery(dispatched_subquery, output_field=FloatField()), 0.0),
        total_adjusted=Coalesce(Subquery(adjusted_subquery, output_field=FloatField()), 0.0)
    ).annotate(
        quantity_available=F('total_quantity_produced') - F('total_dispatched') + F('total_adjusted')
    )
    ```
    This robust method should be used in any API, view, or service that needs
    to accurately determine the available stock of a finished product receipt.
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
    allocated_overhead_cost = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'),
        verbose_name=_("Allocated Overhead Cost"),
        help_text=_("The portion of manufacturing overhead applied to this receipt.")
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


class FixedAsset(models.Model):
    """
    Represents an individual fixed asset. This is the Fixed Asset Sub-Ledger.
    """
    class AssetStatus(models.TextChoices):
        IN_SERVICE = 'in_service', _("In Service")
        UNDER_CONSTRUCTION = 'under_construction', _("Under Construction")
        IDLE = 'idle', _("Idle")
        SOLD = 'sold', _("Sold")
        RETIRED = 'retired', _("Retired")

    asset_tag = models.CharField(max_length=100, unique=True, verbose_name=_("Asset Tag / Barcode"))
    name = models.CharField(max_length=255, verbose_name=_("Asset Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    
    # --- CORRECTED LINES ---
    gl_account = models.ForeignKey(
        'Account', # Use a string here
        on_delete=models.PROTECT,
        limit_choices_to={'code__startswith': '101'},
        related_name='fixed_assets',
        verbose_name=_("GL Control Account")
    )
    
    depreciation_expense_account = models.ForeignKey(
        'Account', # Use a string here
        on_delete=models.PROTECT,
        limit_choices_to={'account_type': 'expense'}, # The value should also be a string
        related_name='+', 
        verbose_name=_("Depreciation Expense Account")
    )
    accumulated_depreciation_account = models.ForeignKey(
        'Account', # Use a string here
        on_delete=models.PROTECT,
        limit_choices_to={'code__startswith': '20205'},
        related_name='+', 
        verbose_name=_("Accumulated Depreciation Account")
    )
    # --- END CORRECTIONS ---
    
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

    @property
    def depreciable_base(self):
        return self.purchase_cost - self.salvage_value

    @property
    def accumulated_depreciation(self):
        return self.depreciation_logs.aggregate(total=Sum('amount'))['total'] or Decimal('0.000')

    @property
    def net_book_value(self):
        return self.purchase_cost - self.accumulated_depreciation


class InventoryConsumption(models.Model):
    class Department(models.TextChoices):
        PRODUCTION = 'production', _("Production")
        ENGINEERING = 'engineering', _("Engineering and Maintenance")
        ADMIN = 'admin', _("Administration")
        QC = 'qc', _("Quality Control")
        OTHER = 'other', _("Other")
        
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


# --- MODIFICATION TO EXISTING 'Payment' MODEL ---
# Find your 'Payment' model and add the 'source_object' generic foreign key.
# This is not strictly required by the plan but is excellent practice for traceability.
# We also add a property to check if it's applied.

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

    # --- NEW: Generic FK for source, e.g., link to a specific bank transfer record ---
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    # --- NEW RECONCILIATION FIELDS ---
    reconciliation = models.ForeignKey(
        'BankReconciliation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payments', verbose_name=_("Bank Reconciliation")
    )
    cleared_date = models.DateField(null=True, blank=True, verbose_name=_("Cleared Date"))


    class Meta:
        db_table = 'payments'
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        ordering = ['-payment_date']

    def __str__(self):
        return f"Payment of {self.amount} on {self.payment_date}"
    
    @property
    def total_applied(self):
        """Total amount applied to SUPPLIER invoices."""
        return self.applications.aggregate(total=models.Sum('amount_applied'))['total'] or Decimal('0.000')

    # --- NEW PROPERTY FOR A/R ---
    @property
    def total_received_applied(self):
        """Total amount applied to CUSTOMER invoices."""
        return self.customer_applications.aggregate(total=models.Sum('amount_applied'))['total'] or Decimal('0.000')

    @property
    def unapplied_amount(self):
        if self.payment_type == self.PaymentType.PAYMENT_OUT:
            return self.amount - self.total_applied
        elif self.payment_type == self.PaymentType.PAYMENT_IN:
            return self.amount - self.total_received_applied
        return self.amount # For transfers etc.
    
    
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

    # --- NEW: Balance Calculation Properties ---
    @property
    def total_advances(self):
        """Calculates the total amount of all advances given to the employee."""
        return self.advances.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.000')

    @property
    def total_settled_from_advances(self):
        """Calculates the total amount settled across all of the employee's advances."""
        return EmployeeAdvanceSettlement.objects.filter(advance__employee=self).aggregate(total=models.Sum('amount_settled'))['total'] or Decimal('0.000')

    @property
    def outstanding_advance_balance(self):
        """The net amount the employee still owes the company from advances."""
        return self.total_advances - self.total_settled_from_advances


# --- NEW: EMPLOYEE ADVANCE & SETTLEMENT MODELS ---

class EmployeeAdvance(models.Model):
    """
    Represents a single disbursement of funds to an employee, creating a receivable.
    This is the core of the Employee Financial Responsibility Sub-Ledger.
    """
    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        PARTIALLY_SETTLED = 'partially_settled', _('Partially Settled')
        SETTLED = 'settled', _('Settled')

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name='advances',
        verbose_name=_("Employee")
    )
    advance_date = models.DateField(verbose_name=_("Advance Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    
    # Link to the actual payment transaction that disbursed the cash
    source_payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name='employee_advance',
        verbose_name=_("Source Payment Transaction")
    )
    
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'employee_advances'
        verbose_name = _("Employee Advance")
        verbose_name_plural = _("Employee Advances")
        ordering = ['-advance_date']

    def __str__(self):
        return f"Advance of {self.amount} to {self.employee.full_name} on {self.advance_date}"

    @property
    def total_settled(self):
        """Calculates the total amount from this advance that has been settled."""
        return self.settlements.aggregate(total=models.Sum('amount_settled'))['total'] or Decimal('0.000')

    @property
    def unsettled_amount(self):
        return self.amount - self.total_settled

    def update_status(self, save=True):
        """Updates the advance status based on the settled amount."""
        if self.status == self.Status.SETTLED:
            return
            
        total_settled = self.total_settled
        if total_settled >= self.amount:
            self.status = self.Status.SETTLED
        elif total_settled > 0:
            self.status = self.Status.PARTIALLY_SETTLED
        else:
            self.status = self.Status.OPEN
        
        if save:
            self.save(update_fields=['status'])


class EmployeeAdvanceSettlement(models.Model):
    """
    A linking table that explicitly connects an expense or inventory receipt
    to an employee advance, acting as a justification for the funds spent.
    """
    advance = models.ForeignKey(
        EmployeeAdvance,
        on_delete=models.CASCADE,
        related_name='settlements',
        verbose_name=_("Employee Advance")
    )
    amount_settled = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount Settled"))
    settlement_date = models.DateField(auto_now_add=True, verbose_name=_("Settlement Date"))

    # Generic Foreign Key to the source transaction (InventoryLog or ExpenseLog)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    object_id = models.PositiveIntegerField()
    source_transaction = GenericForeignKey('content_type', 'object_id')

    class Meta:
        db_table = 'employee_advance_settlements'
        verbose_name = _("Employee Advance Settlement")
        verbose_name_plural = _("Employee Advance Settlements")
        ordering = ['-settlement_date']

    def __str__(self):
        return f"Settlement of {self.amount_settled} for {self.advance}"


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
        verbose_name = _("Journal Entry")
        verbose_name_plural = _("Journal Entries")
        ordering = ['-date']

    def __str__(self):
        return f"JE-{self.id} on {self.date.strftime('%Y-%m-%d')}: {self.description}"

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
    # --- NEW: EMPLOYEE ADVANCES CONTROL ACCOUNT ---
    employee_advances_receivable = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name='+',
        verbose_name=_("Employee Advances Receivable Account"),
        help_text=_("The asset account for tracking money given to employees."),
        null=True, blank=True
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
    
    
    
# ==============================================================================
#  NEW INVENTORY COUNT & ADJUSTMENT MODELS
# ==============================================================================

class InventoryCount(models.Model):
    """
    Header for a physical inventory counting event.
    """
    class CountStatus(models.TextChoices):
        IN_PROGRESS = 'in_progress', _('In Progress')
        PENDING_ALLOCATION = 'pending_allocation', _('Pending Allocation')
        COMPLETED = 'completed', _('Completed')

    count_date = models.DateField(verbose_name=_("Count Date"))
    status = models.CharField(
        max_length=20, choices=CountStatus.choices,
        default=CountStatus.IN_PROGRESS, verbose_name=_("Status")
    )
    reason = models.CharField(max_length=255, verbose_name=_("Reason for Count"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        verbose_name=_("Created By")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_counts'
        verbose_name = _("Inventory Count")
        verbose_name_plural = _("Inventory Counts")
        ordering = ['-count_date']

    def __str__(self):
        return f"Inventory Count on {self.count_date} ({self.get_status_display()})"


class InventoryCountItem(models.Model):
    """
    A single product line within an inventory count, capturing the state at that time.
    """
    inventory_count = models.ForeignKey(
        InventoryCount, on_delete=models.CASCADE,
        related_name='items', verbose_name=_("Inventory Count")
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='count_items', verbose_name=_("Product")
    )
    system_quantity = models.FloatField(verbose_name=_("System Quantity at Time of Count"))
    counted_quantity = models.FloatField(null=True, blank=True, verbose_name=_("Physically Counted Quantity"))

    @property
    def variance_quantity(self):
        if self.counted_quantity is None:
            return 0
        return self.counted_quantity - self.system_quantity

    class Meta:
        db_table = 'inventory_count_items'
        verbose_name = _("Inventory Count Item")
        verbose_name_plural = _("Inventory Count Items")
        unique_together = ('inventory_count', 'product')

    def __str__(self):
        return f"{self.product.name} in count {self.inventory_count.id}"


class InventoryAdjustment(models.Model):
    """
    An auditable record of a single, granular inventory adjustment against a specific stock source.
    """
    class ReasonCode(models.TextChoices):
        SHRINKAGE = 'shrinkage', _('Shrinkage/Loss')
        DAMAGE = 'damage', _('Damaged Goods')
        DATA_ENTRY_ERROR = 'data_entry_error', _('Data Entry Correction')
        OVERAGE_FOUND = 'overage_found', _('Overage Found During Count')
        OTHER = 'other', _('Other')

    product = models.ForeignKey(
        Product, on_delete=models.PROTECT,
        related_name='adjustments', verbose_name=_("Product")
    )
    adjustment_quantity = models.FloatField(
        verbose_name=_("Adjustment Quantity"),
        help_text=_("Use a negative number for shortages and a positive number for overages.")
    )
    adjustment_date = models.DateTimeField(verbose_name=_("Adjustment Date"))
    cost_at_adjustment = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Cost at Time of Adjustment")
    )
    reason_code = models.CharField(
        max_length=30, choices=ReasonCode.choices, verbose_name=_("Reason Code")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    
    # --- Source Linking ---
    source_log = models.ForeignKey(
        InventoryLog, on_delete=models.PROTECT, null=True, blank=True,
        related_name='adjustments', verbose_name=_("Source Inventory Log (Raw Material)")
    )
    source_finished_product = models.ForeignKey(
        FinishedProductReceipt, on_delete=models.PROTECT, null=True, blank=True,
        related_name='adjustments', verbose_name=_("Source Finished Product Receipt")
    )
    
    # --- Context ---
    inventory_count = models.ForeignKey(
        InventoryCount,
        on_delete=models.CASCADE,
        related_name='adjustments',
        verbose_name=_("Inventory Count Event")
    )

    class Meta:
        ordering = ['-adjustment_date']
        db_table = 'inventory_adjustments'
        verbose_name = _("Inventory Adjustment")
        verbose_name_plural = _("Inventory Adjustments")

    def clean(self):
        if self.source_log and self.source_finished_product:
            raise ValidationError(_("An adjustment can only be linked to one source (either an Inventory Log or a Finished Product Receipt)."))
        if not self.source_log and not self.source_finished_product:
            raise ValidationError(_("An adjustment must be linked to a source."))

    def __str__(self):
        direction = _("Shortage") if self.adjustment_quantity < 0 else _("Overage")
        return f"{direction} of {abs(self.adjustment_quantity)} for {self.product.name}"


# ==============================================================================
#  NEW OVERHEAD ALLOCATION MODELS
# ==============================================================================

class CostPool(models.Model):
    """
    A hierarchical model for defining overhead cost pools, similar to the Chart of Accounts.
    """
    name = models.CharField(max_length=255, verbose_name=_("Cost Pool Name"))
    code = models.CharField(max_length=20, unique=True, verbose_name=_("Cost Pool Code"))
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='children', verbose_name=_("Parent Cost Pool")
    )
    # --- NEW: Direct link to the GL account ---
    gl_account = models.ForeignKey(
        'Account',
        on_delete=models.PROTECT,
        related_name='cost_pools',
        verbose_name=_("GL Expense Account"),
        limit_choices_to={'account_type': Account.AccountType.EXPENSE},
        null=True, blank=True, # Allow parent pools to not have a direct account
        help_text=_("The specific expense account in the GL that this pool's costs are cleared to.")
    )

    class Meta:
        db_table = 'cost_pools'
        verbose_name = _("Cost Pool")
        verbose_name_plural = _("Cost Pools")
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # Generate a code only if one isn't provided and the instance is new
        if not self.code and not self.pk:
            if self.parent:
                # Logic for child pools
                last_child = CostPool.objects.filter(parent=self.parent).order_by('code').last()
                if last_child:
                    parts = last_child.code.split('-')
                    try:
                        new_suffix = int(parts[-1]) + 1
                        self.code = f"{self.parent.code}-{new_suffix:03d}"
                    except (ValueError, IndexError):
                        # Fallback if the last child has a weird code
                        self.code = f"{self.parent.code}-001"
                else:
                    # First child
                    self.code = f"{self.parent.code}-001"
            else:
                # Logic for top-level pools
                # Find the highest numeric code among top-level pools
                last_code = CostPool.objects.filter(parent__isnull=True)\
                    .exclude(code__exact='')\
                    .values_list('code', flat=True)
                
                max_code = 0
                for code in last_code:
                    try:
                        # Find the highest integer code, ignoring hierarchical ones
                        if '-' not in code:
                            max_code = max(max_code, int(code))
                    except (ValueError, TypeError):
                        continue # Ignore non-integer codes

                if max_code > 0:
                    self.code = str(max_code + 1)
                else:
                    # First ever valid top-level cost pool
                    self.code = "1000"
        
        super().save(*args, **kwargs)


class AllocationDriver(models.Model):
    """
    Represents a basis for allocating overhead costs, e.g., machine hours, labor hours.
    This is a master list of available drivers.
    """
    class DriverChoices(models.TextChoices):
        MACHINE_HOURS = 'Machine Hours', _('Machine Hours')
        LABOR_HOURS = 'Labor Hours', _('Labor Hours')
        BOTTLE_UNITS = 'Total Production Units (Bottles)', _('Total Production Units (Bottles)')
        LITERS_VOLUME = 'Total Production Volume (Liters)', _('Total Production Volume (Liters)')

    name = models.CharField(
        max_length=255,
        unique=True,
        choices=DriverChoices.choices,
        verbose_name=_("Driver Name")
    )
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))

    class Meta:
        db_table = 'allocation_drivers'
        verbose_name = _("Allocation Driver")
        verbose_name_plural = _("Allocation Drivers")

    def __str__(self):
        return self.get_name_display()


class OverheadAllocationRun(models.Model):
    """
    Records the execution and results of an overhead allocation for a specific period.
    This creates an auditable snapshot of the entire calculation.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        CALCULATED = 'calculated', _('Rate Calculated')
        POSTED = 'posted', _('Posted to GL')
        APPLIED = 'applied', _('Applied to Inventory')

    financial_period = models.ForeignKey(
        FinancialPeriod, on_delete=models.PROTECT, related_name='allocation_runs',
        verbose_name=_("Financial Period")
    )
    cost_pool = models.ForeignKey(
        CostPool, on_delete=models.PROTECT, related_name='allocation_runs',
        verbose_name=_("Cost Pool")
    )
    allocation_driver = models.ForeignKey(
        AllocationDriver, on_delete=models.PROTECT, related_name='allocation_runs',
        verbose_name=_("Allocation Driver")
    )
    
    total_pool_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.0'), verbose_name=_("Total Pool Amount for Period")
    )
    total_driver_units = models.FloatField(default=0.0, verbose_name=_("Total Driver Units for Period"))
    calculated_rate = models.DecimalField(
        max_digits=14, decimal_places=5, default=Decimal('0.0'), verbose_name=_("Calculated Overhead Rate")
    )
    
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name=_("Status")
    )
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Resulting Journal Entry")
    )
    # --- NEW: Link to the second JE that applies the cost from WIP to FG ---
    application_journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Inventory Application Journal Entry")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'overhead_allocation_runs'
        verbose_name = _("Overhead Allocation Run")
        verbose_name_plural = _("Overhead Allocation Runs")
        ordering = ['-financial_period__start_date', 'cost_pool__code']
        unique_together = ('financial_period', 'cost_pool')

    def __str__(self):
        return f"Allocation for {self.cost_pool.name} in {self.financial_period.name}"


# ==============================================================================
#  ACCOUNTING SUB-LEDGER DETAIL MODELS
# ==============================================================================

class SupplierInvoice(models.Model):
    """
    Represents an invoice received from a supplier, linking one or more
    inventory receipts to a single billable document.
    """
    class InvoiceStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        AWAITING_PAYMENT = 'awaiting_payment', _('Awaiting Payment')
        PARTIALLY_PAID = 'partially_paid', _('Partially Paid')
        PAID = 'paid', _('Paid')
        CANCELLED = 'cancelled', _('Cancelled')

    supplier = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name='invoices', verbose_name=_("Supplier")
    )
    invoice_number = models.CharField(max_length=255, verbose_name=_("Invoice Number"))
    invoice_date = models.DateField(verbose_name=_("Invoice Date"))
    due_date = models.DateField(verbose_name=_("Due Date"))
    
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Total Invoice Amount")
    )
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Amount Paid")
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.AWAITING_PAYMENT,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'supplier_invoices'
        verbose_name = _("Supplier Invoice")
        verbose_name_plural = _("Supplier Invoices")
        ordering = ['-invoice_date']
        unique_together = ('supplier', 'invoice_number')

    def __str__(self):
        return f"Invoice {self.invoice_number} from {self.supplier.name}"

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid

    def update_status(self, save=True):
        """Updates the invoice status based on the amount paid."""
        if self.status == self.InvoiceStatus.CANCELLED:
            return
            
        if self.amount_paid >= self.total_amount:
            self.status = self.InvoiceStatus.PAID
        elif self.amount_paid > 0:
            self.status = self.InvoiceStatus.PARTIALLY_PAID
        else:
            self.status = self.InvoiceStatus.AWAITING_PAYMENT
        
        if save:
            self.save(update_fields=['status', 'amount_paid'])


class SupplierInvoiceItem(models.Model):
    """Links a specific inventory receipt to a supplier invoice."""
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.CASCADE, related_name='items', verbose_name=_("Invoice")
    )
    # Using OneToOneField ensures a receipt can only be on ONE invoice.
    receipt = models.OneToOneField(
        InventoryLog, on_delete=models.PROTECT, related_name='invoice_item',
        verbose_name=_("Inventory Receipt (Log)")
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Amount for this item")
    )

    class Meta:
        db_table = 'supplier_invoice_items'
        verbose_name = _("Supplier Invoice Item")
        verbose_name_plural = _("Supplier Invoice Items")

    def __str__(self):
        return f"Item for receipt {self.receipt_id} on Invoice {self.invoice.invoice_number}"


class PaymentApplication(models.Model):
    """
    A linking table that details how much of a single payment was applied
    to a specific invoice. This is crucial for handling partial payments.
    """
    payment = models.ForeignKey(
        'Payment', on_delete=models.CASCADE, related_name='applications', verbose_name=_("Payment")
    )
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.PROTECT, related_name='applications', verbose_name=_("Invoice")
    )
    amount_applied = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount Applied"))
    application_date = models.DateField(auto_now_add=True, verbose_name=_("Application Date"))
    
    class Meta:
        db_table = 'payment_applications'
        verbose_name = _("Payment Application")
        verbose_name_plural = _("Payment Applications")


class CustomerInvoice(models.Model):
    """
    Represents an invoice sent to a customer, linking one or more
    dispatches to a single billable document.
    """
    class InvoiceStatus(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        AWAITING_PAYMENT = 'awaiting_payment', _('Awaiting Payment')
        PARTIALLY_PAID = 'partially_paid', _('Partially Paid')
        PAID = 'paid', _('Paid')
        CANCELLED = 'cancelled', _('Cancelled')

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='invoices', verbose_name=_("Customer")
    )
    invoice_number = models.CharField(max_length=255, verbose_name=_("Invoice Number"))
    invoice_date = models.DateField(verbose_name=_("Invoice Date"))
    due_date = models.DateField(verbose_name=_("Due Date"))
    
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Total Invoice Amount")
    )
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Amount Paid")
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.AWAITING_PAYMENT,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    sales_order = models.ForeignKey(
        SalesOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoices', verbose_name=_("Related Sales Order")
    )

    class Meta:
        db_table = 'customer_invoices'
        verbose_name = _("Customer Invoice")
        verbose_name_plural = _("Customer Invoices")
        ordering = ['-invoice_date']
        unique_together = ('customer', 'invoice_number')

    def __str__(self):
        return f"Invoice {self.invoice_number} to {self.customer.name}"

    @property
    def balance_due(self):
        return self.total_amount - self.amount_paid



    def update_status(self, save=True):
        """Updates the invoice status based on the amount paid."""
        if self.status == self.InvoiceStatus.CANCELLED:
            return
            
        if self.amount_paid >= self.total_amount:
            self.status = self.InvoiceStatus.PAID
        elif self.amount_paid > 0:
            self.status = self.InvoiceStatus.PARTIALLY_PAID
        else:
            self.status = self.InvoiceStatus.AWAITING_PAYMENT
        
        if save:
            self.save(update_fields=['status', 'amount_paid'])


class CustomerInvoiceItem(models.Model):
    """Links a specific dispatch to a customer invoice."""
    invoice = models.ForeignKey(
        CustomerInvoice, on_delete=models.CASCADE, related_name='items', verbose_name=_("Invoice")
    )
    dispatch = models.OneToOneField(
        FinishedProductDispatch, on_delete=models.PROTECT, related_name='invoice_item',
        verbose_name=_("Finished Product Dispatch")
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Amount for this item")
    )

    class Meta:
        db_table = 'customer_invoice_items'
        verbose_name = _("Customer Invoice Item")
        verbose_name_plural = _("Customer Invoice Items")

    def __str__(self):
        return f"Item for dispatch {self.dispatch_id} on Invoice {self.invoice.invoice_number}"


class CustomerPaymentApplication(models.Model):
    """Links a received Payment to a CustomerInvoice."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='customer_applications', verbose_name=_("Payment"))
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name='applications', verbose_name=_("Invoice"))
    amount_applied = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount Applied"))
    application_date = models.DateField(auto_now_add=True, verbose_name=_("Application Date"))

    class Meta:
        db_table = 'customer_payment_applications'
        verbose_name = _("Customer Payment Application")
        verbose_name_plural = _("Customer Payment Applications")

class BankTransfer(models.Model):
    """
    Represents the movement of funds between two internal bank accounts/cash boxes.
    """
    transfer_date = models.DateField(verbose_name=_("Transfer Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    source_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='transfers_out',
        verbose_name=_("Source Account (From)")
    )
    destination_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name='transfers_in',
        verbose_name=_("Destination Account (To)")
    )
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    # --- NEW RECONCILIATION FIELDS ---
    # We need two sets of fields because a transfer affects two reconciliations (one for each bank account)
    source_reconciliation = models.ForeignKey(
        'BankReconciliation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='source_transfers', verbose_name=_("Source Bank Reconciliation")
    )
    source_cleared_date = models.DateField(null=True, blank=True, verbose_name=_("Source Cleared Date"))
    
    destination_reconciliation = models.ForeignKey(
        'BankReconciliation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='destination_transfers', verbose_name=_("Destination Bank Reconciliation")
    )
    destination_cleared_date = models.DateField(null=True, blank=True, verbose_name=_("Destination Cleared Date"))


    class Meta:
        db_table = 'bank_transfers'
        verbose_name = _("Bank Transfer")
        verbose_name_plural = _("Bank Transfers")
    def clean(self):
        if self.source_account == self.destination_account:
            raise ValidationError(_("Source and destination accounts cannot be the same."))
        
        
class DepreciationLog(models.Model):
    """
    Logs a single depreciation event for a fixed asset for a specific period.
    This prevents double-posting depreciation for the same month.
    """
    asset = models.ForeignKey(
        FixedAsset, on_delete=models.CASCADE, related_name='depreciation_logs', verbose_name=_("Asset")
    )
    period_date = models.DateField(verbose_name=_("Period End Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Depreciation Amount"))
    journal_entry = models.ForeignKey(
        JournalEntry, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='depreciation_logs', verbose_name=_("Journal Entry")
    )

    class Meta:
        db_table = 'depreciation_logs'
        verbose_name = _("Depreciation Log")
        verbose_name_plural = _("Depreciation Logs")
        ordering = ['-period_date', 'asset']
        unique_together = ('asset', 'period_date') # Critical constraint

    def __str__(self):
        return f"Depreciation for {self.asset.name} on {self.period_date}"


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
        FinancialPeriod, on_delete=models.CASCADE,
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
    A checklist of mandatory tasks to be completed before a financial period can be closed.
    An instance of this is automatically created for each FinancialPeriod.
    """
    financial_period = models.OneToOneField(
        'FinancialPeriod',
        on_delete=models.CASCADE,
        related_name='checklist',
        verbose_name=_("Financial Period")
    )
    # --- Checklist Flags ---
    is_depreciation_run = models.BooleanField(
        default=False, verbose_name=_("Depreciation Run"),
        help_text=_("Has the monthly depreciation for all fixed assets been calculated and posted?")
    )
    is_overhead_posted = models.BooleanField(
        default=False, verbose_name=_("Overhead Allocated"),
        help_text=_("Has the manufacturing overhead been fully allocated and posted to WIP/FG?")
    )
    all_banks_reconciled = models.BooleanField(
        default=False, verbose_name=_("Banks Reconciled"),
        help_text=_("Have all bank accounts been reconciled for the period?")
    )
    no_draft_manual_jes = models.BooleanField(
        default=False, verbose_name=_("No Draft JEs"),
        help_text=_("Are there any manual journal entries still in 'Draft' status for this period?")
    )
    no_unposted_invoices = models.BooleanField(
        default=False, verbose_name=_("No Unposted Invoices"),
        help_text=_("Are there any supplier or customer invoices still in 'Draft' status for this period?")
    )
    # This is a placeholder for a more complex process, often done manually or with another system.
    is_inventory_valuation_run = models.BooleanField(
        default=True, verbose_name=_("Inventory Valuation Complete"),
        help_text=_("Is the period-end inventory valuation process complete? (Default: True)")
    )

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
        BankAccount, on_delete=models.PROTECT, related_name='reconciliations',
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