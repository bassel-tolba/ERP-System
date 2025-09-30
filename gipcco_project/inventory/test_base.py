# gipcco_project/inventory/test_base.py

from decimal import Decimal
from django.test import TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date

from .models import (
    Account, Product, Company, Customer, FiscalYear, FinancialPeriod,
    GeneralAccountingSettings, ProductTypeAccountingSettings,
    ShopOrderTemplate, Batch, FinishedProductReceipt,
    BankAccount, Employee, CostPool, AllocationDriver,
    # Added to fix NameErrors in test setup
    SupplierInvoice,
    CustomerInvoice,
    PaymentApplication,
    CustomerPaymentApplication,
    SupplierInvoiceItem,
    CustomerInvoiceItem,
    BankTransfer,
)

# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# HELPER FUNCTIONS & TEST SETUP
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

def create_chart_of_accounts():
    """Creates a comprehensive and structured chart of accounts for testing."""
    accounts = {}
    
    # Helper to create accounts and add them to the dictionary
    def create_account(code, name, account_type, parent_code=None):
        parent = accounts.get(parent_code) if parent_code else None
        acc = Account.objects.create(code=code, name=name, account_type=account_type, parent=parent)
        accounts[code] = acc
        return acc

    # 100 - Assets
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

    # 200 - Liabilities
    create_account('200', 'الالتزامات', Account.AccountType.LIABILITY)
    create_account('202', 'الالتزامات المتداولة', Account.AccountType.LIABILITY, '200')
    create_account('20201', 'الموردون (ذمم دائنة)', Account.AccountType.LIABILITY, '202')
    create_account('20202', 'أرصدة دائنة أخرى', Account.AccountType.LIABILITY, '202')
    create_account('2020201', 'ضريبة القيمة المضافة (المخرجات)', Account.AccountType.LIABILITY, '20202')
    create_account('2020202', 'ضريبة الخصم من المنبع', Account.AccountType.LIABILITY, '20202')

    # 400 - Revenue
    create_account('400', 'الإيرادات', Account.AccountType.REVENUE)
    create_account('401', 'إيرادات النشاط', Account.AccountType.REVENUE, '400')
    create_account('40101', 'مبيعات منتجات نهائية', Account.AccountType.REVENUE, '401')
    create_account('402', 'إيرادات أخرى', Account.AccountType.REVENUE, '400')
    create_account('40201', 'عوائد بيع خردة', Account.AccountType.REVENUE, '402')
    create_account('40202', 'مكاسب فروق المخزون', Account.AccountType.REVENUE, '402')

    # 500 - Expenses
    create_account('500', 'المصروفات', Account.AccountType.EXPENSE)
    create_account('501', 'تكلفة البضاعة المباعة (COGS)', Account.AccountType.EXPENSE, '500')
    create_account('50101', 'تكلفة مبيعات المنتجات النهائية', Account.AccountType.EXPENSE, '501')
    create_account('502', 'مصروفات التشغيل', Account.AccountType.EXPENSE, '500')
    create_account('50201', 'مصروفات صيانة', Account.AccountType.EXPENSE, '502')
    create_account('50202', 'مصروفات مستهلكات', Account.AccountType.EXPENSE, '502')
    create_account('50203', 'إيجار المصنع', Account.AccountType.EXPENSE, '502')
    create_account('503', 'خسائر فروق المخزون', Account.AccountType.EXPENSE, '500')

    return accounts

