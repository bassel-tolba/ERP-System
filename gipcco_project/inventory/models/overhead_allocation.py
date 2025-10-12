from decimal import Decimal
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.conf import settings

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
        limit_choices_to={'account_type': 'expense'},
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
    Represents a single run of the overhead allocation process for a given
    financial period and cost pool. This model captures the allocation rate
    and the total amount allocated.
    """
    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        CALCULATED = 'calculated', _('Rate Calculated')
        POSTED = 'posted', _('Posted to GL')
        APPLIED = 'applied', _('Applied to Inventory')

    financial_period = models.ForeignKey(
        'FinancialPeriod', on_delete=models.PROTECT, related_name='allocation_runs',
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
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name=_("Resulting Journal Entry")
    )
    # --- NEW: Link to the second JE that applies the cost from WIP to FG ---
    application_journal_entry = models.ForeignKey(
        'JournalEntry', on_delete=models.SET_NULL, null=True, blank=True,
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
        return f"Run for {self.cost_pool.name} in {self.financial_period.name} ({self.get_status_display()})"
