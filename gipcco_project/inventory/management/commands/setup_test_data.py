# gipcco_project/inventory/management/commands/setup_test_data.py

import os
import shutil
from datetime import date, timedelta, datetime
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction, connections
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

from inventory.models import (
    Account, Product, Company, Customer, FiscalYear, FinancialPeriod,
    GeneralAccountingSettings, ProductTypeAccountingSettings,
    ShopOrderTemplate, Batch, FinishedProductReceipt,
    BankAccount, Employee, CostPool, AllocationDriver,
    InventoryLog, PurchaseOrder, PurchaseOrderItem, PurchaseOrderLandedCost, BatchItem,
    SalesOrder, SalesOrderItem, FinishedProductDispatch,
    SupplierInvoice, SupplierInvoiceItem, Payment, PaymentApplication,
    CustomerInvoice, CustomerInvoiceItem, CustomerPaymentApplication,
    BankTransfer, FixedAsset, DepreciationLog, InventoryConsumption,
    InventoryCount, InventoryAdjustment, TemplateItem, ExpenseRequest, EmployeeAdvance,
    AccruedExpense, AccrualLog, SalesReturn, SalesReturnItem, CustomerCreditMemo,
    LandedCostType, LandedCostInvoice, LandedCostInvoiceItem
)
from inventory.services.adjusting_entries_service import run_monthly_accruals
from inventory.services.sales_return_service import process_inspected_return, create_credit_memo_from_return
from inventory.services import batch_service, purchasing_service, production_returns_service, accounting_service

# A dictionary to hold created objects for easy reference
# This avoids querying the DB repeatedly
CONTEXT = {}

def create_chart_of_accounts():
    """Creates a comprehensive and structured chart of accounts for testing."""
    accounts = {}
    
    def create_account(code, name, account_type, parent_code=None):
        parent = accounts.get(parent_code) if parent_code else None
        acc, _ = Account.objects.get_or_create(
            code=code, 
            defaults={'name': name, 'account_type': account_type, 'parent': parent}
        )
        accounts[code] = acc
        return acc

    # Assets
    create_account('100', 'الأصول', Account.AccountType.ASSET)
    create_account('102', 'الأصول المتداولة', Account.AccountType.ASSET, '100')
    create_account('10201', 'النقدية وما في حكمها', Account.AccountType.ASSET, '102')
    create_account('1020101', 'النقدية بالصندوق', Account.AccountType.ASSET, '10201')
    create_account('1020102', 'النقدية بالبنوك', Account.AccountType.ASSET, '10201')
    create_account('1020103', 'النقدية بالبنك الثانوي', Account.AccountType.ASSET, '10201')
    create_account('10202', 'المخزون', Account.AccountType.ASSET, '102')
    create_account('1020201', 'مخزون مواد خام', Account.AccountType.ASSET, '10202')
    create_account('1020202', 'مخزون تعبئة وتغليف', Account.AccountType.ASSET, '10202')
    create_account('1020205', 'مخزون انتاج تحت التشغيل', Account.AccountType.ASSET, '10202')
    create_account('1020206', 'مخزون منتج نهائي', Account.AccountType.ASSET, '10202')
    create_account('1020207', 'مخزون قطع غيار وصيانة', Account.AccountType.ASSET, '10202')
    create_account('1020208', 'مخزون مستهلكات', Account.AccountType.ASSET, '10202')
    create_account('10203', 'العملاء (ذمم مدينة)', Account.AccountType.ASSET, '102')
    create_account('10204', 'أرصدة مدينة أخرى', Account.AccountType.ASSET, '102')
    create_account('1020404', 'ضريبة القيمة المضافة (المدخلات)', Account.AccountType.ASSET, '10204')
    create_account('1020405', 'سلف الموظفين', Account.AccountType.ASSET, '10204')
    create_account('1020406', 'تسوية مرتجعات المبيعات', Account.AccountType.ASSET, '10204') # Clearing Account
    create_account('10205', 'مصروفات مدفوعة مقدماً', Account.AccountType.ASSET, '102')
    create_account('101', 'الأصول الثابتة', Account.AccountType.ASSET, '100')
    create_account('10101', 'آلات ومعدات', Account.AccountType.ASSET, '101')
    create_account('10102', 'أثاث وتركيبات', Account.AccountType.ASSET, '101')

    # Liabilities
    create_account('200', 'الالتزامات', Account.AccountType.LIABILITY)
    create_account('202', 'الالتزامات المتداولة', Account.AccountType.LIABILITY, '200')
    create_account('20201', 'الموردون (ذمم دائنة)', Account.AccountType.LIABILITY, '202')
    create_account('20202', 'أرصدة دائنة أخرى', Account.AccountType.LIABILITY, '202')
    create_account('2020201', 'ضريبة القيمة المضافة (المخرجات)', Account.AccountType.LIABILITY, '20202')
    create_account('2020202', 'ضريبة الخصم من المنبع', Account.AccountType.LIABILITY, '20202')
    create_account('2020203', 'مصروفات مستحقة', Account.AccountType.LIABILITY, '20202')
    create_account('2020204', 'دفعات عملاء مقدمة', Account.AccountType.LIABILITY, '20202') # Customer Deposits
    create_account('20205', 'مجمعات الإهلاك', Account.AccountType.LIABILITY, '202')
    create_account('2020501', 'مجمع إهلاك - آلات ومعدات', Account.AccountType.LIABILITY, '20205')
    create_account('2020502', 'مجمع إهلاك - أثاث وتركيبات', Account.AccountType.LIABILITY, '20205')

    # Revenue
    create_account('400', 'الإيرادات', Account.AccountType.REVENUE)
    create_account('401', 'إيرادات النشاط', Account.AccountType.REVENUE, '400')
    create_account('40101', 'مبيعات منتجات نهائية', Account.AccountType.REVENUE, '401')
    create_account('40102', 'مرتجعات ومسموحات المبيعات', Account.AccountType.REVENUE, '401') # Contra-Revenue
    create_account('402', 'إيرادات أخرى', Account.AccountType.REVENUE, '400')
    create_account('40201', 'عوائد بيع خردة', Account.AccountType.REVENUE, '402')
    create_account('40202', 'مكاسب فروق المخزون', Account.AccountType.REVENUE, '402')

    # Expenses
    create_account('500', 'المصروفات', Account.AccountType.EXPENSE)
    create_account('501', 'تكلفة البضاعة المباعة (COGS)', Account.AccountType.EXPENSE, '500')
    create_account('50101', 'تكلفة مبيعات المنتجات النهائية', Account.AccountType.EXPENSE, '501')
    create_account('502', 'مصروفات التشغيل', Account.AccountType.EXPENSE, '500')
    create_account('50201', 'مصروفات صيانة', Account.AccountType.EXPENSE, '502')
    create_account('50202', 'مصروفات مستهلكات', Account.AccountType.EXPENSE, '502')
    create_account('50203', 'إيجار المصنع', Account.AccountType.EXPENSE, '502')
    create_account('50206', 'مصروفات برامج وتراخيص', Account.AccountType.EXPENSE, '502')
    create_account('50207', 'مصروفات إدارية وعمومية', Account.AccountType.EXPENSE, '502')
    create_account('503', 'خسائر فروق المخزون', Account.AccountType.EXPENSE, '500')
    create_account('50205', 'مصروفات الإهلاك', Account.AccountType.EXPENSE, '502')
    create_account('5020501', 'مصروف إهلاك - آلات ومعدات', Account.AccountType.EXPENSE, '50205')
    create_account('5020502', 'مصروف إهلاك - أثاث وتركيبات', Account.AccountType.EXPENSE, '50205')
    create_account('50208', 'رسوم استشارات', Account.AccountType.EXPENSE, '502')
    create_account('50209', 'مصروف بضاعة تالفة', Account.AccountType.EXPENSE, '502')
    # --- NEW PURCHASING ACCOUNTS ---
    create_account('20206', 'بضاعة مستلمة غير مفوترة (GRNI)', Account.AccountType.LIABILITY, '202')
    create_account('504', 'فروقات أسعار الشراء (PPV)', Account.AccountType.EXPENSE, '500')
    create_account('505', 'فروقات التصنيع', Account.AccountType.EXPENSE, '500') # Manufacturing Variance
    create_account('506', 'إعادة تقييم المخزون', Account.AccountType.EXPENSE, '500') # Inventory Revaluation
    create_account('1020407', 'تسوية تكاليف شحن', Account.AccountType.ASSET, '10204') # Landed Costs Clearing
    create_account('20207', 'تسوية مرتجعات موردين', Account.AccountType.LIABILITY, '202') # Purchase Returns Clearing
    # --- NEW LANDED COST (NETSUITE) ACCOUNTS ---
    create_account('20208', 'تكاليف شحن مستحقة', Account.AccountType.LIABILITY, '202') # Accrued Landed Costs
    create_account('507', 'فروقات تكاليف الشحن', Account.AccountType.EXPENSE, '500') # Landed Cost Variance

    CONTEXT['accounts'] = accounts
    return accounts

