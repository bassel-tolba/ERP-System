# admin.py

from django.contrib import admin
# REMOVED: from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Company, Product, ProductTag, InventoryLog, ShopOrderTemplate,
    TemplateItem, Batch, BatchItem, OpeningBalance, ProductionReturn,
    PurchaseOrder, PurchaseOrderItem, FinishedProductReceipt, ReceiptSubBatch
)

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(ProductTag)
class ProductTagAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('name', 'code', 'product_type', 'unit', 'moving_average_cost')
    list_filter = ('product_type', 'tags')
    search_fields = ('name', 'code')
    filter_horizontal = ('tags',)


@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('id', 'product', 'quantity', 'status', 'timestamp', 'company', 'qc_no')
    list_filter = ('status', 'company')
    search_fields = ('product__name', 'product__code', 'qc_no', 'po_item__purchase_order__po_number')
    date_hierarchy = 'timestamp'
    autocomplete_fields = ('product', 'company', 'po_item')


class TemplateItemInline(admin.TabularInline):
    model = TemplateItem
    extra = 1
    autocomplete_fields = ('primitive_product',)


@admin.register(ShopOrderTemplate)
class ShopOrderTemplateAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
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
class BatchAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('shop_order_number', 'batch_number', 'creation_date', 'template', 'is_customized')
    list_filter = ('is_customized', 'is_continuation')
    search_fields = ('shop_order_number', 'batch_number')
    date_hierarchy = 'creation_date'
    autocomplete_fields = ('template',)
    inlines = [BatchItemInline]


@admin.register(OpeningBalance)
class OpeningBalanceAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('product', 'quantity', 'balance_date', 'total_value', 'unit_cost')
    search_fields = ('product__name', 'product__code')
    date_hierarchy = 'balance_date'
    autocomplete_fields = ('product',)
    readonly_fields = ('unit_cost',)


@admin.register(ProductionReturn)
class ProductionReturnAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('product', 'quantity', 'return_date', 'source_log')
    search_fields = ('product__name', 'product__code')
    date_hierarchy = 'return_date'
    autocomplete_fields = ('product', 'source_log')


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 1
    autocomplete_fields = ('product',)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('po_number', 'supplier', 'order_date', 'status')
    list_filter = ('status', 'supplier')
    search_fields = ('po_number', 'supplier__name')
    date_hierarchy = 'order_date'
    inlines = [PurchaseOrderItemInline]


@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    search_fields = ('product__name', 'purchase_order__po_number')
    
    def has_module_permission(self, request):
        return False


class ReceiptSubBatchInline(admin.TabularInline):
    model = ReceiptSubBatch
    extra = 1


@admin.register(FinishedProductReceipt)
class FinishedProductReceiptAdmin(admin.ModelAdmin): # CHANGED from SimpleHistoryAdmin
    list_display = ('individual_batch_number', 'batch', 'receipt_date', 'total_quantity_produced', 'status', 'market_type')
    list_filter = ('status', 'market_type')
    search_fields = ('individual_batch_number', 'batch__batch_number', 'batch__shop_order_number')
    date_hierarchy = 'receipt_date'
    autocomplete_fields = ('batch',)
    inlines = [ReceiptSubBatchInline]