from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

class ShopOrderTemplate(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Template Name"))
    final_product = models.ForeignKey(
        'Product',
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
        'Product',
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

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING_APPROVAL = 'pending_approval', _('Pending Approval')
        APPROVED = 'approved', _('Approved')
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT,
        verbose_name=_("Status")
    )

    # --- NEW: Approval workflow fields ---
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='submitted_batches',
        verbose_name=_("Submitted By")
    )
    submitted_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Submitted At")
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_batches',
        verbose_name=_("Approved By")
    )
    approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Approved At")
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
        'Product',
        on_delete=models.CASCADE,
        related_name='batch_items',
        verbose_name=_("Primitive Product")
    )
    theoretical_quantity = models.FloatField(verbose_name=_("Theoretical Quantity"))
    actual_quantity = models.FloatField(null=True, blank=True, verbose_name=_("Actual Quantity"))
    source_log = models.ForeignKey(
        'InventoryLog',
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
        'Product',
        on_delete=models.CASCADE,
        related_name='production_returns',
        verbose_name=_("Product")
    )
    source_log = models.ForeignKey(
        'InventoryLog',
        on_delete=models.CASCADE,
        related_name='production_returns',
        verbose_name=_("Original Source Log")
    )
    batch = models.ForeignKey(
        'Batch',
        on_delete=models.CASCADE,
        related_name='production_returns',
        verbose_name=_("Source Batch"),
        null=True, blank=True # Allow null for returns not from a specific batch
    )
    quantity = models.FloatField(verbose_name=_("Quantity Returned"))
    return_date = models.DateTimeField(verbose_name=_("Return Date"))
    notes = models.TextField(null=True, blank=True, verbose_name=_("Notes"))

    class Status(models.TextChoices):
        POSTED = 'posted', _('Posted')
        CANCELLED = 'cancelled', _('Cancelled')

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.POSTED,
        verbose_name=_("Status")
    )

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
        'Company',
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
        'Product',
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
    # --- NEW: For percentage-based allocation of PO-level landed costs ---
    landed_cost_allocation_percentage = models.DecimalField(
        max_digits=7, decimal_places=4, default=Decimal('0.0000'),
        verbose_name=_("Landed Cost Allocation %"),
        help_text=_("The percentage of the PO's total landed costs to allocate to this line item.")
    )
    is_closed = models.BooleanField(
        default=False,
        verbose_name=_("Is Closed"),
        help_text=_("Indicates that no further receipts are expected for this line item, even if under-delivered.")
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
        CANCELLED = 'cancelled', _('ملغي')

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
    class Status(models.TextChoices):
        COMPLETED = 'completed', _('Completed')
        CANCELLED = 'cancelled', _('Cancelled')

    sales_order_item = models.ForeignKey(
        SalesOrderItem,
        on_delete=models.PROTECT,
        related_name='dispatches',
        verbose_name=_("Sales Order Item")
    )
    finished_product = models.ForeignKey(
        FinishedProductReceipt,
        on_delete=models.PROTECT,
        related_name='dispatches',
        verbose_name=_("Finished Product Batch")
    )
    quantity = models.FloatField(verbose_name=_("Quantity Dispatched"))
    dispatch_date = models.DateTimeField(verbose_name=_("Dispatch Date"))
    cost_at_dispatch = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Cost at Dispatch")
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.COMPLETED, verbose_name=_("Status")
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
        PRODUCTION = 'Production', _('Production')
        ENGINEERING = 'Engineering', _('Engineering')
        QUALITY_CONTROL = 'Quality Control', _('Quality Control')
        WAREHOUSE = 'Warehouse', _('Warehouse')
        
    # --- NEW: Consumption Type for Capitalization vs. Expense ---
    class ConsumptionType(models.TextChoices):
        EXPENSE = 'Expense', _('Expense')
        CAPITALIZE = 'Capitalize', _('Capitalize')
        AMORTIZE = 'Amortize', _('Amortize')

    product = models.ForeignKey(
        'Product',
        on_delete=models.PROTECT,
        related_name='consumptions',
        verbose_name=_("Product")
    )
    source_log = models.ForeignKey(
        'InventoryLog',
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
    cost_pool = models.ForeignKey(
        'CostPool',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='consumptions',
        verbose_name=_("Direct Expense Cost Pool"),
        help_text=_("For non-amortizable items, select a cost pool to directly expense this consumption to.")
    )
    source_request = models.OneToOneField(
        'ExpenseRequest',
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='final_consumption',
        help_text=_("The approved request that triggered this consumption.")
    )
    
    class Meta:
        db_table = 'inventory_consumptions'
        verbose_name = _("Inventory Consumption")
        verbose_name_plural = _("Inventory Consumptions")
        ordering = ['-consumption_date']

    def __str__(self):
        return f"{self.quantity_consumed} of {self.product.name} on {self.consumption_date.date()}"
    
    def clean(self):
        from .operational import Product
        """
        Custom validation to ensure that:
        1. If consumption_type is 'Capitalize', a fixed_asset must be linked.
        2. If consumption_type is 'Expense', the product must be of a suitable type.
        3. If consumption_type is 'Amortize', the product must be marked as amortizable.
        """
        # Validation 1: Capitalization requires a fixed asset
        if self.consumption_type == self.ConsumptionType.CAPITALIZE:
            if not self.fixed_asset:
                raise ValidationError(
                    {'fixed_asset': _("A fixed asset must be selected when capitalizing consumption.")}
                )
        # Validation 2: Expense consumption is only for certain product types
        elif self.consumption_type == self.ConsumptionType.EXPENSE:
            allowed_types = [
                Product.ProductType.MRO,
            ]
            if self.product and self.product.product_type not in allowed_types:
                raise ValidationError(
                    _("Internal consumption as an expense is only allowed for 'MRO' product types. '%(product_name)s' is a '%(product_type)s'.") % {
                        'product_name': self.product.name,
                        'product_type': self.product.get_product_type_display()
                    }
                )
        # Validation 3: Amortization requires an amortizable product
        elif self.consumption_type == self.ConsumptionType.AMORTIZE:
            if not self.product or not self.product.is_amortizable:
                raise ValidationError(
                    {'consumption_type': _("The 'Amortize' consumption type can only be used with products marked as amortizable.")}
                )
