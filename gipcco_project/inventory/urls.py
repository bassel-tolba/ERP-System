# gipcco_project/inventory/urls.py

from django.urls import path

# Import views from their specific modules
from .views.dashboard import index, records, edit_record, delete_record
from .views.companies_products import companies, edit_company, delete_company, products, edit_product, delete_product, create_tag, edit_tag, delete_tag
from .views.templates import shop_order_templates, delete_shop_order_template, view_shop_order_template, edit_shop_order_template
from .views.batches import batches, create_batch, view_batch, delete_batch, add_batch_item, update_batch_items_bulk, delete_batch_item
from .views.production_returns import production_returns, delete_production_return
from .views.opening_balances import opening_balances, edit_opening_balance, delete_opening_balance
from .views.analysis_ledger_visuals import analysis, ledger, visuals, print_ledger
from .views.api import get_used_qc_sources, api_batch_details, get_product_tags

app_name = 'inventory'

urlpatterns = [
    # Dashboard & Records
    path('', index, name='index'),
    path('records/', records, name='records'),
    path('records/edit/<int:pk>/', edit_record, name='edit_record'),
    path('records/delete/<int:pk>/', delete_record, name='delete_record'),

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

    # Template Routes
    path('shop_order_templates/', shop_order_templates, name='shop_order_templates'),
    path('shop_order_templates/delete/<int:pk>/', delete_shop_order_template, name='delete_shop_order_template'),
    path('shop_order_template/<int:pk>/', view_shop_order_template, name='view_shop_order_template'),
    path('shop_order_template/edit/<int:pk>/', edit_shop_order_template, name='edit_shop_order_template'),

    # Batch Routes
    path('batches/', batches, name='batches'),
    path('batches/create/', create_batch, name='create_batch'),
    path('batch/<int:pk>/', view_batch, name='view_batch'),
    path('batch/delete/<int:pk>/', delete_batch, name='delete_batch'),
    path('batch/item/add/<int:batch_pk>/', add_batch_item, name='add_batch_item'),
    path('batch/<int:batch_pk>/update_all/', update_batch_items_bulk, name='update_batch_items_bulk'),
    path('batch/item/delete/<int:item_pk>/', delete_batch_item, name='delete_batch_item'),

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
    path('visuals/', visuals, name='visuals'),

    # API Routes
    path('api/get_used_qc_sources/<int:product_pk>/', get_used_qc_sources, name='api_get_used_qc_sources'),
    path('api/batch_details/<int:batch_pk>/', api_batch_details, name='api_batch_details'),
    path('api/product_tags/<int:product_id>/', get_product_tags, name='api_product_tags'),
]