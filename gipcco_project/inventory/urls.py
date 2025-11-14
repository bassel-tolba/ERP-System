# gipcco_project/inventory/urls.py

from django.urls import path

# --- MODIFIED: Use aliases for release_from_quarantine to avoid name collision ---
from .views.receipts import index, records, void_record_view, quarantine_list, release_from_quarantine as release_material_from_quarantine
from .views.companies_products import companies, edit_company, delete_company, products, edit_product, delete_product, create_tag, edit_tag, delete_tag
from .views.templates import shop_order_templates, delete_shop_order_template, view_shop_order_template, edit_shop_order_template
from .views.batches import batches, create_batch, view_batch, cancel_batch_view, add_batch_item, update_batch_items_bulk, return_batch_item_view, submit_batch_view, approve_batch_view, start_production_view, reject_batch_view
from .views.production_returns import production_returns, cancel_production_return_view
# --- MODIFIED: Import corrected views ---
from .views.analysis_ledger_visuals import visuals
from .views.purchase_orders import purchase_orders, create_purchase_order, view_purchase_order, edit_purchase_order, delete_purchase_order
from .views import purchasing_views
from .views.finished_products import finished_goods_status, receive_finished_product, view_finished_product, release_from_quarantine as release_fg_from_quarantine, cancel_finished_product_receipt_view
from .views.adjustments import inventory_counts_list, create_inventory_count, manage_inventory_count, allocate_inventory_variances
from .views.api import (
    get_used_qc_sources, api_batch_details, get_product_tags, api_get_open_pos_for_supplier, 
    api_get_po_items, api_get_full_batch_analysis, api_get_sellable_stock, 
    api_get_available_stock, api_get_stock_sources_for_product,
    api_get_unallocated_landed_cost_invoices, api_get_receipts_for_allocation
)
from .views import api
# --- MODIFIED: Corrected sales views import ---
from .views.sales import (
    customers, edit_customer, delete_customer, sales_orders, create_sales_order, 
    view_sales_order, delete_sales_order, edit_sales_order_item, delete_sales_order_item,
    create_dispatch, edit_dispatch, cancel_dispatch_view, dispatch_from_sales_order,
    sales_returns_list, create_sales_return, view_sales_return, view_credit_memo_pdf,
    process_inspected_return_view, create_credit_memo_from_return_view
)
from .views import expense_requests
# --- MODIFIED: Corrected financial report views import ---
from .views.financial_reports import (
    trial_balance, profit_and_loss_statement, batch_production_variance_report, 
    product_ledger, general_ledger, tax_reconciliation_report, reconciliation_report, 
    balance_sheet, stock_valuation_report
)
from .views import employees, users
from .views.financials import (
    ap_views,
    ar_views,
    banking_views,
    config_views,
    gl_views,
    overhead_views,
    period_views,
)
from .views.reports import ar as ar_report_views, sales as sales_report_views
from .views import manage_users, edit_user, delete_user
app_name = 'inventory'

urlpatterns = [
    

    # Financial Reports
    path('reports/trial-balance/', trial_balance, name='trial_balance'),
    path('reports/profit-loss/', profit_and_loss_statement, name='profit_and_loss'),
    path('reports/balance-sheet/', balance_sheet, name='balance_sheet'),
    path('reports/product-ledger/', product_ledger, name='product_ledger'),
    path('reports/general-ledger/', general_ledger, name='general_ledger'),
    path('reports/stock-valuation/', stock_valuation_report, name='stock_valuation_report'),
    path('reports/tax-reconciliation/', tax_reconciliation_report, name='tax_reconciliation_report'),
    path('reports/reconciliation/', reconciliation_report, name='reconciliation_report'),
    path('reports/batch-variance/', batch_production_variance_report, name='batch_production_variance_report'),
    
    # --- NEW: Refactored AR Report URLs ---
    path('reports/ar/aging/', ar_report_views.ar_aging_report, name='ar_aging_report'),
    path('reports/ar/aging/customer_detail/<int:customer_id>/', ar_report_views.ar_customer_detail_api, name='ar_customer_detail_api'),
    path('reports/ar/customer-statement/', ar_report_views.customer_statement_report, name='customer_statement_report'),
    
    # ... (rest of the existing URL patterns)
]