class Command(BaseCommand):
    help = 'Resets the database and populates it with a comprehensive set of test data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-reset',
            action='store_true',
            help='Do not reset the database before populating.',
        )

    def handle(self, *args, **options):
        if not options['no_reset']:
            self.reset_database()

        self.stdout.write(self.style.SUCCESS("Starting data population..."))

        # Wrap data creation in a single transaction for performance and atomicity
        with transaction.atomic():
            self.create_base_data()
            self.create_transactional_data()
            self.create_opening_balances()

        self.stdout.write(self.style.SUCCESS("Successfully populated the database with test data."))

    def reset_database(self):
        self.stdout.write("Resetting database...")
        
        # Use the 'flush' command to clear all data from the database.
        # This is cleaner than deleting the file and avoids file lock issues.
        self.stdout.write("Flushing all data from the database...")
        call_command('flush', '--noinput')
        
        self.stdout.write("Running migrations to ensure schema is up-to-date...")
        call_command('migrate')
        self.stdout.write(self.style.SUCCESS("Database reset complete."))

    def create_base_data(self):
        self.stdout.write("1. Creating fiscal year, periods, and chart of accounts...")
        fiscal_year, _ = FiscalYear.objects.get_or_create(
            name="Fiscal Year 2025",
            defaults={'start_date': date(2025, 1, 1), 'end_date': date(2025, 12, 31)}
        )
        period, _ = FinancialPeriod.objects.get_or_create(
            fiscal_year=fiscal_year,
            name="September 2025",
            defaults={
                'start_date': date(2025, 9, 1),
                'end_date': date(2025, 9, 30),
                'status': FinancialPeriod.Status.OPEN
            }
        )
        period_2, _ = FinancialPeriod.objects.get_or_create(
            fiscal_year=fiscal_year,
            name="October 2025",
            defaults={
                'start_date': date(2025, 10, 1),
                'end_date': date(2025, 11, 30),
                'status': FinancialPeriod.Status.OPEN
            }
        )
        CONTEXT['period'] = period
        CONTEXT['period_2'] = period_2
        accounts = create_chart_of_accounts()

        self.stdout.write("2. Configuring accounting settings...")
        GeneralAccountingSettings.objects.create(
            pk=1,
            accounts_payable=accounts['20201'],
            accounts_receivable=accounts['10203'],
            vat_receivable=accounts['1020404'],
            vat_payable=accounts['2020201'],
            wip_inventory=accounts['1020205'],
            withholding_tax_payable=accounts['2020202'],
            finished_goods_inventory=accounts['1020206'],
            inventory_adjustment_loss_account=accounts['503'],
            inventory_adjustment_gain_account=accounts['40202'],
            employee_advances_receivable=accounts['1020405'],
            prepaid_expenses_account=accounts['10205'],
            accrued_expenses_account=accounts['2020203'],
            sales_returns_account=accounts['40102'],
            sales_returns_clearing_account=accounts['1020406'],
            damaged_goods_expense_account=accounts['50209'],
            customer_deposits_account=accounts['2020204'],
            goods_received_not_invoiced_account=accounts['20206'],
            purchase_price_variance_account=accounts['504'],
            landed_costs_clearing_account=accounts['1020407'],
            purchase_returns_clearing_account=accounts['20207'],
            manufacturing_variance_account=accounts['505'],
            inventory_revaluation_account=accounts['506'],
            accrued_landed_costs_account=accounts['20208'],
            landed_cost_variance_account=accounts['507']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.RAW_MATERIAL,
            inventory_account=accounts['1020201'],
            cogs_or_expense_account=accounts['50101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.PACKAGING,
            inventory_account=accounts['1020202'],
            cogs_or_expense_account=accounts['50101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.FINAL_PRODUCT,
            inventory_account=accounts['1020206'],
            cogs_or_expense_account=accounts['50101'],
            sales_revenue_account=accounts['40101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.MRO,
            inventory_account=accounts['1020207'],
            cogs_or_expense_account=accounts['50201']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.CONSUMABLE,
            inventory_account=accounts['1020208'],
            cogs_or_expense_account=accounts['50207']
        )

        self.stdout.write("3. Creating base operational objects (companies, products, etc.)...")
        # Create multiple suppliers, customers, and products
        supplier1, _ = Company.objects.get_or_create(name="Global Pharma Supplies")
        supplier2, _ = Company.objects.get_or_create(name="Advanced Medical Packaging Inc.")
        supplier3, _ = Company.objects.get_or_create(name="PetroChem Lubricants")
        supplier4, _ = Company.objects.get_or_create(name="Innovate Solutions Consulting")
        supplier5, _ = Company.objects.get_or_create(name="Global Freight Forwarders")
        CONTEXT['suppliers'] = {'pharma': supplier1, 'packaging': supplier2, 'mro': supplier3, 'consulting': supplier4, 'shipping': supplier5}

        customer1, _ = Customer.objects.get_or_create(name="City Central Pharmacy")
        customer2, _ = Customer.objects.get_or_create(name="County General Hospital")
        customer3, _ = Customer.objects.get_or_create(name="Rural Health Clinic")
        CONTEXT['customers'] = {'pharmacy': customer1, 'hospital': customer2, 'clinic': customer3}
        
        # Raw Materials
        rm1, _ = Product.objects.get_or_create(code="RM-SALINE-001", defaults={'name': "Saline Solution", 'product_type': Product.ProductType.RAW_MATERIAL, 'unit': "Liter"})
        rm2, _ = Product.objects.get_or_create(code="RM-GLUCOSE-001", defaults={'name': "Glucose Powder", 'product_type': Product.ProductType.RAW_MATERIAL, 'unit': "KG"})
        rm3, _ = Product.objects.get_or_create(code="RM-BAG-PVC-500", defaults={'name': "PVC Bag 500ml", 'product_type': Product.ProductType.PACKAGING, 'unit': "Unit"})
        
        # Final Products
        fp1, _ = Product.objects.get_or_create(code="FP-IVDRIP-500", defaults={'name': "Saline IV Drip Bag 500ml", 'product_type': Product.ProductType.FINAL_PRODUCT, 'unit': "Bag"})
        fp2, _ = Product.objects.get_or_create(code="FP-GLUDRIP-250", defaults={'name': "Glucose Drip Bag 250ml", 'product_type': Product.ProductType.FINAL_PRODUCT, 'unit': "Bag"})

        # MRO & Consumables
        mro1, _ = Product.objects.get_or_create(code="MRO-LUBE-001", defaults={'name': "Machine Lubricant", 'product_type': Product.ProductType.MRO, 'unit': "Can"})
        consumable1, _ = Product.objects.get_or_create(code="CONSUM-SFW-001", defaults={'name': "Annual Antivirus License", 'product_type': Product.ProductType.CONSUMABLE, 'unit': "Unit", 'is_amortizable': True})
        
        CONTEXT['products'] = {
            'saline': rm1, 'glucose': rm2, 'pvc_bag': rm3,
            'saline_drip': fp1, 'glucose_drip': fp2,
            'lubricant': mro1,
            'antivirus': consumable1
        }

        bank_acct, _ = BankAccount.objects.get_or_create(name="Main Business Bank Account", defaults={'gl_account': accounts['1020102']})
        CONTEXT['bank_account'] = bank_acct
        secondary_bank_acct, _ = BankAccount.objects.get_or_create(name="Secondary Business Bank Account", defaults={'gl_account': accounts['1020103']})
        CONTEXT['secondary_bank_account'] = secondary_bank_acct
        
        user, created = User.objects.get_or_create(username='testuser', defaults={'is_staff': True, 'is_superuser': True})
        if created:
            user.set_password('password')
            user.save()
        CONTEXT['user'] = user
        
        employee, _ = Employee.objects.get_or_create(employee_id='E-001', defaults={'first_name': 'John', 'last_name': 'Doe'})
        CONTEXT['employee'] = employee

        parent_pool, _ = CostPool.objects.get_or_create(name="Factory Overhead", code="FOH")
        CostPool.objects.get_or_create(name="Factory Rent", code="FOH-RENT", parent=parent_pool, defaults={'gl_account': accounts['50203']})
        CostPool.objects.get_or_create(name="Factory Maintenance", code="FOH-MAINT", parent=parent_pool, defaults={'gl_account': accounts['50201']})
        admin_pool, _ = CostPool.objects.get_or_create(name="General & Admin", code="G&A")
        CostPool.objects.get_or_create(name="G&A Software Costs", code="G&A-SFW", parent=admin_pool, defaults={'gl_account': accounts['50206']})
        CONTEXT['cost_pools'] = {
            'rent': CostPool.objects.get(code="FOH-RENT"),
            'maintenance': CostPool.objects.get(code="FOH-MAINT"),
            'software': CostPool.objects.get(code="G&A-SFW")
        }
        AllocationDriver.objects.get_or_create(name=AllocationDriver.DriverChoices.MACHINE_HOURS)

        # Create Fixed Assets
        asset1, _ = FixedAsset.objects.get_or_create(
            asset_tag="MACHINE-001",
            defaults={
                'name': "Production Filling Machine",
                'gl_account': CONTEXT['accounts']['10101'],
                'depreciation_expense_account': CONTEXT['accounts']['5020501'],
                'accumulated_depreciation_account': CONTEXT['accounts']['2020501'],
                'purchase_date': "2024-01-01",
                'purchase_cost': Decimal("120000.000"),
                'depreciation_start_date': "2024-01-01",
                'useful_life_years': 10,
                'salvage_value': Decimal("0.000")
            }
        )
        CONTEXT['asset1'] = asset1

        asset2, _ = FixedAsset.objects.get_or_create(
            asset_tag="FURN-001",
            defaults={
                'name': "Office Furniture Set",
                'gl_account': CONTEXT['accounts']['10102'],
                'depreciation_expense_account': CONTEXT['accounts']['5020502'],
                'accumulated_depreciation_account': CONTEXT['accounts']['2020502'],
                'purchase_date': "2023-07-01",
                'purchase_cost': Decimal("30000.000"),
                'depreciation_start_date': "2023-07-01",
                'useful_life_years': 5,
                'salvage_value': Decimal("0.000")
            }
        )
        CONTEXT['asset2'] = asset2

        # Create templates with items (Bill of Materials)
        template1, _ = ShopOrderTemplate.objects.get_or_create(name="Standard Saline IV Drip Template", defaults={'final_product': fp1, 'bottle_size_ml': 500})
        TemplateItem.objects.get_or_create(template=template1, primitive_product=rm1, defaults={'theoretical_quantity': 0.5}) # 0.5L Saline
        TemplateItem.objects.get_or_create(template=template1, primitive_product=rm3, defaults={'theoretical_quantity': 1.0}) # 1 PVC Bag
        CONTEXT['template1'] = template1

        template2, _ = ShopOrderTemplate.objects.get_or_create(name="Standard Glucose IV Drip Template", defaults={'final_product': fp2, 'bottle_size_ml': 250})
        TemplateItem.objects.get_or_create(template=template2, primitive_product=rm2, defaults={'theoretical_quantity': 0.1}) # 0.1KG Glucose
        TemplateItem.objects.get_or_create(template=template2, primitive_product=rm3, defaults={'theoretical_quantity': 1.0}) # 1 PVC Bag
        CONTEXT['template2'] = template2


    def create_transactional_data(self):
        self.stdout.write("4. Creating sample transactions...")
        
        # Purchase Order and Receipt
        po, _ = PurchaseOrder.objects.get_or_create(
            po_number="PO-DEMO-001",
            defaults={
                'supplier': CONTEXT['suppliers']['pharma'],
                'order_date': date(2025, 9, 2)
            }
        )
        po_item, _ = PurchaseOrderItem.objects.get_or_create(
            purchase_order=po,
            product=CONTEXT['products']['saline'],
            defaults={
                'quantity_ordered': 200.0,
                'base_price_per_unit': Decimal("10.500"),
                'vat_rate': Decimal("0.14"),
                'withholding_tax_rate': Decimal("0.01")
            }
        )
        log, _ = InventoryLog.objects.get_or_create(
            po_item=po_item,
            defaults={
                'product': CONTEXT['products']['saline'],
                'company': CONTEXT['suppliers']['pharma'],
                'quantity': 200.0,
                'timestamp': timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0)),
                'release_timestamp': timezone.make_aware(timezone.datetime(2025, 9, 5, 11, 0, 0)),
                'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("10.500"),
                'vat_amount': Decimal("294.000"), # 200 * 10.5 * 0.14
                'withholding_tax_amount': Decimal("21.000") # 200 * 10.5 * 0.01
            }
        )
        CONTEXT['log1'] = log
        self.stdout.write("   - Created Purchase Order and received 200L of Saline Solution.")

        # Production
        batch, created = Batch.objects.get_or_create(
            shop_order_number="SO-DEMO-001",
            defaults={
                'template': CONTEXT['template1'],
                'batch_number': "B-DEMO-001",
                'creation_date': timezone.make_aware(timezone.datetime(2025, 9, 10, 9, 0, 0)),
            }
        )
        
        # If the batch is new (or still a draft), create items and run workflow
        if created:
             BatchItem.objects.create(
                batch=batch,
                primitive_product=CONTEXT['products']['saline'],
                theoretical_quantity=80.0,
                actual_quantity=82.5,
                source_log=log
            )

        if batch.status == Batch.Status.DRAFT:
            batch = batch_service.submit_batch_for_approval(batch, CONTEXT['user'])
            batch = batch_service.approve_batch(batch, CONTEXT['user'])
            batch = batch_service.start_batch_production(batch)
        
        receipt, _ = FinishedProductReceipt.objects.get_or_create(
            individual_batch_number="FPB-DEMO-001",
            defaults={
                'batch': batch,
                'receipt_date': date(2025, 9, 12),
                'release_date': date(2025, 9, 12),
                'total_cost': Decimal("866.250"), # 82.5 * 10.5
                'total_quantity_produced': 150.0,
                'status': FinishedProductReceipt.Status.RELEASED
            }
        )
        CONTEXT['receipt'] = receipt
        self.stdout.write("   - Created a production batch, consuming 82.5L to produce 150 IV Bags.")

        # Production Return Workflow
        self.stdout.write("   - Creating a production return...")
        production_returns_service.create_production_return(
            product_id=CONTEXT['products']['saline'].id,
            source_log_id=log.id,
            quantity=2.5,
            return_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 10, 0, 0)),
            notes="Excess material returned from batch SO-DEMO-001"
        )
        self.stdout.write("     - Returned 2.5L of Saline Solution from the batch.")

        self.stdout.write("   - Creating and cancelling a production return...")
        return_to_cancel = production_returns_service.create_production_return(
            product_id=CONTEXT['products']['saline'].id,
            source_log_id=log.id,
            quantity=1.0,
            return_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 11, 0, 0)),
            notes="To be cancelled"
        )
        production_returns_service.cancel_production_return(
            prod_return=return_to_cancel,
            user=CONTEXT['user'],
            justification="Entered in error."
        )
        self.stdout.write("     - Created and then cancelled a production return for 1.0L of Saline.")

        # Sales
        so, _ = SalesOrder.objects.get_or_create(
            so_number="SALE-DEMO-001",
            defaults={
                'customer': CONTEXT['customers']['pharmacy'],
                'order_date': date(2025, 9, 15)
            }
        )
        so_item, _ = SalesOrderItem.objects.get_or_create(
            sales_order=so,
            finished_product=receipt,
            defaults={
                'quantity_ordered': 50.0,
                'base_price_per_unit': Decimal("25.000"),
                'vat_rate': Decimal("0.14")
            }
        )
        dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=so_item,
            finished_product=receipt, # <-- FIX: Added the required foreign key
            quantity=50.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 16, 14, 0, 0)),
            cost_at_dispatch=Decimal("288.750") # 866.250 / 150 * 50
        )
        self.stdout.write("   - Created a sales order and dispatched 50 IV Bags.")

        # Sales Return Workflow
        self.stdout.write("   - Starting Sales Return Workflow...")
        sales_return = SalesReturn.objects.create(
            customer=CONTEXT['customers']['pharmacy'],
            return_date=date(2025, 9, 18),
            sales_order=so,
            status=SalesReturn.Status.PENDING_INSPECTION
        )
        # Return 10 items, 8 to stock and 2 to be scrapped
        return_item_good = SalesReturnItem.objects.create(
            sales_return=sales_return,
            original_dispatch=dispatch,
            quantity_returned=8.0,
            disposition=SalesReturnItem.Disposition.RETURN_TO_STOCK
        )
        return_item_scrap = SalesReturnItem.objects.create(
            sales_return=sales_return,
            original_dispatch=dispatch,
            quantity_returned=2.0,
            disposition=SalesReturnItem.Disposition.SCRAP
        )
        sales_return.status = SalesReturn.Status.PENDING_PROCESSING
        sales_return.save()
        self.stdout.write("     - Created Sales Return with 8 items for stock, 2 for scrap.")

        # Process the inspected return
        process_inspected_return(sales_return)
        self.stdout.write("     - Processed the inspected return, creating inventory adjustments.")

        # Create the credit memo
        create_credit_memo_from_return(
            sales_return=sales_return,
            memo_number="CM-DEMO-001",
            memo_date=date(2025, 9, 19)
        )
        self.stdout.write("     - Created the final credit memo for the customer.")

        # Invoicing and Payments
        self.stdout.write("   - Creating, posting, and paying a supplier invoice...")
        log = CONTEXT['log1']
        actual_subtotal = log.base_unit_price * Decimal(str(log.quantity))
        actual_vat = log.vat_amount

        # Create the invoice in Draft status
        sup_inv, created = SupplierInvoice.objects.get_or_create(
            invoice_number="GS-INV-001",
            defaults={
                'supplier': CONTEXT['suppliers']['pharma'],
                'invoice_date': date(2025, 9, 6),
                'due_date': date(2025, 10, 6),
                'status': SupplierInvoice.InvoiceStatus.DRAFT,
                'actual_subtotal': actual_subtotal,
                'actual_vat': actual_vat
            }
        )
        
        # Only proceed if the invoice was newly created to avoid re-processing
        if created:
            SupplierInvoiceItem.objects.create(invoice=sup_inv, receipt=log, amount=log.total_cost)
            
            # Post the invoice to perform the 3-way match
            purchasing_service.post_supplier_invoice(sup_inv)
            self.stdout.write("     - Posted invoice, clearing GRNI and creating A/P liability.")

            # Now, create the payment against the posted invoice
            # The amount to pay is the final A/P liability
            amount_to_pay = actual_subtotal + actual_vat - log.withholding_tax_amount
            payment_out = Payment.objects.create(
                payment_date=date(2025, 9, 20),
                amount=amount_to_pay,
                bank_account=CONTEXT['bank_account'],
                payment_type=Payment.PaymentType.PAYMENT_OUT,
                description="Payment for PO-DEMO-001",
                supplier=CONTEXT['suppliers']['pharma']
            )
            PaymentApplication.objects.create(payment=payment_out, invoice=sup_inv, amount_applied=payment_out.amount)
            self.stdout.write("   - Created a payment to settle the supplier invoice.")
        else:
            self.stdout.write(self.style.WARNING("   - Supplier invoice already exists, skipping creation and payment."))

        # Purchase and receive MRO item (lubricant) so it's in stock
        po_mro, _ = PurchaseOrder.objects.get_or_create(
            po_number="PO-DEMO-MRO-001",
            defaults={
                'supplier': CONTEXT['suppliers']['mro'],
                'order_date': date(2025, 9, 3)
            }
        )
        po_item_mro, _ = PurchaseOrderItem.objects.get_or_create(
            purchase_order=po_mro,
            product=CONTEXT['products']['lubricant'],
            defaults={
                'quantity_ordered': 10.0,
                'base_price_per_unit': Decimal("50.000"),
                'vat_rate': Decimal("0.14"),
                'withholding_tax_rate': Decimal("0.00")
            }
        )
        log_mro, _ = InventoryLog.objects.get_or_create(
            po_item=po_item_mro,
            defaults={
                'product': CONTEXT['products']['lubricant'],
                'company': CONTEXT['suppliers']['mro'],
                'quantity': 10.0,
                'timestamp': timezone.make_aware(timezone.datetime(2025, 9, 6, 10, 0, 0)),
                'release_timestamp': timezone.make_aware(timezone.datetime(2025, 9, 6, 11, 0, 0)),
                'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("50.000"),
                'vat_amount': Decimal("70.000"),
                'withholding_tax_amount': Decimal("0.000")
            }
        )
        CONTEXT['log_mro'] = log_mro
        self.stdout.write("   - Received 10 Cans of Machine Lubricant into inventory.")

        # Run depreciation for the current period
        DepreciationLog.objects.create(
            asset=CONTEXT['asset1'], 
            period_date="2025-09-30", 
            amount=Decimal("1000.000") # 120,000 / 10 years / 12 months
        )
        self.stdout.write("   - Ran depreciation for September for the Filling Machine.")

        self.stdout.write("   - Creating sample Expense Requests...")
        from inventory.services import approval_service, expense_service

        # a) Pending Direct Expense (Direct Payment)
        ExpenseRequest.objects.create(
            requested_by=CONTEXT['user'],
            request_type=ExpenseRequest.RequestType.DIRECT_EXPENSE,
            request_date=date(2025, 9, 18),
            description="Catering for team meeting",
            amount=Decimal("350.00"),
            cost_pool=CONTEXT['cost_pools']['software'],
            status=ExpenseRequest.Status.PENDING,
            settlement_method=ExpenseRequest.SettlementMethod.DIRECT_PAYMENT,
            bank_account=CONTEXT['bank_account']
        )

        # b) Pending Direct Expense (Accrue & Pay Later)
        ExpenseRequest.objects.create(
            requested_by=CONTEXT['user'],
            request_type=ExpenseRequest.RequestType.DIRECT_EXPENSE,
            request_date=date(2025, 9, 19),
            description="Urgent maintenance supplies from local vendor",
            amount=Decimal("800.00"),
            cost_pool=CONTEXT['cost_pools']['maintenance'],
            status=ExpenseRequest.Status.PENDING,
            settlement_method=ExpenseRequest.SettlementMethod.ACCRUE_AND_PAY_LATER,
            supplier=CONTEXT['suppliers']['mro']
        )

        # c) Approved Inventory Expense
        approved_req = ExpenseRequest.objects.create(
            requested_by=CONTEXT['user'],
            request_type=ExpenseRequest.RequestType.INVENTORY_EXPENSE,
            request_date=date(2025, 9, 15),
            description="Lubricant for Machine-001",
            product=CONTEXT['products']['lubricant'],
            quantity=Decimal("2.0"),
            cost_pool=CONTEXT['cost_pools']['maintenance'],
            status=ExpenseRequest.Status.PENDING # Will be approved next
        )
        approval_service.approve_request(approved_req.id, CONTEXT['user'])

        # d) Rejected Capitalization Request
        rejected_req = ExpenseRequest.objects.create(
            requested_by=CONTEXT['user'],
            request_type=ExpenseRequest.RequestType.INVENTORY_CAPITALIZE,
            request_date=date(2025, 9, 11),
            description="Upgrade parts for Office Furniture",
            product=CONTEXT['products']['lubricant'], # Not a realistic product, but fine for demo
            quantity=Decimal("5.0"),
            fixed_asset=CONTEXT['asset2'],
            status=ExpenseRequest.Status.PENDING,
        )
        approval_service.reject_request(rejected_req.id, CONTEXT['user'], "This is not a capitalizable expense.")
        self.stdout.write("   - Created PENDING, APPROVED, and REJECTED expense requests.")

        self.stdout.write("   - Creating full Accrual-to-Settlement workflow...")
        # e) Create and approve an Accrual request
        accrual_req = ExpenseRequest.objects.create(
            requested_by=CONTEXT['user'],
            request_type=ExpenseRequest.RequestType.ACCRUAL,
            request_date=date(2025, 9, 1),
            description="Q4 Financial Consulting Services",
            amount=Decimal("6000.00"), # Total for 3 months
            expense_account=CONTEXT['accounts']['50208'],
            amortization_start_date=date(2025, 9, 1), # Using amortization fields for date range
            amortization_end_date=date(2025, 11, 30),
            status=ExpenseRequest.Status.PENDING,
            supplier=CONTEXT['suppliers']['consulting']
        )
        approval_service.approve_request(accrual_req.id, CONTEXT['user'])
        
        # Simulate the September period-end process by calling the actual service
        self.stdout.write("     - Running monthly accrual service for September...")
        run_monthly_accruals(CONTEXT['period'])

        # Find the log that was just created by the service
        accrued_expense_schedule = AccruedExpense.objects.get(source_request=accrual_req)
        sept_log = AccrualLog.objects.get(
            accrued_expense=accrued_expense_schedule,
            financial_period=CONTEXT['period']
        )

        # Create the actual invoice that arrives later
        consulting_invoice = SupplierInvoice.objects.create(
            supplier=CONTEXT['suppliers']['consulting'],
            invoice_number="INV-CONSULT-SEP",
            invoice_date=date(2025, 10, 5),
            due_date=date(2025, 10, 31),
            total_amount=Decimal("2150.00") # Actual is higher
        )
        
        # Settle the September accrual with the actual invoice
        expense_service.settle_accrual(
            user=CONTEXT['user'],
            accrual_log_id=sept_log.id,
            invoice_id=consulting_invoice.id
        )
        self.stdout.write("   - Created and settled a sample accrual for consulting services.")


        self.stdout.write("   - Creating sample Employee Advance...")
        # Create a dummy payment for the advance source
        advance_payment = Payment.objects.create(
            payment_date=date(2025, 9, 8),
            amount=Decimal("750.00"),
            bank_account=CONTEXT['bank_account'],
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Cash advance for John Doe"
        )
        EmployeeAdvance.objects.create(
            employee=CONTEXT['employee'],
            advance_date=date(2025, 9, 8),
            amount=Decimal("750.00"),
            source_payment=advance_payment,
            status=EmployeeAdvance.Status.OPEN
        )
        self.stdout.write("   - Created an OPEN employee advance.")

        # Purchase Return Workflow
        self.stdout.write("   - Starting Purchase Return Workflow...")
        from inventory.models import PurchaseReturn, PurchaseReturnItem
        # Step 1: Create the return object
        pr = PurchaseReturn.objects.create(
            supplier=CONTEXT['suppliers']['mro'],
            return_date=date(2025, 9, 25),
            status=PurchaseReturn.Status.PENDING
        )
        PurchaseReturnItem.objects.create(
            purchase_return=pr,
            original_receipt=log_mro,
            quantity_returned=3.0
        )
        self.stdout.write("     - Created Purchase Return for 3 cans of lubricant.")

        # Step 2: Process the inventory movement (creates negative adjustment)
        purchasing_service.process_inventory_return(CONTEXT['user'], pr)
        self.stdout.write("     - Processed inventory return, creating adjustment.")

        # Step 3: Create the debit memo
        purchasing_service.create_debit_memo_from_return(
            user=CONTEXT['user'],
            purchase_return=pr,
            memo_data={'memo_number': 'DM-001', 'memo_date': date(2025, 9, 26)}
        )
        self.stdout.write("     - Created supplier debit memo.")

        # Partially Received & Closed PO
        po_partial, _ = PurchaseOrder.objects.get_or_create(
            po_number="PO-DEMO-PARTIAL",
            defaults={
                'supplier': CONTEXT['suppliers']['packaging'],
                'order_date': date(2025, 9, 11),
                'status': PurchaseOrder.Status.PENDING
            }
        )
        po_item_partial, _ = PurchaseOrderItem.objects.get_or_create(
            purchase_order=po_partial,
            product=CONTEXT['products']['pvc_bag'],
            defaults={
                'quantity_ordered': 1000.0,
                'base_price_per_unit': Decimal("0.750"),
                'vat_rate': Decimal("0.14"),
                'withholding_tax_rate': Decimal("0.00")
            }
        )
        log_partial = InventoryLog.objects.create(
            po_item=po_item_partial,
            product=CONTEXT['products']['pvc_bag'],
            company=CONTEXT['suppliers']['packaging'],
            quantity=950.0, # Under-delivered
            timestamp=timezone.make_aware(timezone.datetime(2025, 9, 15, 10, 0, 0)),
            status=InventoryLog.Status.QUARANTINED,
            base_unit_price=Decimal("0.750")
        )
        # Simulate the user checking the "final receipt" box for this under-delivery
        purchasing_service.update_po_status_after_receipt(log_partial.id, is_final_receipt=True)
        self.stdout.write("   - Created a partially received PO and manually closed the line short.")

        self.stdout.write("   - Starting NetSuite-Style Landed Cost Workflow...")
        
        # 1. Setup: Create a new PO with estimated landed costs
        freight_cost_type, _ = LandedCostType.objects.get_or_create(name="Ocean Freight")
        product1 = CONTEXT['products']['glucose']
        product2 = CONTEXT['products']['pvc_bag']
        supplier = CONTEXT['suppliers']['pharma']
        shipping_vendor = CONTEXT['suppliers']['shipping']

        po_price1 = Decimal('25.000')
        po_qty1 = 500  # Value = 12500
        po_price2 = Decimal('2.000')
        po_qty2 = 2500 # Value = 5000
        # Total value = 17500. Allocation: 12500/17500 = ~71.43%, 5000/17500 = ~28.57%
        
        total_estimated_freight = Decimal('1500.000')

        po_lc = purchasing_service.create_purchase_order(
            user=CONTEXT['user'],
            po_data={'po_number': 'PO-LC-DEMO', 'supplier_id': supplier.id, 'order_date': date(2025, 9, 28)},
            items_data=[
                {
                    'product_id': product1.id, 'quantity': po_qty1, 'base_price_per_unit': po_price1,
                    'vat_rate': '0.0', 'withholding_tax_rate': '0.0', 'landed_cost_allocation_percentage': '71.43'
                },
                {
                    'product_id': product2.id, 'quantity': po_qty2, 'base_price_per_unit': po_price2,
                    'vat_rate': '0.0', 'withholding_tax_rate': '0.0', 'landed_cost_allocation_percentage': '28.57'
                }
            ],
            landed_costs_data=[
                {'cost_type_id': freight_cost_type.id, 'estimated_amount': total_estimated_freight}
            ]
        )
        self.stdout.write(f"     - Created PO {po_lc.po_number} with estimated landed costs.")

        # 2. Receive goods for the PO. Signals will handle JE creation and cost capitalization.
        po_item1 = po_lc.items.get(product=product1)
        po_item2 = po_lc.items.get(product=product2)

        InventoryLog.objects.create(
            product=product1,
            company=supplier,
            quantity=po_qty1,
            timestamp=timezone.make_aware(datetime(2025, 10, 2, 9, 0)),
            release_timestamp=timezone.make_aware(datetime(2025, 10, 2, 10, 0)),
            status=InventoryLog.Status.RELEASED,
            qc_no="QC-LC-001",
            po_item=po_item1,
            base_unit_price=po_price1,
            costing_unit_price=po_price1 # Initial, will be updated by signal
        )
        self.stdout.write(f"     - Received {po_qty1} KG of {product1.name}.")

        InventoryLog.objects.create(
            product=product2,
            company=supplier,
            quantity=po_qty2,
            timestamp=timezone.make_aware(datetime(2025, 10, 2, 9, 30)),
            release_timestamp=timezone.make_aware(datetime(2025, 10, 2, 10, 30)),
            status=InventoryLog.Status.RELEASED,
            qc_no="QC-LC-002",
            po_item=po_item2,
            base_unit_price=po_price2,
            costing_unit_price=po_price2 # Initial, will be updated by signal
        )
        self.stdout.write(f"     - Received {po_qty2} units of {product2.name}.")

        # 3. Create and post the actual landed cost invoice with a variance.
        actual_freight_cost = Decimal('1625.000') # Unfavorable variance of 125
        lc_invoice = LandedCostInvoice.objects.create(
            vendor=shipping_vendor,
            invoice_number='LC-INV-DEMO-01',
            invoice_date=date(2025, 10, 5),
            total_amount=actual_freight_cost,
            purchase_order=po_lc,
            status=LandedCostInvoice.Status.DRAFT
        )
        LandedCostInvoiceItem.objects.create(
            landed_cost_invoice=lc_invoice,
            cost_type=freight_cost_type,
            amount=actual_freight_cost
        )

        purchasing_service.post_landed_cost_invoice(lc_invoice, CONTEXT['user'])
        self.stdout.write(f"     - Posted Landed Cost Invoice {lc_invoice.invoice_number} with a variance.")

        self.stdout.write("   - Setting up A/R Workbench test scenarios...")
        # Scenario 1: Open Invoice and Credit Memo for "City Central Pharmacy"
        # Create an invoice for the dispatch made earlier
        invoice_amount = so_item.base_price_per_unit * Decimal(str(dispatch.quantity)) * (Decimal('1') + so_item.vat_rate)
        cust_inv_1, _ = CustomerInvoice.objects.get_or_create(
            invoice_number="INV-PHARM-001",
            defaults={
                'customer': CONTEXT['customers']['pharmacy'],
                'invoice_date': date(2025, 9, 17),
                'due_date': date(2025, 10, 17),
                'total_amount': invoice_amount,
                'sales_order': so
            }
        )
        CustomerInvoiceItem.objects.get_or_create(invoice=cust_inv_1, dispatch=dispatch, defaults={'amount': invoice_amount})
        self.stdout.write("     - Created open invoice for City Central Pharmacy.")

        # Scenario 2: Open Invoice and Unapplied Payment for "County General Hospital"
        # a) Create a new SO, dispatch, and invoice
        so_hosp, _ = SalesOrder.objects.get_or_create(
            so_number="SALE-DEMO-HOSP-001",
            defaults={
                'customer': CONTEXT['customers']['hospital'],
                'order_date': date(2025, 9, 20)
            }
        )
        so_item_hosp, _ = SalesOrderItem.objects.get_or_create(
            sales_order=so_hosp,
            finished_product=receipt,
            defaults={
                'quantity_ordered': 20.0,
                'base_price_per_unit': Decimal("26.000"),
                'vat_rate': Decimal("0.14")
            }
        )
        dispatch_hosp = FinishedProductDispatch.objects.create(
            sales_order_item=so_item_hosp,
            finished_product=receipt,
            quantity=20.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 21, 10, 0, 0)),
            cost_at_dispatch=receipt.unit_cost * 20
        )
        invoice_amount_hosp = so_item_hosp.base_price_per_unit * Decimal(str(dispatch_hosp.quantity)) * (Decimal('1') + so_item_hosp.vat_rate)
        cust_inv_2, _ = CustomerInvoice.objects.get_or_create(
            invoice_number="INV-HOSP-001",
            defaults={
                'customer': CONTEXT['customers']['hospital'],
                'invoice_date': date(2025, 9, 22),
                'due_date': date(2025, 10, 22),
                'total_amount': invoice_amount_hosp,
                'sales_order': so_hosp
            }
        )
        CustomerInvoiceItem.objects.get_or_create(invoice=cust_inv_2, dispatch=dispatch_hosp, defaults={'amount': invoice_amount_hosp})
        self.stdout.write("     - Created open invoice for County General Hospital.")

        # b) Create an unapplied payment for the same customer
        Payment.objects.create(
            payment_date=date(2025, 9, 25),
            amount=Decimal("300.000"),
            bank_account=CONTEXT['bank_account'],
            payment_type=Payment.PaymentType.PAYMENT_IN,
            description="On-account payment from County General Hospital",
            customer=CONTEXT['customers']['hospital']
        )
        self.stdout.write("     - Created unapplied on-account payment for County General Hospital.")


    def create_opening_balances(self):
        self.stdout.write("5. Creating opening balances (if any)...")
        # This is where you would add logic to create opening balance JEs
        pass


    def create_opening_balances(self):
        """Creates and posts a comprehensive opening balance entry."""
        self.stdout.write("5. Creating and posting opening balances for Jan 1, 2025...")
        from inventory.services.accounting_service import create_je_for_opening_balance
        from inventory.models import OpeningBalanceEntry, OpeningBalanceEntryLine, OpeningBalanceSubLedgerDetail
        # --- FIX: Import signal components to temporarily disconnect the receiver ---
        from django.db.models.signals import post_save
        from inventory.signals import handle_fg_receipt_save

        migration_date = date(2025, 1, 1)
        fy_2025 = FiscalYear.objects.first()
        FinancialPeriod.objects.get_or_create(
            name="January 2025",
            fiscal_year=fy_2025,
            defaults={
                'start_date': migration_date,
                'end_date': date(2025, 1, 31),
                'status': FinancialPeriod.Status.OPEN
            }
        )

        # Create the fiscal year and period for the WIP batch date to prevent errors
        fy_2024, _ = FiscalYear.objects.get_or_create(
            name="Fiscal Year 2024",
            defaults={'start_date': date(2024, 1, 1), 'end_date': date(2024, 12, 31)}
        )
        FinancialPeriod.objects.get_or_create(
            name="December 2024",
            fiscal_year=fy_2024,
            defaults={
                'start_date': date(2024, 12, 1),
                'end_date': date(2024, 12, 31),
                'status': FinancialPeriod.Status.OPEN
            }
        )

        # 1. Create Operational Sub-Ledger Records for Opening Balances
        
        # --- FIX: Temporarily disconnect the post_save signal for FinishedProductReceipt ---
        post_save.disconnect(handle_fg_receipt_save, sender=FinishedProductReceipt)
        self.stdout.write("   - (Temporarily disconnected FG receipt signal to prevent duplicate JEs)")

        try:
            # a) Finished Goods Inventory
            mig_template_saline = CONTEXT['template1']
            mig_batch_saline, _ = Batch.objects.get_or_create(
                shop_order_number="MIG-SO-SALINE",
                defaults={'template': mig_template_saline, 'batch_number': "MIG-FG-1", 'creation_date': migration_date}
            )
            ob_receipt1, _ = FinishedProductReceipt.objects.get_or_create(
                individual_batch_number="OB-FP-SALINE-001",
                defaults={
                    'batch': mig_batch_saline, 'total_quantity_produced': 1000.0,
                    'total_cost': Decimal("5750.000"), 'receipt_date': migration_date,
                    'status': FinishedProductReceipt.Status.RELEASED
                }
            )

            mig_template_glucose = CONTEXT['template2']
            mig_batch_glucose, _ = Batch.objects.get_or_create(
                shop_order_number="MIG-SO-GLUCOSE",
                defaults={'template': mig_template_glucose, 'batch_number': "MIG-FG-2", 'creation_date': migration_date}
            )
            ob_receipt2, _ = FinishedProductReceipt.objects.get_or_create(
                individual_batch_number="OB-FP-GLUCOSE-001",
                defaults={
                    'batch': mig_batch_glucose, 'total_quantity_produced': 500.0,
                    'total_cost': Decimal("4200.000"), 'receipt_date': migration_date,
                    'status': FinishedProductReceipt.Status.RELEASED
                }
            )
        finally:
            # --- FIX: Reconnect the signal to ensure normal operation continues ---
            post_save.connect(handle_fg_receipt_save, sender=FinishedProductReceipt)
            self.stdout.write("   - (Reconnected FG receipt signal)")


        # b) Raw Materials Inventory
        ob_log_saline, _ = InventoryLog.objects.get_or_create(
            qc_no="MIG-RM-SALINE",
            defaults={
                'product': CONTEXT['products']['saline'], 'quantity': 500.0,
                'timestamp': migration_date, 'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("10.500"), 'release_timestamp': migration_date
            }
        )
        ob_log_pvc, _ = InventoryLog.objects.get_or_create(
            qc_no="MIG-RM-PVC",
            defaults={
                'product': CONTEXT['products']['pvc_bag'], 'quantity': 2000.0,
                'timestamp': migration_date, 'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("1.200"), 'release_timestamp': migration_date
            }
        )

        # c) MRO & Consumables Inventory
        ob_log_lube, _ = InventoryLog.objects.get_or_create(
            qc_no="MIG-MRO-LUBE",
            defaults={
                'product': CONTEXT['products']['lubricant'], 'quantity': 50.0,
                'timestamp': migration_date, 'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("25.000"), 'release_timestamp': migration_date
            }
        )
        ob_log_antivirus, _ = InventoryLog.objects.get_or_create(
            qc_no="MIG-CONSUM-AV",
            defaults={
                'product': CONTEXT['products']['antivirus'], 'quantity': 10.0,
                'timestamp': migration_date, 'status': InventoryLog.Status.RELEASED,
                'base_unit_price': Decimal("1200.000"), 'release_timestamp': migration_date
            }
        )

        # d) Work-in-Progress Inventory
        wip_batch, _ = Batch.objects.get_or_create(
            shop_order_number="WIP-SO-001",
            defaults={
                'template': mig_template_saline, 'batch_number': "MIG-WIP-1",
                'creation_date': "2024-12-31", # Before migration
                'status': Batch.Status.IN_PROGRESS
            }
        )
        wip_item1, _ = BatchItem.objects.get_or_create(batch=wip_batch, primitive_product=CONTEXT['products']['saline'], defaults={'theoretical_quantity': 50.0, 'actual_quantity': 50.0, 'cost_at_consumption': Decimal("10.500")})
        wip_item2, _ = BatchItem.objects.get_or_create(batch=wip_batch, primitive_product=CONTEXT['products']['pvc_bag'], defaults={'theoretical_quantity': 100.0, 'actual_quantity': 100.0, 'cost_at_consumption': Decimal("1.200")})
        wip_total_cost = (Decimal(str(wip_item1.actual_quantity)) * wip_item1.cost_at_consumption) + \
                         (Decimal(str(wip_item2.actual_quantity)) * wip_item2.cost_at_consumption)


        # e) Fixed Assets (already created in base_data)
        asset1 = CONTEXT['asset1']
        asset2 = CONTEXT['asset2']
        # Calculate accumulated depreciation up to migration date
        # Asset 1: 12 months (Jan 2024 - Dec 2024)
        accum_dep_asset1 = (asset1.depreciable_base / (asset1.useful_life_years * 12)) * 12
        # Asset 2: 18 months (Jul 2023 - Dec 2024)
        accum_dep_asset2 = (asset2.depreciable_base / (asset2.useful_life_years * 12)) * 18
        
        # 2. Create Financial Opening Balance Structure
        ob_entry, created = OpeningBalanceEntry.objects.get_or_create(
            name="Go-Live 2025-01-01",
            defaults={'migration_date': migration_date}
        )
        
        if not created:
            self.stdout.write(self.style.WARNING("   - Opening balance entry already exists. Skipping creation."))
            return

        # --- DEBITS ---
        total_debits = Decimal("0.0")

        # Bank Accounts
        line_bank = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020102'],
            entry_type='debit', total_amount=Decimal("250000.000")
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_bank, sub_ledger_object=CONTEXT['bank_account'], amount=Decimal("250000.000"))
        
        line_bank2 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020103'],
            entry_type='debit', total_amount=Decimal("50000.000")
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_bank2, sub_ledger_object=CONTEXT['secondary_bank_account'], amount=Decimal("50000.000"))
        total_debits += line_bank.total_amount + line_bank2.total_amount

        # Accounts Receivable
        ar_total = Decimal("95000.000")
        line_ar = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['10203'],
            entry_type='debit', total_amount=ar_total
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ar, sub_ledger_object=CONTEXT['customers']['hospital'], amount=Decimal("75000.000"))
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ar, sub_ledger_object=CONTEXT['customers']['pharmacy'], amount=Decimal("20000.000"))
        total_debits += ar_total

        # Finished Goods Inventory
        fg_total = ob_receipt1.total_cost + ob_receipt2.total_cost
        line_fg = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020206'],
            entry_type='debit', total_amount=fg_total
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_fg, sub_ledger_object=ob_receipt1, amount=ob_receipt1.total_cost)
        OpeningBalanceSubLedgerDetail.objects.create(line=line_fg, sub_ledger_object=ob_receipt2, amount=ob_receipt2.total_cost)
        total_debits += fg_total

        # Raw Materials Inventory
        rm_value_saline = Decimal(str(ob_log_saline.quantity)) * ob_log_saline.costing_unit_price
        line_rm = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020201'],
            entry_type='debit', total_amount=rm_value_saline
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_rm, sub_ledger_object=ob_log_saline.product, amount=rm_value_saline)
        total_debits += rm_value_saline

        # Packaging Inventory
        rm_value_pvc = Decimal(str(ob_log_pvc.quantity)) * ob_log_pvc.costing_unit_price
        line_pkg = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020202'],
            entry_type='debit', total_amount=rm_value_pvc
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_pkg, sub_ledger_object=ob_log_pvc.product, amount=rm_value_pvc)
        total_debits += rm_value_pvc

        # MRO Inventory
        mro_value_lube = Decimal(str(ob_log_lube.quantity)) * ob_log_lube.costing_unit_price
        line_mro = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020207'],
            entry_type='debit', total_amount=mro_value_lube
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_mro, sub_ledger_object=ob_log_lube.product, amount=mro_value_lube)
        total_debits += mro_value_lube

        # Consumables Inventory
        consumable_value_av = Decimal(str(ob_log_antivirus.quantity)) * ob_log_antivirus.costing_unit_price
        line_consumable = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020208'],
            entry_type='debit', total_amount=consumable_value_av
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_consumable, sub_ledger_object=ob_log_antivirus.product, amount=consumable_value_av)
        total_debits += consumable_value_av

        # WIP Inventory
        line_wip = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['1020205'],
            entry_type='debit', total_amount=wip_total_cost
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_wip, sub_ledger_object=wip_batch.template.final_product, amount=wip_total_cost)
        total_debits += wip_total_cost

        # Fixed Asset Cost - Asset 1
        line_fa1 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['10101'],
            entry_type='debit', total_amount=asset1.purchase_cost
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_fa1, sub_ledger_object=asset1, amount=asset1.purchase_cost)
        total_debits += asset1.purchase_cost

        # Fixed Asset Cost - Asset 2
        line_fa2 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['10102'],
            entry_type='debit', total_amount=asset2.purchase_cost
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_fa2, sub_ledger_object=asset2, amount=asset2.purchase_cost)
        total_debits += asset2.purchase_cost

        # --- CREDITS ---
        total_credits = Decimal("0.0")

        # Accumulated Depreciation - Asset 1
        line_ad1 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['2020501'],
            entry_type='credit', total_amount=accum_dep_asset1
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ad1, sub_ledger_object=asset1, amount=accum_dep_asset1)
        total_credits += accum_dep_asset1

        # Accumulated Depreciation - Asset 2
        line_ad2 = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['2020502'],
            entry_type='credit', total_amount=accum_dep_asset2
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ad2, sub_ledger_object=asset2, amount=accum_dep_asset2)
        total_credits += accum_dep_asset2

        # Accounts Payable
        ap_total = Decimal("65000.000")
        line_ap = OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=CONTEXT['accounts']['20201'],
            entry_type='credit', total_amount=ap_total
        )
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ap, sub_ledger_object=CONTEXT['suppliers']['pharma'], amount=Decimal("45000.000"))
        OpeningBalanceSubLedgerDetail.objects.create(line=line_ap, sub_ledger_object=CONTEXT['suppliers']['packaging'], amount=Decimal("20000.000"))
        total_credits += ap_total

        # Equity (Balancing Figure)
        equity_balance = total_debits - total_credits
        
        retained_earnings, _ = Account.objects.get_or_create(code='305', name='Retained Earnings', account_type=Account.AccountType.EQUITY)
        OpeningBalanceEntryLine.objects.create(
            opening_balance_entry=ob_entry, account=retained_earnings,
            entry_type='credit', total_amount=equity_balance
        )

        # 3. Post the JE
        try:
            create_je_for_opening_balance(ob_entry)
            self.stdout.write(self.style.SUCCESS("   - Successfully created and posted comprehensive opening balance journal entry."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   - Failed to post opening balance JE: {e}"))
