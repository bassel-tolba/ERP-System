# gipcco_project/inventory/admin.py

from decimal import Decimal
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Q, Count
from django.db.models.functions import TruncMonth

from .models import (
    Company, Product, ProductTag, InventoryLog, ShopOrderTemplate,
    TemplateItem, Batch, BatchItem, OpeningBalance, ProductionReturn,
    PurchaseOrder, PurchaseOrderItem, FinishedProductReceipt, ReceiptSubBatch,
    Customer, Employee,
    SalesOrder, SalesOrderItem, FinishedProductDispatch, InventoryConsumption, ExpenseLog,
    FinancialPeriod, Account, JournalEntry, JournalEntryLine,
    ProductTypeAccountingSettings, FixedAsset, BankAccount, Payment,
    GeneralAccountingSettings,
    # --- NEW MODEL IMPORTS ---
    SupplierInvoice, SupplierInvoiceItem, PaymentApplication,
    CustomerInvoice, CustomerInvoiceItem, CustomerPaymentApplication,
    BankTransfer, DepreciationLog,
    # --- ADDED FOR FIX ---
    BankReconciliation, BankStatementLine, FiscalYear
)
from .views.dashboard import update_po_status
from .views.helpers import check_and_update_batch_customization
from .services.costing_service import recalculate_cost_history_for_product

# ==============================================================================
#  SETUP & OPERATIONAL ADMINS
# ==============================================================================
@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin): # Changed from ImportExportModelAdmin
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin): # Changed from ImportExportModelAdmin
    list_display = ('name', 'address', 'contact_info')
    search_fields = ('name',)

@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin): # Changed from ImportExportModelAdmin
    list_display = ('name', 'code', 'product_type', 'unit', 'moving_average_cost')
    list_filter = ('product_type', 'tags')
    search_fields = ('name', 'code')
    filter_horizontal = ('tags',)
    autocomplete_fields = (
        'override_inventory_account',
        'override_cogs_expense_account',
        'override_sales_revenue_account'
    )
    readonly_fields = ('moving_average_cost',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin): # Changed from ImportExportModelAdmin
    list_display = ('employee_id', 'full_name', 'job_title', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('employee_id', 'first_name', 'last_name')

    @admin.display(description='Full Name')
    def full_name(self, obj):
        return obj.full_name

# ==============================================================================
#  INVENTORY & PRODUCTION ADMINS
# ==============================================================================
@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin): # Removed AdminChartMixin
    list_display = ('id', 'product', 'quantity', 'status', 'qc_no', 'release_timestamp', 'company')
    list_filter = ('status', 'company', 'product__product_type')
    search_fields = ('product__name', 'product__code', 'qc_no', 'po_item__purchase_order__po_number')
    date_hierarchy = 'timestamp'
    autocomplete_fields = ('product', 'company', 'po_item')
    actions = ['release_items', 'reject_items', 'scrap_items'] # Added scrap

    @admin.action(description="Release selected items")
    def release_items(self, request, queryset):
        # ... (add logic here if needed, or rely on UI)
        pass

    @admin.action(description="Reject selected items")
    def reject_items(self, request, queryset):
        # ... (add logic here if needed, or rely on UI)
        pass

    @admin.action(description="Scrap selected items")
    def scrap_items(self, request, queryset):
        # ... (add logic here if needed)
        pass

class TemplateItemInline(admin.TabularInline):
    model = TemplateItem
    extra = 1
    autocomplete_fields = ('primitive_product',)

@admin.register(ShopOrderTemplate)
class ShopOrderTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'final_product')
    search_fields = ('name', 'final_product__name')
    autocomplete_fields = ('final_product',)
    inlines = [TemplateItemInline]

class BatchItemInline(admin.TabularInline):
    model = BatchItem
    extra = 0
    autocomplete_fields = ('primitive_product', 'source_log')
    readonly_fields = ('cost_at_consumption',)

@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('shop_order_number', 'batch_number', 'creation_date', 'template', 'is_customized', 'is_continuation')
    list_filter = ('is_customized', 'is_continuation', 'template__final_product')
    search_fields = ('shop_order_number', 'batch_number')
    date_hierarchy = 'creation_date'
    autocomplete_fields = ('template', 'parent_batch')
    inlines = [BatchItemInline]

    def _trigger_batch_logic(self, batch):
        products_to_recalc = set(item.primitive_product_id for item in batch.items.all())
        recalc_start_date = batch.creation_date
        check_and_update_batch_customization(batch.id)
        for pid in products_to_recalc:
            recalculate_cost_history_for_product(pid, recalc_start_date)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        self._trigger_batch_logic(form.instance)

