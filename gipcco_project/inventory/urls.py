# gipcco_project/inventory/urls.py

from django.urls import path
from . import views  # We will create the views in the next step

app_name = 'inventory'

urlpatterns = [
    # Dashboard & Records
    path('', views.index, name='index'),
    path('records/', views.records, name='records'),
    path('records/edit/<int:pk>/', views.edit_record, name='edit_record'),
    path('records/delete/<int:pk>/', views.delete_record, name='delete_record'),

    # Company Routes
    path('companies/', views.companies, name='companies'),
    path('companies/edit/<int:pk>/', views.edit_company, name='edit_company'),
    path('companies/delete/<int:pk>/', views.delete_company, name='delete_company'),

    # Product Routes
    path('products/', views.products, name='products'),
    path('products/edit/<int:pk>/', views.edit_product, name='edit_product'),
    path('products/delete/<int:pk>/', views.delete_product, name='delete_product'),

    # Template Routes
    path('shop_order_templates/', views.shop_order_templates, name='shop_order_templates'),
    path('shop_order_templates/delete/<int:pk>/', views.delete_shop_order_template, name='delete_shop_order_template'),
    path('shop_order_template/<int:pk>/', views.view_shop_order_template, name='view_shop_order_template'),
    path('shop_order_template/edit/<int:pk>/', views.edit_shop_order_template, name='edit_shop_order_template'),

    # Batch Routes
    path('batches/', views.batches, name='batches'),
    path('batches/create/', views.create_batch, name='create_batch'),
    path('batch/<int:pk>/', views.view_batch, name='view_batch'),
    path('batch/delete/<int:pk>/', views.delete_batch, name='delete_batch'),
    path('batch/item/add/<int:batch_pk>/', views.add_batch_item, name='add_batch_item'),
    path('batch/<int:batch_pk>/update_all/', views.update_batch_items_bulk, name='update_batch_items_bulk'),
    path('batch/item/delete/<int:item_pk>/', views.delete_batch_item, name='delete_batch_item'),

    # Production Returns Routes
    path('production_returns/', views.production_returns, name='production_returns'),
    path('production_returns/delete/<int:pk>/', views.delete_production_return, name='delete_production_return'),

    # Opening Balances Routes
    path('opening_balances/', views.opening_balances, name='opening_balances'),
    path('opening_balances/edit/<int:pk>/', views.edit_opening_balance, name='edit_opening_balance'),
    path('opening_balances/delete/<int:pk>/', views.delete_opening_balance, name='delete_opening_balance'),

    # Ledger, Analysis & Visuals
    path('ledger/', views.ledger, name='ledger'),
    path('ledger/print/', views.print_ledger, name='print_ledger'),
    path('analysis/', views.analysis, name='analysis'),
    path('visuals/', views.visuals, name='visuals'),

    # API Routes
    path('api/get_used_qc_sources/<int:product_pk>/', views.get_used_qc_sources, name='api_get_used_qc_sources'),
    path('api/batch_details/<int:batch_pk>/', views.api_batch_details, name='api_batch_details'),
]