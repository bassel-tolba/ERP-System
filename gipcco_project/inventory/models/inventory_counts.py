# gipcco_project/inventory/models/inventory_counts.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings

from .operational import Product, InventoryLog
from .inventory_management import FinishedProductReceipt
from .accounting_sub_ledger import SalesReturnItem


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
        'InventoryCount', on_delete=models.CASCADE,
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
            return 0.0
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
        SHRINKAGE = 'shrinkage', _('نقص/خسارة')
        DAMAGE = 'damage', _('بضاعة تالفة')
        DATA_ENTRY_ERROR = 'data_entry_error', _('تصحيح خطأ إدخال بيانات')
        OVERAGE_FOUND = 'overage_found', _('زيادة وجدت أثناء الجرد')
        SALES_RETURN_STOCK = 'sales_return_stock', _('إرجاع إلى المخزون من المبيعات')
        RETURN_TO_SUPPLIER = 'return_to_supplier', _('مرتجع إلى المورد')
        OTHER = 'other', _('أخرى')

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
    source_sales_return_item = models.OneToOneField(
        'inventory.SalesReturnItem',
        on_delete=models.CASCADE,
        related_name='inventory_adjustment',
        verbose_name=_("Source Sales Return Item"),
        null=True,
        blank=True
    )
    source_purchase_return_item = models.OneToOneField(
        'inventory.PurchaseReturnItem',
        on_delete=models.CASCADE,
        related_name='inventory_adjustment',
        verbose_name=_("Source Purchase Return Item"),
        null=True,
        blank=True
    )
    
    # --- Context ---
    inventory_count = models.ForeignKey(
        'InventoryCount',
        on_delete=models.CASCADE,
        related_name='adjustments',
        verbose_name=_("Inventory Count Event"),
        null=True, # Allow adjustments outside of a formal count
        blank=True
    )

    class Meta:
        ordering = ['-adjustment_date']
        db_table = 'inventory_adjustments'
        verbose_name = _("Inventory Adjustment")
        verbose_name_plural = _("Inventory Adjustments")

    def clean(self):
        sources = [
            self.source_log,
            self.source_finished_product,
            self.source_sales_return_item,
            self.source_purchase_return_item
        ]
        if sum(s is not None for s in sources) > 1:
            raise ValidationError(_("An adjustment can only be linked to one source (Log, FP Receipt, Sales Return, or Purchase Return)."))
        if all(s is None for s in sources):
            # Allow adjustments outside of a formal count, but require a source
            if not self.inventory_count:
                 raise ValidationError(_("An adjustment must be linked to a source if not part of a formal inventory count."))

    def __str__(self):
        direction = _("Shortage") if self.adjustment_quantity < 0 else _("Overage")
        return f"{direction} of {abs(self.adjustment_quantity)} for {self.product.name}"