@admin.register(OpeningBalance)
class OpeningBalanceAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'balance_date', 'total_value', 'unit_cost')
    search_fields = ('product__name', 'product__code')
    date_hierarchy = 'balance_date'
    autocomplete_fields = ('product',)
    readonly_fields = ('unit_cost',)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        recalculate_cost_history_for_product(obj.product_id, obj.balance_date)

@admin.register(ProductionReturn)
class ProductionReturnAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'return_date', 'source_log')
    search_fields = ('product__name', 'product__code')
    date_hierarchy = 'return_date'
    autocomplete_fields = ('product', 'source_log')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        recalculate_cost_history_for_product(obj.product_id, obj.return_date)

class ReceiptSubBatchInline(admin.TabularInline):
    model = ReceiptSubBatch
    extra = 1

@admin.register(FinishedProductReceipt)
class FinishedProductReceiptAdmin(admin.ModelAdmin):
    list_display = ('individual_batch_number', 'batch', 'receipt_date', 'total_quantity_produced', 'status', 'market_type')
    list_filter = ('status', 'market_type', 'batch__template__final_product')
    search_fields = ('individual_batch_number', 'batch__batch_number', 'batch__shop_order_number')
    date_hierarchy = 'receipt_date'
    autocomplete_fields = ('batch',)
    inlines = [ReceiptSubBatchInline]
    actions = ['release_receipts']

    @admin.action(description="Release selected receipts")
    def release_receipts(self, request, queryset):
        updated = queryset.filter(status=FinishedProductReceipt.Status.QUARANTINED).update(
            status=FinishedProductReceipt.Status.RELEASED, release_date=timezone.now().date()
        )
        self.message_user(request, f"{updated} receipts were successfully released.", messages.SUCCESS)

# ==============================================================================
#  PURCHASING & SALES ADMINS
# ==============================================================================
class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    autocomplete_fields = ('product',)

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ('po_number', 'supplier', 'order_date', 'status')
    list_filter = ('status', 'supplier')
    search_fields = ('po_number', 'supplier__name')
    date_hierarchy = 'order_date'
    inlines = [PurchaseOrderItemInline]
    readonly_fields = ('status',)
    autocomplete_fields = ('supplier',)

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    search_fields = ('product__name', 'purchase_order__po_number')
    def has_module_permission(self, request):
        return False # Hide from main admin index

class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 1
    autocomplete_fields = ('finished_product',)
    readonly_fields = ('product_name', 'total_price',)
    fields = ('finished_product', 'product_name', 'quantity_ordered', 'base_price_per_unit', 'vat_rate', 'total_price')

    @admin.display(description='Product Name')
    def product_name(self, obj):
        return obj.finished_product.batch.template.final_product.name if obj.finished_product else "N/A"

@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    inlines = [SalesOrderItemInline]
    list_display = ('so_number', 'customer', 'order_date', 'status')
    list_filter = ('status', 'customer')
    search_fields = ('so_number', 'customer__name')
    date_hierarchy = 'order_date'
    readonly_fields = ('status',)
    autocomplete_fields = ('customer',)

@admin.register(SalesOrderItem)
class SalesOrderItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'sales_order', 'finished_product', 'quantity_ordered')
    search_fields = ('sales_order__so_number', 'finished_product__individual_batch_number', 'finished_product__batch__template__final_product__name')
    autocomplete_fields = ('sales_order', 'finished_product')
    def has_module_permission(self, request):
        return False # Hide from main admin index

@admin.register(FinishedProductDispatch)
class FinishedProductDispatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'sales_order_item', 'quantity', 'dispatch_date', 'cost_at_dispatch')
    list_filter = ('dispatch_date',)
    search_fields = ('sales_order_item__sales_order__so_number', 'sales_order_item__finished_product__individual_batch_number')
    date_hierarchy = 'dispatch_date'
    autocomplete_fields = ('sales_order_item',)
    readonly_fields = ('cost_at_dispatch',)

@admin.register(ExpenseLog)
class ExpenseLogAdmin(admin.ModelAdmin):
    list_display = ('expense_date', 'description', 'amount', 'category', 'classification')
    list_filter = ('category', 'classification', 'expense_date')
    search_fields = ('description', 'notes')
    date_hierarchy = 'expense_date'

# ==============================================================================
#  FINANCE & BANKING ADMINS
# ==============================================================================

class PaymentApplicationInline(admin.TabularInline):
    model = PaymentApplication
    extra = 0
    autocomplete_fields = ('payment',)
    readonly_fields = ('application_date',)

class SupplierInvoiceItemInline(admin.TabularInline):
    model = SupplierInvoiceItem
    extra = 0
    autocomplete_fields = ('receipt',)
    readonly_fields = ('product_name', 'receipt_total')
    fields = ('receipt', 'product_name', 'receipt_total', 'amount')

    @admin.display(description="Product")
    def product_name(self, obj):
        return obj.receipt.product.name if obj.receipt else ""

    @admin.display(description="Receipt Total")
    def receipt_total(self, obj):
        return (obj.receipt.base_unit_price * Decimal(str(obj.receipt.quantity))) + obj.receipt.vat_amount if obj.receipt else ""

