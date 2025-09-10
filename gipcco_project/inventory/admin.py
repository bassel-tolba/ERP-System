# gipcco_project/inventory/admin.py

from decimal import Decimal
from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, Q, F, FloatField, Value 
from django.contrib.contenttypes.admin import GenericTabularInline

# Model imports (Existing and New)
from .models import (
    Company, Product, ProductTag, InventoryLog, ShopOrderTemplate,
    TemplateItem, Batch, BatchItem, OpeningBalance, ProductionReturn,
    PurchaseOrder, PurchaseOrderItem, FinishedProductReceipt, ReceiptSubBatch,
    Customer, Employee, 
    SalesOrder, SalesOrderItem, FinishedProductDispatch, InventoryConsumption, ExpenseLog,
    
    # New Accounting Core Models
    FinancialPeriod, Account, JournalEntry, JournalEntryLine,
    ProductTypeAccountingSettings,
    
    # New Sub-Ledger Models
    FixedAsset, BankAccount, Payment,
    
    # --- NEW MODEL IMPORT ---
    GeneralAccountingSettings
)

# Business logic helpers from the views package.
from .views.dashboard import update_po_status
from .views.helpers import check_and_update_batch_customization
from .services.costing_service import recalculate_cost_history_for_product

# ==============================================================================
#  INVENTORY & PRODUCTION ADMINS (UNCHANGED)
# ==============================================================================

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'address', 'contact_info')
    search_fields = ('name',)

