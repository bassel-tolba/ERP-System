from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

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
        'Company', on_delete=models.PROTECT, related_name='invoices', verbose_name=_("Supplier")
    )
    invoice_number = models.CharField(max_length=255, verbose_name=_("Invoice Number"))
    invoice_date = models.DateField(verbose_name=_("Invoice Date"))
    due_date = models.DateField(verbose_name=_("Due Date"))
    
    # --- MODIFIED: Fields to capture actual invoice values for 3-way match ---
    actual_subtotal = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True, verbose_name=_("Actual Subtotal (from Invoice)")
    )
    actual_vat = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True, verbose_name=_("Actual VAT (from Invoice)")
    )
    
    # This field will now be calculated from actual_subtotal + actual_vat upon posting.
    # It can also be populated by summing receipts for draft invoices.
    total_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Total Invoice Amount")
    )
    amount_paid = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'), verbose_name=_("Amount Paid")
    )
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT, # --- MODIFIED: Default to Draft ---
        verbose_name=_("Status")
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))

    # --- NEW: Link to the final JE created upon posting ---
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
        verbose_name=_("Posting Journal Entry")
    )

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
    receipt = models.ForeignKey(
        'InventoryLog', on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Inventory Receipt (Log)")
    )
    expense_log = models.ForeignKey(
        'ExpenseLog', on_delete=models.PROTECT, null=True, blank=True,
        verbose_name=_("Expense Log")
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=3, verbose_name=_("Amount for this item")
    )

    class Meta:
        db_table = 'supplier_invoice_items'
        verbose_name = _("Supplier Invoice Item")
        verbose_name_plural = _("Supplier Invoice Items")

    def __str__(self):
        return f"Item for Invoice {self.invoice.invoice_number} - Amount: {self.amount}"

    def clean(self):
        if self.receipt and self.expense_log:
            raise ValidationError(_("An invoice item can be linked to either a receipt or an expense log, not both."))
        if not self.receipt and not self.expense_log:
            raise ValidationError(_("An invoice item must be linked to either a receipt or an expense log."))


class PaymentApplication(models.Model):
    payment = models.ForeignKey('Payment', on_delete=models.CASCADE, related_name='applications', verbose_name=_("Payment"))
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='applications', verbose_name=_("Invoice"))
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
        'Customer', on_delete=models.PROTECT, related_name='invoices', verbose_name=_("Customer")
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
        'SalesOrder', on_delete=models.SET_NULL, null=True, blank=True,
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
        'FinishedProductDispatch', on_delete=models.PROTECT, related_name='invoice_item',
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
    payment = models.ForeignKey('Payment', on_delete=models.CASCADE, related_name='customer_applications', verbose_name=_("Payment"))
    invoice = models.ForeignKey(CustomerInvoice, on_delete=models.CASCADE, related_name='applications', verbose_name=_("Invoice"))
    amount_applied = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount Applied"))
    application_date = models.DateField(auto_now_add=True, verbose_name=_("Application Date"))

    class Meta:
        unique_together = ('payment', 'invoice')

class CustomerCreditMemo(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        OPEN = 'open', _('Open')
        PARTIALLY_APPLIED = 'partially_applied', _('Partially Applied')
        APPLIED = 'applied', _('Applied')

    customer = models.ForeignKey('Customer', on_delete=models.PROTECT, related_name='credit_memos')
    memo_number = models.CharField(max_length=100, unique=True)
    memo_date = models.DateField()
    base_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'),
        verbose_name=_("Base Amount (before VAT)")
    )
    vat_amount = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal('0.000'),
        verbose_name=_("VAT Amount")
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=3)
    unapplied_amount = models.DecimalField(max_digits=14, decimal_places=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True, null=True)
    # Link to the source of the credit, e.g., a Sales Return
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True)
    object_id = models.PositiveIntegerField(null=True)
    source_object = GenericForeignKey('content_type', 'object_id')

    def save(self, *args, **kwargs):
        # --- NEW: Calculate total_amount from base and VAT ---
        self.total_amount = (self.base_amount + self.vat_amount).quantize(Decimal('0.001'))
        if not self.pk: # On creation
            self.unapplied_amount = self.total_amount
        super().save(*args, **kwargs)


class SalesReturn(models.Model):
    class Status(models.TextChoices):
        PENDING_INSPECTION = 'pending_inspection', _('Pending Inspection')
        PENDING_PROCESSING = 'pending_processing', _('Pending Processing')
        COMPLETED = 'completed', _('Completed')

    customer = models.ForeignKey('Customer', on_delete=models.PROTECT, related_name='sales_returns')
    return_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_INSPECTION)
    # Optional link to original SO for traceability
    sales_order = models.ForeignKey('SalesOrder', on_delete=models.SET_NULL, null=True, blank=True)
    # --- NEW: Link to the JE that reverses COGS ---
    cogs_reversal_journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
        verbose_name=_("COGS Reversal Journal Entry")
    )

class SalesReturnItem(models.Model):
    class Disposition(models.TextChoices):
        RETURN_TO_STOCK = 'return_to_stock', _('Return to Stock')
        SCRAP = 'scrap', _('Scrap')

    sales_return = models.ForeignKey(SalesReturn, on_delete=models.CASCADE, related_name='items')
    # Link to the original dispatch to get cost and product info
    original_dispatch = models.ForeignKey(
        'FinishedProductDispatch',
        on_delete=models.PROTECT,
        related_name='return_items'
    )
    quantity_returned = models.FloatField()
    disposition = models.CharField(max_length=20, choices=Disposition.choices, null=True, blank=True)




class BankTransfer(models.Model):
    """
    Represents the movement of funds between two internal bank accounts/cash boxes.
    """
    transfer_date = models.DateField(verbose_name=_("Transfer Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Amount"))
    source_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, related_name='transfers_out',
        verbose_name=_("Source Account (From)")
    )
    destination_account = models.ForeignKey(
        'BankAccount', on_delete=models.PROTECT, related_name='transfers_in',
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
        'FixedAsset', on_delete=models.CASCADE, related_name='depreciation_logs', verbose_name=_("Asset")
    )
    period_date = models.DateField(verbose_name=_("Period End Date"))
    amount = models.DecimalField(max_digits=14, decimal_places=3, verbose_name=_("Depreciation Amount"))
    journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
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
