from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

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
    
    supplier = models.ForeignKey('Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name=_("Supplier"))
    customer = models.ForeignKey('Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', verbose_name=_("Customer"))
    
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
    
    journal_entry = models.OneToOneField(
        'JournalEntry',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='employee_advance_settlement'
    )

    class Meta:
        db_table = 'employee_advance_settlements'
        verbose_name = _("Employee Advance Settlement")
        verbose_name_plural = _("Employee Advance Settlements")
        ordering = ['-settlement_date']

    def __str__(self):
        return f"Settlement of {self.amount_settled} for {self.advance}"