@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
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

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'product', 'quantity', 'status', 'qc_no', 'release_timestamp', 'company')
    list_filter = ('status', 'company', 'product', 'vat_treatment')
    search_fields = ('product__name', 'product__code', 'qc_no', 'po_item__purchase_order__po_number')
    date_hierarchy = 'timestamp'
    autocomplete_fields = ('product', 'company', 'po_item')
    actions = ['release_items', 'reject_items']
    
    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != InventoryLog.Status.QUARANTINED:
            return ('status', 'qc_no', 'release_timestamp')
        return ()

    @admin.action(description="الإفراج عن البنود المحددة (Release selected items)")
    def release_items(self, request, queryset):
        quarantined_items = queryset.filter(status=InventoryLog.Status.QUARANTINED)
        if not quarantined_items.exists():
            self.message_user(request, "لم يتم تحديد أي بنود صالحة للإفراج (يجب أن تكون تحت الفحص).", messages.WARNING)
            return
        for item in quarantined_items:
            if not item.qc_no:
                self.message_user(request, f"البند رقم {item.id} ليس له رقم فحص (QC No). لا يمكن الإفراج عنه.", messages.ERROR)
                return
        with transaction.atomic():
            now = timezone.now()
            updated_count = 0
            products_to_recalc = set()
            for item in quarantined_items:
                item.status = InventoryLog.Status.RELEASED
                item.release_timestamp = now
                item.save(update_fields=['status', 'release_timestamp'])
                products_to_recalc.add((item.product_id, item.release_timestamp))
                updated_count += 1
            for product_id, timestamp in products_to_recalc:
                recalculate_cost_history_for_product(product_id, timestamp)
        self.message_user(request, f"تم الإفراج عن {updated_count} بند بنجاح وتحديث التكاليف.", messages.SUCCESS)

    @admin.action(description="رفض البنود المحددة (Reject selected items)")
    def reject_items(self, request, queryset):
        quarantined_items = queryset.filter(status=InventoryLog.Status.QUARANTINED)
        updated_count = quarantined_items.update(status=InventoryLog.Status.REJECTED)
        self.message_user(request, f"تم رفض {updated_count} بند.", messages.SUCCESS)

    def save_model(self, request, obj: InventoryLog, form, change):
        was_released = False
        recalc_date = obj.release_timestamp or obj.timestamp
        product_id_to_recalc = obj.product_id
        original_po_item = None
        if obj.pk:
            original_obj = InventoryLog.objects.get(pk=obj.pk)
            was_released = original_obj.status == InventoryLog.Status.RELEASED
            recalc_date = min(recalc_date, original_obj.release_timestamp or original_obj.timestamp)
            original_po_item = original_obj.po_item
        super().save_model(request, obj, form, change)
        if was_released or obj.status == InventoryLog.Status.RELEASED:
            recalculate_cost_history_for_product(product_id_to_recalc, recalc_date)
            if change and 'product' in form.changed_data:
                 recalculate_cost_history_for_product(original_obj.product_id, recalc_date)
        if original_po_item != obj.po_item:
            if original_po_item: update_po_status(original_po_item.purchase_order_id)
            if obj.po_item: update_po_status(obj.po_item.purchase_order_id)
        elif obj.po_item:
            update_po_status(obj.po_item.purchase_order_id)

    def _trigger_recalc_and_po_update(self, queryset):
        products_to_recalc = set()
        po_ids_to_update = set()
        for item in queryset:
            if item.status == InventoryLog.Status.RELEASED:
                products_to_recalc.add((item.product_id, item.release_timestamp or item.timestamp))
            if item.po_item:
                po_ids_to_update.add(item.po_item.purchase_order_id)
        with transaction.atomic():
            queryset.delete()
        for product_id, timestamp in products_to_recalc:
            recalculate_cost_history_for_product(product_id, timestamp)
        for po_id in po_ids_to_update:
            update_po_status(po_id)
        
    def delete_model(self, request, obj):
        self._trigger_recalc_and_po_update(InventoryLog.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        self._trigger_recalc_and_po_update(queryset)

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
    autocomplete_fields = ('template',)
    inlines = [BatchItemInline]

    def _trigger_batch_logic(self, batch):
        products_to_recalc = set(item.primitive_product_id for item in batch.items.all())
        recalc_start_date = batch.creation_date
        check_and_update_batch_customization(batch.id)
        for pid in products_to_recalc:
            recalculate_cost_history_for_product(pid, recalc_start_date)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        batch = form.instance
        self._trigger_batch_logic(batch)

    def delete_model(self, request, obj):
        products_to_recalc = set(item.primitive_product_id for item in obj.items.all())
        recalc_start_date = obj.creation_date
        with transaction.atomic():
            obj.delete()
        for pid in products_to_recalc:
            recalculate_cost_history_for_product(pid, recalc_start_date)

    def delete_queryset(self, request, queryset):
        recalc_map = {}
        for batch in queryset:
            for item in batch.items.all():
                pid = item.primitive_product_id
                if pid not in recalc_map or batch.creation_date < recalc_map[pid]:
                    recalc_map[pid] = batch.creation_date
        with transaction.atomic():
            queryset.delete()
        for pid, start_date in recalc_map.items():
            recalculate_cost_history_for_product(pid, start_date)

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

    def delete_model(self, request, obj):
        product_id, balance_date = obj.product_id, obj.balance_date
        with transaction.atomic():
            obj.delete()
        recalculate_cost_history_for_product(product_id, balance_date)
        
    def delete_queryset(self, request, queryset):
        recalc_map = {}
        for b in queryset:
            if b.product_id not in recalc_map or b.balance_date < recalc_map[b.product_id]:
                recalc_map[b.product_id] = b.balance_date
        with transaction.atomic():
            queryset.delete()
        for product_id, balance_date in recalc_map.items():
            recalculate_cost_history_for_product(product_id, balance_date)

@admin.register(ProductionReturn)
class ProductionReturnAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity', 'return_date', 'source_log')
    search_fields = ('product__name', 'product__code')
    date_hierarchy = 'return_date'
    autocomplete_fields = ('product', 'source_log')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        recalculate_cost_history_for_product(obj.product_id, obj.return_date)

    def delete_model(self, request, obj):
        product_id, return_date = obj.product_id, obj.return_date
        with transaction.atomic():
            obj.delete()
        recalculate_cost_history_for_product(product_id, return_date)

    def delete_queryset(self, request, queryset):
        recalc_map = {}
        for r in queryset:
            if r.product_id not in recalc_map or r.return_date < recalc_map[r.product_id]:
                recalc_map[r.product_id] = r.return_date
        with transaction.atomic():
            queryset.delete()
        for product_id, return_date in recalc_map.items():
             recalculate_cost_history_for_product(product_id, return_date)

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

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    search_fields = ('product__name', 'purchase_order__po_number')
    def has_module_permission(self, request):
        return False

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
    
    def get_readonly_fields(self, request, obj=None):
        if obj:
            return ('total_cost', 'total_quantity_produced', 'status', 'release_date')
        return ('total_cost', 'total_quantity_produced', 'status', 'release_date')

    @admin.action(description="الإفراج عن التشغيلات المحددة (Release selected receipts)")
    def release_receipts(self, request, queryset):
        quarantined = queryset.filter(status=FinishedProductReceipt.Status.QUARANTINED)
        updated_count = 0
        with transaction.atomic():
            for receipt in quarantined:
                receipt.status = FinishedProductReceipt.Status.RELEASED
                receipt.release_date = timezone.now().date()
                receipt.save(update_fields=['status', 'release_date'])
                updated_count += 1
        self.message_user(request, f"تم الإفراج عن {updated_count} تشغيلة بنجاح.", messages.SUCCESS)
    
    def save_model(self, request, obj: FinishedProductReceipt, form, change):
        if not change:
             obj.status = FinishedProductReceipt.Status.QUARANTINED
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        receipt = form.instance
        total_qty = receipt.sub_batches.aggregate(total=Sum('quantity'))['total'] or 0.0
        if receipt.total_quantity_produced != total_qty:
            receipt.total_quantity_produced = total_qty
            receipt.save(update_fields=['total_quantity_produced'])

# ==============================================================================
#  ACCOUNTING & FINANCE ADMINS (NEW)
# ==============================================================================

@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date', 'is_closed')
    list_filter = ('is_closed',)

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_closed:
            return [field.name for field in self.model._meta.fields]
        return []

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'parent')
    list_filter = ('account_type',)
    search_fields = ('code', 'name')
    autocomplete_fields = ('parent',)

