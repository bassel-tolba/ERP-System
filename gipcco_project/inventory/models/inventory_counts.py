# gipcco_project/inventory/models/inventory_counts.py

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings

from .operational import Product, InventoryLog
from .inventory_management import FinishedProductReceipt

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
        if self.source_log and self.source_finished_product:
            raise ValidationError(_("An adjustment can only be linked to one source (either an Inventory Log or a Finished Product Receipt)."))
        if not self.source_log and not self.source_finished_product:
            raise ValidationError(_("An adjustment must be linked to a source."))

    def __str__(self):
        direction = _("Shortage") if self.adjustment_quantity < 0 else _("Overage")
        return f"{direction} of {abs(self.adjustment_quantity)} for {self.product.name}"
