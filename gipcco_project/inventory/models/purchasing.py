from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from .inventory_management import PurchaseOrderItem

# ==============================================================================
#  PURCHASING & RETURNS MODELS
# ==============================================================================

class LandedCostType(models.Model):
    """
    Defines a type of landed cost that can be added to a shipment,
    e.g., 'Freight', 'Customs Duty', 'Insurance'.
    """
    name = models.CharField(max_length=100, unique=True, verbose_name=_("Landed Cost Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))

    class Meta:
        db_table = 'landed_cost_types'
        verbose_name = _("Landed Cost Type")
        verbose_name_plural = _("Landed Cost Types")

    def __str__(self):
        return self.name

class PurchaseReturn(models.Model):
    """
    Header model for a return of goods to a supplier.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        SHIPPED = 'shipped', _('Shipped')
        COMPLETED = 'completed', _('Completed')

    supplier = models.ForeignKey(
        'Company', on_delete=models.PROTECT, related_name='purchase_returns',
        verbose_name=_("Supplier")
    )
    return_date = models.DateField(verbose_name=_("Return Date"))
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    class Meta:
        db_table = 'purchase_returns'
        verbose_name = _("Purchase Return")
        verbose_name_plural = _("Purchase Returns")
        ordering = ['-return_date']

    def __str__(self):
        return f"Return to {self.supplier.name} on {self.return_date}"


class PurchaseReturnItem(models.Model):
    """
    Represents a single product being returned to a supplier.
    """
    purchase_return = models.ForeignKey(
        PurchaseReturn, on_delete=models.CASCADE, related_name='items',
        verbose_name=_("Purchase Return")
    )
    # Link to the original receipt to get cost and product info
    original_receipt = models.ForeignKey(
        'InventoryLog', on_delete=models.PROTECT, related_name='purchase_return_items',
        verbose_name=_("Original Receipt Log")
    )
    quantity_returned = models.FloatField(verbose_name=_("Quantity Returned"))

    class Meta:
        db_table = 'purchase_return_items'
        verbose_name = _("Purchase Return Item")
        verbose_name_plural = _("Purchase Return Items")

    def __str__(self):
        return f"{self.quantity_returned} of {self.original_receipt.product.name}"


class SupplierDebitMemo(models.Model):
    """
    Represents a debit memo issued to a supplier, typically for a purchase return.
    This is the financial document that confirms the reduction in Accounts Payable.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        OPEN = 'open', _('Open')
        APPLIED = 'applied', _('Applied')

    supplier = models.ForeignKey(
        'Company', on_delete=models.PROTECT, related_name='debit_memos',
        verbose_name=_("Supplier")
    )
    memo_number = models.CharField(max_length=100, verbose_name=_("Debit Memo Number"))
    memo_date = models.DateField(verbose_name=_("Memo Date"))
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Total Amount")
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN,
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    # Link to the source of the debit, e.g., a Purchase Return
    purchase_return = models.OneToOneField(
        PurchaseReturn, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='debit_memo', verbose_name=_("Source Purchase Return")
    )
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Journal Entry")
    )

    class Meta:
        db_table = 'supplier_debit_memos'
        verbose_name = _("Supplier Debit Memo")
        verbose_name_plural = _("Supplier Debit Memos")
        unique_together = ('supplier', 'memo_number')

    def __str__(self):
        return f"Debit Memo {self.memo_number} to {self.supplier.name}"


class LandedCostInvoice(models.Model):
    """
    Represents an invoice from a third-party (e.g., a shipping company)
    for landed costs that need to be applied to inventory receipts.
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        AWAITING_PAYMENT = 'awaiting_payment', _('Awaiting Payment')
        PAID = 'paid', _('Paid')

    vendor = models.ForeignKey(
        'Company', on_delete=models.PROTECT, related_name='landed_cost_invoices',
        verbose_name=_("Vendor")
    )
    invoice_number = models.CharField(max_length=100, verbose_name=_("Invoice Number"))
    invoice_date = models.DateField(verbose_name=_("Invoice Date"))
    total_amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Total Amount"))
    status = models.CharField(
        max_length=25, choices=Status.choices, default=Status.DRAFT,
        verbose_name=_("Status")
    )
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Journal Entry")
    )
    # --- NEW: Optional link to PO for variance calculation ---
    purchase_order = models.ForeignKey(
        'PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='landed_cost_invoices', verbose_name=_("Related Purchase Order")
    )

    class Meta:
        db_table = 'landed_cost_invoices'
        verbose_name = _("Landed Cost Invoice")
        verbose_name_plural = _("Landed Cost Invoices")
        unique_together = ('vendor', 'invoice_number')

    def __str__(self):
        return f"Landed Cost Invoice {self.invoice_number} from {self.vendor.name}"


class LandedCostInvoiceItem(models.Model):
    """
    A line item on a LandedCostInvoice, linking a specific cost type and amount.
    """
    landed_cost_invoice = models.ForeignKey(
        LandedCostInvoice, on_delete=models.CASCADE, related_name='items',
        verbose_name=_("Landed Cost Invoice")
    )
    cost_type = models.ForeignKey(
        LandedCostType, on_delete=models.PROTECT,
        verbose_name=_("Cost Type")
    )
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))

    class Meta:
        db_table = 'landed_cost_invoice_items'
        verbose_name = _("Landed Cost Invoice Item")
        verbose_name_plural = _("Landed Cost Invoice Items")

    def __str__(self):
        return f"{self.cost_type.name}: {self.amount}"


class PurchaseOrderLandedCost(models.Model):
    """
    Stores an estimated landed cost for an entire Purchase Order.
    This is the core of the NetSuite-style estimation-first approach.
    """
    purchase_order = models.ForeignKey(
        'PurchaseOrder', on_delete=models.CASCADE, related_name='landed_costs',
        verbose_name=_("Purchase Order")
    )
    cost_type = models.ForeignKey(
        LandedCostType, on_delete=models.PROTECT,
        verbose_name=_("Landed Cost Type")
    )
    estimated_amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Estimated Amount")
    )

    class Meta:
        db_table = 'po_landed_costs'
        verbose_name = _("PO Landed Cost Estimate")
        verbose_name_plural = _("PO Landed Cost Estimates")
        unique_together = ('purchase_order', 'cost_type')

    def __str__(self):
        return f"Estimate for {self.cost_type.name}: {self.estimated_amount}"
