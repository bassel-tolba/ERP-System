# gipcco_project/inventory/management/commands/setup_test_data.py

import os
import shutil
from datetime import date, timedelta
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
    InventoryLog, PurchaseOrder, PurchaseOrderItem, BatchItem,
    SalesOrder, SalesOrderItem, FinishedProductDispatch,
    SupplierInvoice, SupplierInvoiceItem, Payment, PaymentApplication,
    CustomerInvoice, CustomerInvoiceItem, CustomerPaymentApplication,
    BankTransfer, FixedAsset, DepreciationLog, InventoryConsumption,
    InventoryCount, InventoryAdjustment, TemplateItem, ExpenseRequest, EmployeeAdvance,
    AccruedExpense, AccrualLog
)
from inventory.services.adjusting_entries_service import run_monthly_accruals

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
    create_account('20205', 'مجمعات الإهلاك', Account.AccountType.LIABILITY, '202')
    create_account('2020501', 'مجمع إهلاك - آلات ومعدات', Account.AccountType.LIABILITY, '20205')
    create_account('2020502', 'مجمع إهلاك - أثاث وتركيبات', Account.AccountType.LIABILITY, '20205')

    # Revenue
    create_account('400', 'الإيرادات', Account.AccountType.REVENUE)
    create_account('401', 'إيرادات النشاط', Account.AccountType.REVENUE, '400')
    create_account('40101', 'مبيعات منتجات نهائية', Account.AccountType.REVENUE, '401')
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
                'end_date': date(2025, 10, 30),
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
            accrued_expenses_account=accounts['2020203']
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
        CONTEXT['suppliers'] = {'pharma': supplier1, 'packaging': supplier2, 'mro': supplier3, 'consulting': supplier4}

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
        batch, _ = Batch.objects.get_or_create(
            shop_order_number="SO-DEMO-001",
            defaults={
                'template': CONTEXT['template1'],
                'batch_number': "B-DEMO-001",
                'creation_date': timezone.make_aware(timezone.datetime(2025, 9, 10, 9, 0, 0)),
            }
        )
        BatchItem.objects.create(
            batch=batch,
            primitive_product=CONTEXT['products']['saline'],
            theoretical_quantity=80.0,
            actual_quantity=82.5,
            source_log=log,
            cost_at_consumption=Decimal("10.500")
        )
        batch.save() # Trigger signal
        
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
        FinishedProductDispatch.objects.create(
            sales_order_item=so_item,
            quantity=50.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 16, 14, 0, 0)),
            cost_at_dispatch=Decimal("288.750") # 866.250 / 150 * 50
        )
        self.stdout.write("   - Created a sales order and dispatched 50 IV Bags.")

        # Invoicing and Payments
        sup_inv, _ = SupplierInvoice.objects.get_or_create(
            invoice_number="GS-INV-001",
            defaults={
                'supplier': CONTEXT['suppliers']['pharma'],
                'invoice_date': date(2025, 9, 6),
                'due_date': date(2025, 10, 6),
                'total_amount': Decimal("2373.00") # (200 * 10.5) + 294 - 21
            }
        )
        SupplierInvoiceItem.objects.create(invoice=sup_inv, receipt=log, amount=log.total_cost)
        
        payment_out = Payment.objects.create(
            payment_date=date(2025, 9, 20),
            amount=Decimal("2373.000"),
            bank_account=CONTEXT['bank_account'],
            payment_type=Payment.PaymentType.PAYMENT_OUT,
            description="Payment for PO-DEMO-001",
            supplier=CONTEXT['suppliers']['pharma']
        )
        PaymentApplication.objects.create(payment=payment_out, invoice=sup_inv, amount_applied=payment_out.amount)
        self.stdout.write("   - Created and paid a supplier invoice.")

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
                'creation_date': "2024-12-31" # Before migration
            }
        )
        wip_item1 = BatchItem.objects.create(batch=wip_batch, primitive_product=CONTEXT['products']['saline'], theoretical_quantity=50.0, actual_quantity=50.0, cost_at_consumption=Decimal("10.500"))
        wip_item2 = BatchItem.objects.create(batch=wip_batch, primitive_product=CONTEXT['products']['pvc_bag'], theoretical_quantity=100.0, actual_quantity=100.0, cost_at_consumption=Decimal("1.200"))
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