@admin.register(SupplierInvoice)
class SupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'invoice_date', 'due_date', 'total_amount', 'amount_paid', 'balance_due', 'status')
    list_filter = ('status', 'supplier', 'invoice_date')
    search_fields = ('invoice_number', 'supplier__name')
    date_hierarchy = 'invoice_date'
    autocomplete_fields = ('supplier',)
    inlines = [SupplierInvoiceItemInline, PaymentApplicationInline]
    readonly_fields = ('total_amount', 'amount_paid', 'balance_due')
    actions = ['update_invoice_status']

    @admin.action(description="Recalculate and update status for selected invoices")
    def update_invoice_status(self, request, queryset):
        for invoice in queryset:
            invoice.update_status()
        self.message_user(request, f"Status updated for {queryset.count()} invoices.", messages.SUCCESS)

class CustomerPaymentApplicationInline(admin.TabularInline):
    model = CustomerPaymentApplication
    extra = 0
    autocomplete_fields = ('payment',)
    readonly_fields = ('application_date',)

class CustomerInvoiceItemInline(admin.TabularInline):
    model = CustomerInvoiceItem
    extra = 0
    autocomplete_fields = ('dispatch',)

@admin.register(CustomerInvoice)
class CustomerInvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'customer', 'invoice_date', 'due_date', 'total_amount', 'amount_paid', 'balance_due', 'status')
    list_filter = ('status', 'customer', 'invoice_date')
    search_fields = ('invoice_number', 'customer__name', 'sales_order__so_number')
    date_hierarchy = 'invoice_date'
    autocomplete_fields = ('customer', 'sales_order')
    inlines = [CustomerInvoiceItemInline, CustomerPaymentApplicationInline]
    readonly_fields = ('total_amount', 'amount_paid', 'balance_due')
    actions = ['update_invoice_status']

    @admin.action(description="Recalculate and update status for selected invoices")
    def update_invoice_status(self, request, queryset):
        for invoice in queryset:
            invoice.update_status()
        self.message_user(request, f"Status updated for {queryset.count()} invoices.", messages.SUCCESS)

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'gl_account')
    search_fields = ('name',)
    autocomplete_fields = ('gl_account',)

@admin.register(BankTransfer)
class BankTransferAdmin(admin.ModelAdmin):
    list_display = ('transfer_date', 'amount', 'source_account', 'destination_account')
    list_filter = ('transfer_date',)
    search_fields = ('description', 'source_account__name', 'destination_account__name')
    date_hierarchy = 'transfer_date'
    autocomplete_fields = ('source_account', 'destination_account')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment_date', 'description', 'amount', 'bank_account', 'payment_type', 'supplier', 'customer')
    list_filter = ('payment_type', 'bank_account')
    search_fields = ('description', 'supplier__name', 'customer__name')
    date_hierarchy = 'payment_date'
    autocomplete_fields = ('bank_account', 'supplier', 'customer')

# ==============================================================================
#  FIXED ASSETS & DEPRECIATION ADMINS
# ==============================================================================

class DepreciationLogInline(admin.TabularInline):
    model = DepreciationLog
    extra = 0
    readonly_fields = ('period_date', 'amount', 'journal_entry_link')
    can_delete = False
    
    @admin.display(description="Journal Entry")
    def journal_entry_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.journal_entry:
            url = reverse('admin:inventory_journalentry_change', args=[obj.journal_entry.pk])
            return format_html('<a href="{}">JE-{}</a>', url, obj.journal_entry.pk)
        return "-"

@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_tag', 'name', 'status', 'purchase_cost', 'accumulated_depreciation', 'net_book_value')
    list_filter = ('status', 'gl_account')
    search_fields = ('asset_tag', 'name', 'serial_number')
    date_hierarchy = 'purchase_date'
    autocomplete_fields = ('gl_account', 'depreciation_expense_account', 'accumulated_depreciation_account')
    inlines = [DepreciationLogInline]
    readonly_fields = ('accumulated_depreciation', 'net_book_value')

@admin.register(DepreciationLog)
class DepreciationLogAdmin(admin.ModelAdmin):
    list_display = ('asset', 'period_date', 'amount', 'journal_entry')
    list_filter = ('period_date',)
    search_fields = ('asset__name',)
    date_hierarchy = 'period_date'
    def has_add_permission(self, request):
        return False # Should be created by management command
    def has_change_permission(self, request, obj=None):
        return False # Should not be edited manually


