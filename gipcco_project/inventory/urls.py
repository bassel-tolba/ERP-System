# gipcco_project/inventory/urls.py

from django.urls import path

# --- MODIFIED: Use aliases for release_from_quarantine to avoid name collision ---
from .views.dashboard import index, records, edit_record, delete_record, quarantine_list, release_from_quarantine as release_material_from_quarantine
from .views.companies_products import companies, edit_company, delete_company, products, edit_product, delete_product, create_tag, edit_tag, delete_tag
from .views.templates import shop_order_templates, delete_shop_order_template, view_shop_order_template, edit_shop_order_template
from .views.batches import batches, create_batch, view_batch, delete_batch, add_batch_item, update_batch_items_bulk, delete_batch_item
from .views.production_returns import production_returns, delete_production_return
from .views.opening_balances import opening_balances, edit_opening_balance, delete_opening_balance
from .views.analysis_ledger_visuals import analysis, ledger, visuals, print_ledger, stock_valuation
from .views.purchase_orders import purchase_orders, create_purchase_order, view_purchase_order, edit_purchase_order, delete_purchase_order
# --- MODIFIED: Use aliases for release_from_quarantine to avoid name collision ---
from .views.finished_products import finished_goods_status, receive_finished_product, view_finished_product, release_from_quarantine as release_fg_from_quarantine
# --- MODIFIED: Import new API view ---
from .views.api import get_used_qc_sources, api_batch_details, get_product_tags, api_get_open_pos_for_supplier, api_get_po_items, api_get_full_batch_analysis

app_name = 'inventory'

urlpatterns = [
    # Dashboard & Records
    
    path('', index, name='index'),
    path('records/', records, name='records'),
    path('records/edit/<int:pk>/', edit_record, name='edit_record'),
    path('records/delete/<int:pk>/', delete_record, name='delete_record'),
    
    # --- NEW: Quality Control Routes ---
    path('quarantine/', quarantine_list, name='quarantine_list'),
    # --- MODIFIED: Use new view alias and unique URL name ---
    path('quarantine/release/<int:pk>/', release_material_from_quarantine, name='release_material_from_quarantine'),

    # Company Routes
    path('companies/', companies, name='companies'),
    path('companies/edit/<int:pk>/', edit_company, name='edit_company'),
    path('companies/delete/<int:pk>/', delete_company, name='delete_company'),

    # Product Routes
    path('products/', products, name='products'),
    path('products/edit/<int:pk>/', edit_product, name='edit_product'),
    path('products/delete/<int:pk>/', delete_product, name='delete_product'),

    # Product Tag Routes
    path('products/tags/create/', create_tag, name='create_tag'),
    path('products/tags/edit/<int:pk>/', edit_tag, name='edit_tag'),
    path('products/tags/delete/<int:pk>/', delete_tag, name='delete_tag'),
    
    # Purchase Order Routes
    path('purchase_orders/', purchase_orders, name='purchase_orders'),
    path('purchase_orders/create/', create_purchase_order, name='create_purchase_order'),
    path('purchase_order/<int:pk>/', view_purchase_order, name='view_purchase_order'),
    path('purchase_order/<int:pk>/edit/', edit_purchase_order, name='edit_purchase_order'),
    path('purchase_order/<int:pk>/delete/', delete_purchase_order, name='delete_purchase_order'),

    # Template Routes
    path('shop_order_templates/', shop_order_templates, name='shop_order_templates'),
    path('shop_order_templates/delete/<int:pk>/', delete_shop_order_template, name='delete_shop_order_template'),
    path('shop_order_template/<int:pk>/', view_shop_order_template, name='view_shop_order_template'),
    path('shop_order_template/edit/<int:pk>/', edit_shop_order_template, name='edit_shop_order_template'),

    # Batch Routes (Production Plans)
    path('batches/', batches, name='batches'),
    path('batches/create/', create_batch, name='create_batch'),
    path('batch/<int:pk>/', view_batch, name='view_batch'),
    path('batch/delete/<int:pk>/', delete_batch, name='delete_batch'),
    path('batch/item/add/<int:batch_pk>/', add_batch_item, name='add_batch_item'),
    path('batch/<int:batch_pk>/update_all/', update_batch_items_bulk, name='update_batch_items_bulk'),
    path('batch/item/delete/<int:item_pk>/', delete_batch_item, name='delete_batch_item'),

    # --- MODIFIED & NEW: Finished Product Routes ---
    path('finished_products/', finished_goods_status, name='finished_products_list'), # Renamed for clarity
    path('finished_goods_status/', finished_goods_status, name='finished_goods_status'), # New unified view
    path('batch/<int:batch_pk>/receive/<path:individual_batch_number>/', receive_finished_product, name='receive_finished_product'),
    path('finished_product/<int:pk>/', view_finished_product, name='view_finished_product'),
    # --- MODIFIED: Use new view alias and unique URL name ---
    path('finished_product/<int:pk>/release/', release_fg_from_quarantine, name='release_fg_from_quarantine'), # New release action

    # Production Returns Routes
    path('production_returns/', production_returns, name='production_returns'),
    path('production_returns/delete/<int:pk>/', delete_production_return, name='delete_production_return'),

    # Opening Balances Routes
    path('opening_balances/', opening_balances, name='opening_balances'),
    path('opening_balances/edit/<int:pk>/', edit_opening_balance, name='edit_opening_balance'),
    path('opening_balances/delete/<int:pk>/', delete_opening_balance, name='delete_opening_balance'),

    # Ledger, Analysis & Visuals
    path('ledger/', ledger, name='ledger'),
    path('ledger/print/', print_ledger, name='print_ledger'),
    path('analysis/', analysis, name='analysis'),
    path('stock_valuation/', stock_valuation, name='stock_valuation'),
    path('visuals/', visuals, name='visuals'),

    # API Routes
    path('api/get_used_qc_sources/<int:product_pk>/', get_used_qc_sources, name='api_get_used_qc_sources'),
    path('api/batch_details/<int:batch_pk>/', api_batch_details, name='api_batch_details'),
    # --- NEW API ROUTE ---
    path('api/batch_analysis/<int:batch_pk>/', api_get_full_batch_analysis, name='api_get_full_batch_analysis'),
    path('api/product_tags/<int:product_id>/', get_product_tags, name='api_product_tags'),
    path('api/supplier/<int:supplier_id>/open_pos/', api_get_open_pos_for_supplier, name='api_get_open_pos_for_supplier'),
    path('api/po/<int:po_id>/items/', api_get_po_items, name='api_get_po_items'),

]