urlpatterns = [
    # User Management
    path('users/', manage_users, name='manage_users'),
    path('users/<int:pk>/edit/', edit_user, name='edit_user'),
    path('users/<int:pk>/delete/', delete_user, name='delete_user'),
    # Group & Permission Management
    path('groups/', users.manage_groups, name='manage_groups'),
    path('groups/<int:pk>/edit/', users.edit_group, name='edit_group'),
    path('groups/<int:pk>/delete/', users.delete_group, name='delete_group'),
    # Dashboard & Records
    path('', index, name='receipts'),
    path('records/', records, name='records'),
    path('records/void/<int:pk>/', void_record_view, name='void_record'),
    
    # Quality Control Routes
    path('quarantine/', quarantine_list, name='quarantine_list'),
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

    # --- NEW: Purchase Return Routes ---
    path('purchase_returns/', purchasing_views.purchase_returns_list, name='purchase_returns_list'),
    path('purchase_returns/create/', purchasing_views.create_purchase_return, name='create_purchase_return'),
    path('purchase_return/<int:pk>/', purchasing_views.view_purchase_return, name='view_purchase_return'),
    path('purchase_return/<int:pk>/process/', purchasing_views.process_inventory_return_view, name='process_inventory_return'),
    path('purchase_return/<int:pk>/create_debit_memo/', purchasing_views.create_debit_memo_from_return_view, name='create_debit_memo_from_return'),

    # Template Routes
    path('shop_order_templates/', shop_order_templates, name='shop_order_templates'),
    path('shop_order_templates/delete/<int:pk>/', delete_shop_order_template, name='delete_shop_order_template'),
    path('shop_order_template/<int:pk>/', view_shop_order_template, name='view_shop_order_template'),
    path('shop_order_template/edit/<int:pk>/', edit_shop_order_template, name='edit_shop_order_template'),

    # Batch Routes (Production Plans)
    path('batches/', batches, name='batches'),
    path('batches/create/', create_batch, name='create_batch'),
    path('batch/<int:pk>/', view_batch, name='view_batch'),
    path('batch/cancel/<int:pk>/', cancel_batch_view, name='cancel_batch'),
    path('batch/item/add/<int:batch_pk>/', add_batch_item, name='add_batch_item'),
    path('batch/<int:batch_pk>/update_all/', update_batch_items_bulk, name='update_batch_items_bulk'),
    path('batch/item/return/<int:item_pk>/', return_batch_item_view, name='return_batch_item'),

    # --- NEW: Batch Workflow URLs ---
    path('batch/<int:pk>/submit/', submit_batch_view, name='submit_batch'),
    path('batch/<int:pk>/approve/', approve_batch_view, name='approve_batch'),
    path('batch/<int:pk>/start/', start_production_view, name='start_production'),
    path('batch/<int:pk>/reject/', reject_batch_view, name='reject_batch'),

    # --- NEW: Landed Cost APIs ---
    path('api/landed-cost/invoices/', api.api_get_unallocated_landed_cost_invoices, name='api_get_unallocated_landed_cost_invoices'),
    path('api/landed-cost/receipts/', api.api_get_receipts_for_allocation, name='api_get_receipts_for_allocation'),

    # Finished Product Routes
    path('finished_products/', finished_goods_status, name='finished_products_list'),
    path('finished_goods_status/', finished_goods_status, name='finished_goods_status'),
    path('batch/<int:batch_pk>/receive/<path:individual_batch_number>/', receive_finished_product, name='receive_finished_product'),
    path('finished_product/<int:pk>/', view_finished_product, name='view_finished_product'),
    path('finished_product/<int:pk>/cancel/', cancel_finished_product_receipt_view, name='cancel_finished_product_receipt'),
    path('finished_product/<int:pk>/release/', release_fg_from_quarantine, name='release_fg_from_quarantine'),

    # Production Returns Routes
    path('production_returns/', production_returns, name='production_returns'),
    path('production_returns/cancel/<int:pk>/', cancel_production_return_view, name='cancel_production_return'),

    # Analysis & Visuals
    path('visuals/', visuals, name='visuals'),
    
    # Inventory Counts & Adjustments
    path('inventory_counts/', inventory_counts_list, name='inventory_counts_list'),
    path('inventory_counts/create/', create_inventory_count, name='create_inventory_count'),
    path('inventory_counts/manage/<int:pk>/', manage_inventory_count, name='manage_inventory_count'),
    path('inventory_counts/allocate/<int:pk>/', allocate_inventory_variances, name='allocate_inventory_variances'),

    # Sales Management
    path('customers/', customers, name='customers'),
    path('customers/edit/<int:pk>/', edit_customer, name='edit_customer'),
    path('customers/delete/<int:pk>/', delete_customer, name='delete_customer'),

    # Sales Order Routes
    path('sales_orders/', sales_orders, name='sales_orders'),
    path('sales_orders/create/', create_sales_order, name='create_sales_order'),
    path('sales_order/<int:pk>/', view_sales_order, name='view_sales_order'),
    path('sales_order/<int:pk>/delete/', delete_sales_order, name='delete_sales_order'),
    path('sales_order_item/<int:pk>/edit/', edit_sales_order_item, name='edit_sales_order_item'),
    path('sales_order_item/<int:pk>/delete/', delete_sales_order_item, name='delete_sales_order_item'),
    path('dispatch/create/<int:so_item_pk>/', create_dispatch, name='create_dispatch'),
    path('dispatch/edit/<int:pk>/', edit_dispatch, name='edit_dispatch'),
    path('dispatch/cancel/<int:pk>/', cancel_dispatch_view, name='cancel_dispatch'),
    path('sales_order/<int:so_pk>/dispatch/', dispatch_from_sales_order, name='dispatch_from_sales_order'),

    # Sales Return Routes
    path('sales_returns/', sales_returns_list, name='sales_returns_list'),
    path('sales_order/<int:so_pk>/return/create/', create_sales_return, name='create_sales_return'),
    path('sales_return/<int:pk>/', view_sales_return, name='view_sales_return'),
    path('sales_return/<int:return_pk>/process/', process_inspected_return_view, name='process_inspected_return'),
    path('sales_return/<int:return_pk>/credit_memo/create/', create_credit_memo_from_return_view, name='create_credit_memo_from_return'),
    path('credit_memo/<int:memo_pk>/pdf/', view_credit_memo_pdf, name='view_credit_memo_pdf'),

    # Employee Financials
    path('employees/financials/', employees.employee_financials_dashboard, name='employee_financials_dashboard'),
    path('employees/financials/<int:employee_id>/', employees.employee_advance_detail, name='employee_advance_detail'),
    path('employees/financials/settle/<int:advance_id>/', employees.settle_employee_advance, name='settle_employee_advance'),
    path('employees/manage/', employees.manage_employees, name='manage_employees'),

    # Expense Management
    path('expense_requests/', expense_requests.manage_expense_requests, name='manage_expense_requests'),


    # Financials (A/P, A/R, Banking)
    path('financials/supplier_invoices/', ap_views.supplier_invoices, name='supplier_invoices'),
    path('financials/supplier_invoices/create/', ap_views.create_supplier_invoice, name='create_supplier_invoice'),
    path('financials/supplier_invoice/<int:pk>/', ap_views.view_supplier_invoice, name='view_supplier_invoice'),
    path('financials/supplier_invoice/<int:pk>/post/', ap_views.post_supplier_invoice_view, name='post_supplier_invoice'),
    path('financials/landed_cost_invoices/', ap_views.landed_cost_invoices, name='landed_cost_invoices'),
    path('financials/landed_cost_invoices/create/', ap_views.create_landed_cost_invoice, name='create_landed_cost_invoice'),
    path('financials/landed_cost_invoice/<int:pk>/', ap_views.view_landed_cost_invoice, name='view_landed_cost_invoice'),
    path('financials/landed_cost_invoice/<int:pk>/add_item/', ap_views.add_landed_cost_invoice_item, name='add_landed_cost_invoice_item'),
    path('financials/landed_cost_invoice/<int:pk>/post/', ap_views.post_landed_cost_invoice_view, name='post_landed_cost_invoice'),
    path('financials/supplier_invoice/<int:pk>/allocate_costs/', ap_views.allocate_landed_costs_view, name='allocate_landed_costs'),
    path('financials/supplier_invoice/<int:pk>/delete/', ap_views.delete_supplier_invoice, name='delete_supplier_invoice'),
    path('financials/supplier_invoice/<int:invoice_pk>/apply_payment/', ap_views.apply_payment_to_invoice, name='apply_payment_to_invoice'),
    path('financials/customer_invoices/', ar_views.customer_invoices, name='customer_invoices'),
    path('financials/customer_invoices/create/', ar_views.create_customer_invoice, name='create_customer_invoice'),
    path('financials/customer_invoice/<int:pk>/', ar_views.view_customer_invoice, name='view_customer_invoice'),
    path('financials/customer_invoice/<int:pk>/delete/', ar_views.delete_customer_invoice, name='delete_customer_invoice'),
    path('financials/customer_invoice/<int:invoice_pk>/receive_payment/', ar_views.receive_payment_for_invoice, name='receive_payment_for_invoice'),
    path('financials/customer_payments/', ar_views.customer_payments_list, name='customer_payments_list'),
    path('financials/customer_payment/<int:pk>/', ar_views.view_customer_payment, name='view_customer_payment'),
    path('financials/ar/workbench/', ar_views.ar_cash_application_workbench, name='ar_cash_application_workbench'),
    path('financials/customer_payment/<int:pk>/pdf/', ar_views.view_customer_payment_pdf, name='view_customer_payment_pdf'),
    path('financials/banking/', banking_views.bank_accounts_dashboard, name='bank_accounts_dashboard'),
    path('financials/journal/', gl_views.journal_entries, name='journal_entries'),
    path('financials/journal/create/', gl_views.create_journal_entry, name='create_journal_entry'),
    path('financials/journal/<int:pk>/', gl_views.view_journal_entry, name='view_journal_entry'),
    path('financials/journal/<int:pk>/post/', gl_views.post_journal_entry, name='post_journal_entry'),
    path('financials/fixed_assets/', gl_views.fixed_assets_dashboard, name='fixed_assets_dashboard'),
    
    # Overhead Allocation & Configuration
    path('financials/cost_pools/', config_views.cost_pools_list, name='cost_pools_list'),
    path('financials/allocation_drivers/', config_views.allocation_drivers_list, name='allocation_drivers_list'),
    path('financials/overhead_allocation/', overhead_views.overhead_allocation_workspace, name='overhead_allocation_workspace'),

    # Bank Reconciliation
    path('financials/reconciliation/', banking_views.bank_reconciliations_list, name='bank_reconciliations_list'),
    path('financials/reconciliation/create/', banking_views.create_bank_reconciliation, name='create_bank_reconciliation'),
    path('financials/reconciliation/<int:pk>/manage/', banking_views.manage_bank_reconciliation, name='manage_bank_reconciliation'),
    path('financials/reconciliation/<int:pk>/delete/', banking_views.delete_bank_reconciliation, name='delete_bank_reconciliation'),
    path('financials/reconciliation/<int:pk>/finalize/', banking_views.finalize_reconciliation, name='finalize_reconciliation'),

    # Financial Period Management
    path('financials/periods/', period_views.fiscal_year_list, name='fiscal_year_list'),
    path('financials/periods/create/', period_views.create_fiscal_year, name='create_fiscal_year'),
    path('financials/periods/edit/<int:pk>/', period_views.edit_fiscal_year, name='edit_fiscal_year'),
    path('financials/periods/delete/<int:pk>/', period_views.delete_fiscal_year, name='delete_fiscal_year'),
    path('financials/periods/generate/<int:year_id>/', period_views.generate_monthly_periods, name='generate_monthly_periods'),
    path('financials/periods/create_period/<int:year_id>/', period_views.create_financial_period, name='create_financial_period'),
    path('financials/periods/change_status/<int:period_id>/', period_views.change_period_status, name='change_period_status'),
    path('financials/periods/close_cockpit/<int:period_id>/', period_views.close_period_cockpit, name='close_period_cockpit'),
    path('financials/periods/close_action/<int:period_id>/', period_views.close_period_action, name='close_period_action'),
    path('financials/periods/audit_log/<int:period_id>/', period_views.view_period_audit_log, name='view_period_audit_log'),

    # Reports
    path('reports/trial_balance/', trial_balance, name='trial_balance'),
    path('reports/profit_and_loss/', profit_and_loss_statement, name='profit_and_loss_statement'),
    path('reports/balance_sheet/', balance_sheet, name='balance_sheet'),
    path('reports/tax_reconciliation/', tax_reconciliation_report, name='tax_reconciliation_report'),
    path('reports/production_variance/', batch_production_variance_report, name='batch_production_variance_report'),
    path('reports/reconciliation/', reconciliation_report, name='reconciliation_report'),
    path('reports/general_ledger/', general_ledger, name='general_ledger'),
    path('reports/product_ledger/', product_ledger, name='product_ledger'),
    path('reports/stock_valuation/', stock_valuation_report, name='stock_valuation'),

    # --- NEW: Refactored AR Report URLs ---
    path('reports/ar/aging/', ar_report_views.ar_aging_report, name='ar_aging_report'),
    path('reports/ar/aging/customer_detail/<int:customer_id>/', ar_report_views.ar_customer_detail_api, name='ar_customer_detail_api'),
    path('reports/ar/customer-statement/', ar_report_views.customer_statement_report, name='customer_statement_report'),
    
    # --- NEW: Sales Report URLs ---
    path('reports/sales/by-customer/', sales_report_views.sales_by_customer_report, name='sales_by_customer_report'),
    path('reports/sales/by-product/', sales_report_views.sales_by_product_report, name='sales_by_product_report'),
    path('reports/sales/backlog/', sales_report_views.sales_order_backlog_report, name='sales_order_backlog_report'),

    # API Routes
    path('api/inventory_log/<int:log_pk>/history/', api.api_get_inventory_log_history, name='api_get_inventory_log_history'),
    path('api/batch_details/<int:batch_pk>/', api_batch_details, name='api_batch_details'),
    path('api/batch_analysis/<int:batch_pk>/', api_get_full_batch_analysis, name='api_get_full_batch_analysis'),
    path('api/product_tags/<int:product_id>/', get_product_tags, name='api_product_tags'),
    path('api/supplier/<int:supplier_id>/open_pos/', api_get_open_pos_for_supplier, name='api_get_open_pos_for_supplier'),
    path('api/po/<int:po_id>/items/', api_get_po_items, name='api_get_po_items'),
    path('api/sellable_stock/', api_get_sellable_stock, name='api_get_sell_stock'),
    path('api/get_used_qc_sources/<int:product_pk>/', get_used_qc_sources, name='get_used_qc_sources'),
    path('api/source_log/<int:log_pk>/batches/', api.api_get_batches_for_source_log, name='api_get_batches_for_source_log'),
    path('api/available_stock/<int:product_pk>/', api_get_available_stock, name='api_get_available_stock'),
    path('api/supplier/<int:supplier_id>/uninvoiced_receipts/', ap_views.api_get_uninvoiced_receipts, name='api_get_uninvoiced_receipts'),
    path('api/supplier/<int:supplier_id>/unsettled_expenses/', ap_views.api_get_unsettled_expenses, name='api_get_unsettled_expenses'),
    path('api/customer/<int:customer_id>/open_items/', ar_views.api_get_customer_open_items, name='api_get_customer_open_items'),
    path('api/customer/<int:customer_id>/uninvoiced_dispatches/', ar_views.api_get_uninvoiced_dispatches, name='api_get_uninvoiced_dispatches'),
    path('api/product/<int:product_id>/sources/', api_get_stock_sources_for_product, name='api_get_stock_sources_for_product'),
    path('api/period_checklist/<int:period_id>/', period_views.api_period_checklist_status, name='api_period_checklist_status'),
]