# ==============================================================================
#  BANK RECONCILIATION ADMINS (NEWLY ADDED SECTION)
# ==============================================================================
class BankStatementLineInline(admin.TabularInline):
    model = BankStatementLine
    extra = 0
    readonly_fields = ('is_reconciled', 'reconciled_object')
    fields = ('transaction_date', 'description', 'amount', 'is_reconciled', 'reconciled_object')

@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'bank_account', 'statement_date', 'status', 'statement_closing_balance')
    list_filter = ('status', 'bank_account')
    search_fields = ('bank_account__name',)
    date_hierarchy = 'statement_date'
    autocomplete_fields = ('bank_account',)
    inlines = [BankStatementLineInline]
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('bank_account', 'statement_date', 'status')
        }),
        ('Balances', {
            'fields': ('statement_opening_balance', 'statement_closing_balance')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )

# ==============================================================================
#  CORE ACCOUNTING & SETTINGS ADMINS
# ==============================================================================
class FinancialPeriodInline(admin.TabularInline):
    model = FinancialPeriod
    extra = 0
    readonly_fields = ('name', 'start_date', 'end_date', 'status')
    fields = ('name', 'start_date', 'end_date', 'status')
    can_delete = False
    ordering = ('start_date',)
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(FiscalYear)
class FiscalYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_closed')
    list_filter = ('is_closed',)
    search_fields = ('name',)
    inlines = [FinancialPeriodInline]

@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'fiscal_year', 'start_date', 'end_date', 'status')
    list_filter = ('status', 'fiscal_year')
    search_fields = ('name', 'fiscal_year__name')
    ordering = ('-start_date',)

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin): # Changed from ImportExportModelAdmin
    list_display = ('code', 'name', 'account_type', 'parent', 'is_control_account')
    list_filter = ('account_type', 'is_control_account')
    search_fields = ('code', 'name')
    autocomplete_fields = ('parent',)
    list_editable = ('is_control_account',)
    fieldsets = (
        (None, {
            'fields': ('code', 'name', 'account_type', 'parent')
        }),
        ('Sub-Ledger Settings', {
            'classes': ('collapse',),
            'fields': ('is_control_account', 'sub_ledger_model'),
        }),
    )

class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 2
    autocomplete_fields = ('account',)
    readonly_fields = ('sub_ledger_object',)
    fields = ('entry_type', 'account', 'amount', 'sub_ledger_content_type', 'sub_ledger_object_id', 'sub_ledger_object')

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    inlines = [JournalEntryLineInline]
    list_display = ('id', 'date', 'description', 'source_object_link', 'is_balanced')
    list_filter = ('date',)
    search_fields = ('description', 'lines__account__name')
    readonly_fields = ('source_object_link',)

    @admin.display(boolean=True, description='Balanced?')
    def is_balanced(self, obj):
        totals = obj.lines.aggregate(
            debits=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.DEBIT)),
            credits=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.CREDIT))
        )
        return abs((totals['debits'] or 0) - (totals['credits'] or 0)) < Decimal('0.001')

    @admin.display(description="Source Document")
    def source_object_link(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        if obj.source_object:
            meta = obj.source_object._meta
            url = reverse(f'admin:{meta.app_label}_{meta.model_name}_change', args=[obj.object_id])
            return format_html('<a href="{}">{}</a>', url, obj.source_object)
        return "Manual Entry"

@admin.register(ProductTypeAccountingSettings)
class ProductTypeAccountingSettingsAdmin(admin.ModelAdmin):
    list_display = ('product_type', 'inventory_account', 'cogs_or_expense_account', 'sales_revenue_account')
    autocomplete_fields = ('inventory_account', 'cogs_or_expense_account', 'sales_revenue_account')

@admin.register(GeneralAccountingSettings)
class GeneralAccountingSettingsAdmin(admin.ModelAdmin):
    autocomplete_fields = (
        'accounts_payable', 'accounts_receivable', 'vat_receivable',
        'vat_payable', 'wip_inventory', 'finished_goods_inventory',
        'withholding_tax_payable'
    )
    def has_add_permission(self, request):
        return self.model.objects.count() == 0
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(InventoryConsumption)
class InventoryConsumptionAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity_consumed', 'department', 'consumption_date', 'consumption_type', 'fixed_asset')
    list_filter = ('department', 'consumption_type')
    search_fields = ('product__name', 'fixed_asset__name')
    autocomplete_fields = ('product', 'source_log', 'fixed_asset')
    readonly_fields = ('cost_at_consumption',)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['product'].queryset = Product.objects.filter(product_type__in=[Product.ProductType.MRO, Product.ProductType.CONSUMABLE])
        return form

    def save_model(self, request, obj, form, change):
        if obj.source_log and obj.quantity_consumed:
            obj.cost_at_consumption = obj.source_log.costing_unit_price * Decimal(str(obj.quantity_consumed))
        super().save_model(request, obj, form, change)