class JournalEntryLineInline(admin.TabularInline):
    model = JournalEntryLine
    extra = 2
    autocomplete_fields = ('account',)

@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    inlines = [JournalEntryLineInline]
    list_display = ('id', 'date', 'description', 'is_balanced')
    list_filter = ('date',)
    search_fields = ('description', 'lines__account__name')
    readonly_fields = ('content_type', 'object_id', 'source_object')

    @admin.display(boolean=True, description='متوازن؟ (Balanced?)')
    def is_balanced(self, obj):
        totals = obj.lines.aggregate(
            debits=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.DEBIT)),
            credits=Sum('amount', filter=Q(entry_type=JournalEntryLine.EntryType.CREDIT))
        )
        debits = totals['debits'] or Decimal('0.0')
        credits = totals['credits'] or Decimal('0.0')
        return abs(debits - credits) < Decimal('0.001')

    def save_formset(self, request, form, formset, change):
        debits = Decimal('0.0')
        credits = Decimal('0.0')
        for form_line in formset.cleaned_data:
            if form_line and not form_line.get('DELETE', False):
                amount = form_line.get('amount', Decimal('0.0'))
                if form_line.get('entry_type') == JournalEntryLine.EntryType.DEBIT:
                    debits += amount
                elif form_line.get('entry_type') == JournalEntryLine.EntryType.CREDIT:
                    credits += amount
        
        if abs(debits - credits) >= Decimal('0.001'):
            self.message_user(request, f"القيد غير متوازن! المدين: {debits}, الدائن: {credits}. لم يتم الحفظ.", messages.ERROR)
            return
        
        super().save_formset(request, form, formset, change)

@admin.register(ProductTypeAccountingSettings)
class ProductTypeAccountingSettingsAdmin(admin.ModelAdmin):
    list_display = ('product_type', 'inventory_account', 'cogs_or_expense_account', 'sales_revenue_account')
    autocomplete_fields = ('inventory_account', 'cogs_or_expense_account', 'sales_revenue_account')

@admin.register(GeneralAccountingSettings)
class GeneralAccountingSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'accounts_payable', 'accounts_receivable', 'vat_receivable')
    autocomplete_fields = (
        'accounts_payable', 
        'accounts_receivable', 
        'vat_receivable', 
        'vat_payable', 
        'wip_inventory',
        'finished_goods_inventory'
    )

    def has_add_permission(self, request):
        # Prevent adding a new object if one already exists
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        # Prevent deleting the settings object
        return False

@admin.register(InventoryConsumption)
class InventoryConsumptionAdmin(admin.ModelAdmin):
    list_display = ('product', 'quantity_consumed', 'department', 'consumption_date', 'consumption_type', 'fixed_asset')
    list_filter = ('department', 'consumption_type', 'consumption_date')
    search_fields = ('product__name', 'fixed_asset__name', 'notes')
    autocomplete_fields = ('product', 'source_log', 'fixed_asset')
    readonly_fields = ('cost_at_consumption',)

    def get_form(self, request, obj=None, **kwargs):
        # Limit product choices to MRO and Consumables
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['product'].queryset = Product.objects.filter(
            product_type__in=[Product.ProductType.MRO, Product.ProductType.CONSUMABLE]
        )
        return form
    
    def save_model(self, request, obj: InventoryConsumption, form, change):
        # Calculate cost before saving
        if obj.source_log and obj.quantity_consumed:
            cost_per_unit = obj.source_log.costing_unit_price
            obj.cost_at_consumption = cost_per_unit * Decimal(str(obj.quantity_consumed))
        super().save_model(request, obj, form, change)

    class Media:
        # Add a small piece of JavaScript to the admin page
        js = ('admin/js/inventory_consumption.js',)
# ==============================================================================
#  SUB-LEDGER ADMINS (NEW)
# ==============================================================================

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'full_name', 'job_title', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('employee_id', 'first_name', 'last_name')
    
    @admin.display(description='Full Name')
    def full_name(self, obj):
        return obj.full_name

@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ('asset_tag', 'name', 'gl_account', 'purchase_cost', 'purchase_date', 'status')
    list_filter = ('status', 'gl_account')
    search_fields = ('asset_tag', 'name', 'serial_number')
    date_hierarchy = 'purchase_date'
    autocomplete_fields = ('gl_account',)

@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'currency', 'gl_account')
    search_fields = ('name',)
    autocomplete_fields = ('gl_account',)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment_date', 'description', 'amount', 'bank_account', 'payment_type')
    list_filter = ('payment_type', 'bank_account')
    search_fields = ('description', 'supplier__name', 'customer__name')
    date_hierarchy = 'payment_date'
    autocomplete_fields = ('bank_account', 'supplier', 'customer')