class AccountingServiceBaseTestCase(TransactionTestCase):
    """
    A base test case that sets up a scalable and reusable testing environment
    for accounting-related services.
    """
    # Using serialized_rollback=True can speed up tests that don't need to interact
    # with transaction-sensitive code (like testing third-party payment gateways).
    # For this case, we need real commits, so we don't set it.

    def setUp(self):
        """
        Set up non-modified objects used by all test methods in this class.
        This is run before every test since TransactionTestCase flushes the DB.
        """
        super().setUp()

        # 1. Create Fiscal Year and an Open Period
        self.fiscal_year = FiscalYear.objects.create(
            name="Test Fiscal Year 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31)
        )
        self.period = FinancialPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            name="September 2025",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 9, 30),
            status=FinancialPeriod.Status.OPEN
        )

        # 2. Create Chart of Accounts
        self.accounts = create_chart_of_accounts()

        # 3. Configure General Accounting Settings
        self.general_settings = GeneralAccountingSettings.objects.create(
            pk=1, # Enforce singleton behavior
            accounts_payable=self.accounts['20201'],
            accounts_receivable=self.accounts['10203'],
            vat_receivable=self.accounts['1020404'],
            vat_payable=self.accounts['2020201'],
            wip_inventory=self.accounts['1020205'],
            withholding_tax_payable=self.accounts['2020202'],
            finished_goods_inventory=self.accounts['1020206'],
            inventory_adjustment_loss_account=self.accounts['503'],
            inventory_adjustment_gain_account=self.accounts['40202'],
            employee_advances_receivable=self.accounts['1020405']
        )

        # 4. Configure Product Type Accounting Settings
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.RAW_MATERIAL,
            inventory_account=self.accounts['1020201'],
            cogs_or_expense_account=self.accounts['50101'] # Not typically used for RM, but required
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.FINAL_PRODUCT,
            inventory_account=self.accounts['1020206'],
            cogs_or_expense_account=self.accounts['50101'],
            sales_revenue_account=self.accounts['40101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.MRO,
            inventory_account=self.accounts['1020207'],
            cogs_or_expense_account=self.accounts['50201']
        )

        # 5. Create Base Operational Objects
        self.supplier = Company.objects.create(name="Test Supplier Pharma")
        self.customer = Customer.objects.create(name="Test Customer Pharmacy")
        self.raw_material = Product.objects.create(
            name="Saline Solution",
            code="RM-SALINE-001",
            product_type=Product.ProductType.RAW_MATERIAL,
            unit="Liter"
        )
        self.final_product = Product.objects.create(
            name="IV Drip Bag 500ml",
            code="FP-IVDRIP-500",
            product_type=Product.ProductType.FINAL_PRODUCT,
            unit="Bag"
        )
        self.mro_product = Product.objects.create(
            name="Machine Lubricant",
            code="MRO-LUBE-001",
            product_type=Product.ProductType.MRO,
            unit="Can"
        )

        # 6. Create a Bank Account for transactions
        self.bank_account = BankAccount.objects.create(
            name="Test Bank Account",
            gl_account=self.accounts['1020102'] # النقدية بالبنوك
        )
        self.secondary_bank_account = BankAccount.objects.create(
            name="Secondary Test Bank Account",
            gl_account=self.accounts['1020103']
        )

        # 7. Create a Test User and Employee
        self.test_user = User.objects.create_user(username='testuser', password='password')
        self.employee = Employee.objects.create(
            employee_id='E-001',
            first_name='Test',
            last_name='Employee'
        )

        # 8. Create Overhead Allocation Objects
        self.parent_pool = CostPool.objects.create(
            name="Factory Overhead", code="FOH",
            gl_account=None # Parent pools don't need a direct GL link
        )
        self.child_pool_rent = CostPool.objects.create(
            name="Factory Rent", code="FOH-RENT", parent=self.parent_pool,
            gl_account=self.accounts['50203']
        )
        self.child_pool_maintenance = CostPool.objects.create(
            name="Factory Maintenance", code="FOH-MAINT", parent=self.parent_pool,
            gl_account=self.accounts['50201']
        )
        self.machine_hours_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.MACHINE_HOURS
        )
        self.labor_hours_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.LABOR_HOURS
        )
        self.bottle_units_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.BOTTLE_UNITS
        )
        self.liters_volume_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.LITERS_VOLUME
        )

        # 9. Create a Shop Order Template for use in multiple tests
        self.test_template = ShopOrderTemplate.objects.create(
            name="Standard IV Drip Template",
            final_product=self.final_product,
            bottle_size_ml=500 
        )

        # 10. Create common receipts for adjustment/financial tests
        batch = self.get_or_create_batch_for_template(self.test_template, "SO-SETUP-01", "B-SETUP-01")
        self.receipt1 = self.get_or_create_receipt(batch, "FPB-SETUP-01", 100.0, "1000.000", "2025-09-05")
        self.receipt2 = self.get_or_create_receipt(batch, "FPB-SETUP-02", 50.0, "550.000", "2025-09-06")

    @classmethod
    def get_product_type_setting(cls, product_type):
        """Helper to get the accounting setting for a product type."""
        from .models import ProductTypeAccountingSettings
        return ProductTypeAccountingSettings.objects.get(product_type=product_type)

    @classmethod
    def get_or_create_batch_for_template(cls, template, shop_order_number="SO-ADJ-01", batch_number="B-ADJ-01"):
        """Helper to prevent creating duplicate batches in test setups."""
        batch, created = Batch.objects.get_or_create(
            shop_order_number=shop_order_number,
            defaults={
                'template': template,
                'batch_number': batch_number,
                'creation_date': timezone.make_aware(timezone.datetime(2025, 9, 4, 9, 0, 0)),
            }
        )
        return batch

    @classmethod
    def get_or_create_receipt(cls, batch, individual_batch_number, quantity, cost, date_str):
        """Helper to prevent creating duplicate receipts in test setups."""
        receipt, created = FinishedProductReceipt.objects.get_or_create(
            individual_batch_number=individual_batch_number,
            defaults={
                'batch': batch,
                'receipt_date': timezone.make_aware(timezone.datetime.strptime(date_str, "%Y-%m-%d")),
                'release_date': timezone.make_aware(timezone.datetime.strptime(date_str, "%Y-%m-%d")),
                'status': FinishedProductReceipt.Status.RELEASED,
                'total_cost': Decimal(cost),
                'total_quantity_produced': quantity
            }
        )
        return receipt
