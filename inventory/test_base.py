# gipcco_project/inventory/test_base.py

from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group, Permission
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
    FixedAsset,
    InventoryLog,
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
    create_account('1020406', 'تسوية مرتجعات المبيعات', Account.AccountType.ASSET, '10204') # Clearing Account
    create_account('10205', 'مصروفات مدفوعة مقدماً', Account.AccountType.ASSET, '102') # Prepaid Expenses
    create_account('101', 'الأصول الثابتة', Account.AccountType.ASSET, '100')
    create_account('10101', 'آلات ومعدات', Account.AccountType.ASSET, '101')
    create_account('10102', 'أثاث وتركيبات', Account.AccountType.ASSET, '101')

    # 200 - Liabilities
    create_account('200', 'الالتزامات', Account.AccountType.LIABILITY)
    create_account('202', 'الالتزامات المتداولة', Account.AccountType.LIABILITY, '200')
    create_account('20201', 'الموردون (ذمم دائنة)', Account.AccountType.LIABILITY, '202')
    create_account('20202', 'أرصدة دائنة أخرى', Account.AccountType.LIABILITY, '202')
    create_account('2020201', 'ضريبة القيمة المضافة (المخرجات)', Account.AccountType.LIABILITY, '20202')
    create_account('2020202', 'ضريبة الخصم من المنبع', Account.AccountType.LIABILITY, '20202')
    create_account('20205', 'مجمعات الإهلاك', Account.AccountType.LIABILITY, '202')
    create_account('2020501', 'مجمع إهلاك - آلات ومعدات', Account.AccountType.LIABILITY, '20205')
    create_account('2020502', 'مجمع إهلاك - أثاث وتركيبات', Account.AccountType.LIABILITY, '20205')
    create_account('20203', 'إيرادات مؤجلة (عملاء)', Account.AccountType.LIABILITY, '202') # Deferred Revenue / Customer Deposits
    create_account('20204', 'مصروفات مستحقة', Account.AccountType.LIABILITY, '202') # Accrued Expenses

    # 400 - Revenue
    create_account('400', 'الإيرادات', Account.AccountType.REVENUE)
    create_account('401', 'إيرادات النشاط', Account.AccountType.REVENUE, '400')
    create_account('40101', 'مبيعات منتجات نهائية', Account.AccountType.REVENUE, '401')
    create_account('402', 'إيرادات أخرى', Account.AccountType.REVENUE, '400')
    create_account('40201', 'عوائد بيع خردة', Account.AccountType.REVENUE, '402')
    create_account('40202', 'مكاسب فروق المخزون', Account.AccountType.REVENUE, '402')
    create_account('40102', 'مردودات ومسموحات المبيعات', Account.AccountType.REVENUE, '401') # Sales Returns & Allowances

    # 500 - Expenses
    create_account('500', 'المصروفات', Account.AccountType.EXPENSE)
    create_account('501', 'تكلفة البضاعة المباعة (COGS)', Account.AccountType.EXPENSE, '500')
    create_account('50101', 'تكلفة مبيعات المنتجات النهائية', Account.AccountType.EXPENSE, '501')
    create_account('502', 'مصروفات التشغيل', Account.AccountType.EXPENSE, '500')
    create_account('50201', 'مصروفات صيانة', Account.AccountType.EXPENSE, '502')
    create_account('50202', 'مصروفات مستهلكات', Account.AccountType.EXPENSE, '502')
    create_account('50203', 'إيجار المصنع', Account.AccountType.EXPENSE, '502')
    create_account('503', 'خسائر فروق المخزون', Account.AccountType.EXPENSE, '500')
    create_account('50205', 'مصروفات الإهلاك', Account.AccountType.EXPENSE, '502')
    create_account('5020501', 'مصروف إهلاك - آلات ومعدات', Account.AccountType.EXPENSE, '50205')
    create_account('5020502', 'مصروف إهلاك - أثاث وتركيبات', Account.AccountType.EXPENSE, '50205')
    create_account('50206', 'مصروف بضاعة تالفة', Account.AccountType.EXPENSE, '502') # Damaged Goods Expense
    create_account('50207', 'مصروف تأمين', Account.AccountType.EXPENSE, '502') # Insurance Expense
    create_account('50208', 'مصروف كهرباء ومياه', Account.AccountType.EXPENSE, '502') # Utilities Expense
    # --- NEW PURCHASING ACCOUNTS ---
    create_account('20206', 'بضاعة مستلمة غير مفوترة (GRNI)', Account.AccountType.LIABILITY, '202')
    create_account('504', 'فروقات أسعار الشراء (PPV)', Account.AccountType.EXPENSE, '500')
    create_account('1020407', 'تسوية تكاليف شحن', Account.AccountType.ASSET, '10204') # Landed Costs Clearing
    create_account('20207', 'تسوية مرتجعات موردين', Account.AccountType.LIABILITY, '202') # Purchase Returns Clearing
    # --- NEW LANDED COST (NETSUITE) ACCOUNTS ---
    create_account('20208', 'تكاليف شحن مستحقة', Account.AccountType.LIABILITY, '202') # Accrued Landed Costs
    create_account('505', 'فروقات تكاليف الشحن', Account.AccountType.EXPENSE, '500') # Landed Cost Variance

    # --- Configure Control Accounts ---
    from django.contrib.contenttypes.models import ContentType
    from .models import Customer, Company, Product, FinishedProductReceipt, FixedAsset, BankAccount, Employee

    def set_control(code, model_class):
        acc = accounts.get(code)
        if acc:
            acc.is_control_account = True
            acc.sub_ledger_model = ContentType.objects.get_for_model(model_class)
            acc.save()

    set_control('10203', Customer)
    set_control('20201', Company)
    set_control('1020201', Product)
    set_control('1020206', FinishedProductReceipt)
    set_control('1020207', Product)
    # Add other control accounts as needed for tests
    set_control('1020102', BankAccount)
    set_control('1020103', BankAccount)
    set_control('1020405', Employee)
    set_control('10101', FixedAsset)
    set_control('10102', FixedAsset)

    return accounts

class AccountingServiceBaseTestCase(TestCase):
    """
    A base test case that sets up a scalable and reusable testing environment
    for accounting-related services.
    """
    # Using TestCase with setUpTestData is much more efficient than TransactionTestCase
    # as it creates the common data only once per test class run.

    @classmethod
    def setUpTestData(cls):
        """
        Set up non-modified objects used by all test methods in this class.
        This is run once per class, making it much faster.
        """
        # 1. Create Fiscal Year and an Open Period
        cls.fiscal_year = FiscalYear.objects.create(
            name="Test Fiscal Year 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31)
        )
        cls.period = FinancialPeriod.objects.create(
            fiscal_year=cls.fiscal_year,
            name="September 2025",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 9, 30),
            status=FinancialPeriod.Status.OPEN
        )
        # --- FIX: Add more periods to prevent test failures on different dates ---
        FinancialPeriod.objects.create(
            fiscal_year=cls.fiscal_year,
            name="October 2025",
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
            status=FinancialPeriod.Status.OPEN
        )
        FinancialPeriod.objects.create(
            fiscal_year=cls.fiscal_year,
            name="November 2025",
            start_date=date(2025, 11, 1),
            end_date=date(2025, 11, 30),
            status=FinancialPeriod.Status.OPEN
        )
        FinancialPeriod.objects.create(
            fiscal_year=cls.fiscal_year,
            name="January 2025",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
            status=FinancialPeriod.Status.OPEN
        )


        # 2. Create Chart of Accounts
        cls.accounts = create_chart_of_accounts()

        # 3. Configure General Accounting Settings
        cls.general_settings = GeneralAccountingSettings.objects.create(
            pk=1, # Enforce singleton behavior
            accounts_payable=cls.accounts['20201'],
            accounts_receivable=cls.accounts['10203'],
            vat_receivable=cls.accounts['1020404'],
            vat_payable=cls.accounts['2020201'],
            wip_inventory=cls.accounts['1020205'],
            withholding_tax_payable=cls.accounts['2020202'],
            finished_goods_inventory=cls.accounts['1020206'],
            inventory_adjustment_loss_account=cls.accounts['503'],
            inventory_adjustment_gain_account=cls.accounts['40202'],
            employee_advances_receivable=cls.accounts['1020405']
        )
        cls.general_settings.customer_deposits_account = cls.accounts['20203']
        cls.general_settings.sales_returns_account = cls.accounts['40102']
        cls.general_settings.sales_returns_clearing_account = cls.accounts['1020406']
        cls.general_settings.prepaid_expenses_account = cls.accounts['10205']
        cls.general_settings.accrued_expenses_account = cls.accounts['20204']
        cls.general_settings.damaged_goods_expense_account = cls.accounts['50206']
        cls.general_settings.goods_received_not_invoiced_account = cls.accounts['20206']
        cls.general_settings.purchase_price_variance_account = cls.accounts['504']
        cls.general_settings.landed_costs_clearing_account = cls.accounts['1020407']
        cls.general_settings.purchase_returns_clearing_account = cls.accounts['20207']
        # --- NEW LANDED COST (NETSUITE) ACCOUNTS ---
        cls.general_settings.accrued_landed_costs_account = cls.accounts['20208']
        cls.general_settings.landed_cost_variance_account = cls.accounts['505']
        cls.general_settings.save()

        # 4. Configure Product Type Accounting Settings
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.RAW_MATERIAL,
            inventory_account=cls.accounts['1020201'],
            cogs_or_expense_account=cls.accounts['50101'] # Not typically used for RM, but required
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.PACKAGING,
            inventory_account=cls.accounts['1020202'],
            cogs_or_expense_account=cls.accounts['50101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.FINAL_PRODUCT,
            inventory_account=cls.accounts['1020206'],
            cogs_or_expense_account=cls.accounts['50101'],
            sales_revenue_account=cls.accounts['40101']
        )
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.MRO,
            inventory_account=cls.accounts['1020207'],
            cogs_or_expense_account=cls.accounts['50201']
        )

        # 5. Create Base Operational Objects
        cls.supplier = Company.objects.create(name="Test Supplier Pharma")
        cls.customer = Customer.objects.create(name="Test Customer Pharmacy")
        cls.raw_material = Product.objects.create(
            name="Saline Solution",
            code="RM-SALINE-001",
            product_type=Product.ProductType.RAW_MATERIAL,
            unit="Liter"
        )
        cls.packaging_material = Product.objects.create(
            name="PVC Bag 500ml",
            code="PKG-BAG-500",
            product_type=Product.ProductType.PACKAGING,
            unit="Unit"
        )
        cls.final_product = Product.objects.create(
            name="IV Drip Bag 500ml",
            code="FP-IVDRIP-500",
            product_type=Product.ProductType.FINAL_PRODUCT,
            unit="Bag"
        )
        cls.mro_product = Product.objects.create(
            name="Machine Lubricant",
            code="MRO-LUBE-001",
            product_type=Product.ProductType.MRO,
            unit="Can"
        )
        cls.amortizable_product = Product.objects.create(
            name="Amortizable Filter",
            code="MRO-FILT-001A",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=True
        )

        # 6. Create a Bank Account for transactions
        cls.bank_account = BankAccount.objects.create(
            name="Test Bank Account",
            gl_account=cls.accounts['1020102'] # النقدية بالبنوك
        )
        cls.secondary_bank_account = BankAccount.objects.create(
            name="Secondary Test Bank Account",
            gl_account=cls.accounts['1020103']
        )

        # 7. Create a Test User
        cls.test_user = User.objects.create_user(username='testuser', password='password')
        cls.user = cls.test_user

        # 8. Create Overhead Allocation Objects
        cls.parent_pool = CostPool.objects.create(
            name="Factory Overhead", code="FOH",
            gl_account=None # Parent pools don't need a direct GL link
        )
        cls.child_pool_rent = CostPool.objects.create(
            name="Factory Rent", code="FOH-RENT", parent=cls.parent_pool,
            gl_account=cls.accounts['50203']
        )
        cls.child_pool_maintenance = CostPool.objects.create(
            name="Factory Maintenance", code="FOH-MAINT", parent=cls.parent_pool,
            gl_account=cls.accounts['50201']
        )
        cls.machine_hours_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.MACHINE_HOURS
        )
        cls.labor_hours_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.LABOR_HOURS
        )
        cls.bottle_units_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.BOTTLE_UNITS
        )
        cls.liters_volume_driver = AllocationDriver.objects.create(
            name=AllocationDriver.DriverChoices.LITERS_VOLUME
        )

        # 9. Create a Shop Order Template for use in multiple tests
        cls.test_template = ShopOrderTemplate.objects.create(
            name="Standard IV Drip Template",
            final_product=cls.final_product,
            bottle_size_ml=500 
        )

        # 10. Create common receipts for adjustment/financial tests
        batch = cls.get_or_create_batch_for_template(cls.test_template, "SO-SETUP-01", "B-SETUP-01")
        cls.receipt1 = cls.get_or_create_receipt(batch, "FPB-SETUP-01", 100.0, "1000.000", "2025-09-05")
        cls.receipt2 = cls.get_or_create_receipt(batch, "FPB-SETUP-02", 50.0, "550.000", "2025-09-06")

        # 11. Create Fixed Assets
        cls.asset1 = FixedAsset.objects.create(
            asset_tag="MACHINE-TEST-001",
            name="Test Production Filling Machine",
            gl_account=cls.accounts['10101'],
            depreciation_expense_account=cls.accounts['5020501'],
            accumulated_depreciation_account=cls.accounts['2020501'],
            purchase_date="2024-01-01",
            purchase_cost=Decimal("120000.000"),
            depreciation_start_date="2024-01-01",
            useful_life_years=10,
            salvage_value=Decimal("0.000")
        )
        cls.asset2 = FixedAsset.objects.create(
            asset_tag="FURN-TEST-001",
            name="Test Office Furniture Set",
            gl_account=cls.accounts['10102'],
            depreciation_expense_account=cls.accounts['5020502'],
            accumulated_depreciation_account=cls.accounts['2020502'],
            purchase_date="2023-07-01",
            purchase_cost=Decimal("30000.000"),
            depreciation_start_date="2023-07-01",
            useful_life_years=5,
            salvage_value=Decimal("0.000")
        )

        # --- NEW: Create Users, Groups, and Permissions for testing ---
        # 1. Create Groups
        cls.planner_group, _ = Group.objects.get_or_create(name="Production Planner")
        cls.manager_group, _ = Group.objects.get_or_create(name="Production Manager")

        # 2. Get all relevant permissions
        batch_permissions = Permission.objects.filter(content_type__app_label='inventory', content_type__model='batch')
        return_permissions = Permission.objects.filter(content_type__app_label='inventory', content_type__model='productionreturn')

        # 3. Assign permissions to groups
        planner_perms_codenames = [
            'add_batch', 'change_batch', 'view_batch', 'can_submit_batch', 'add_productionreturn'
        ]
        manager_perms_codenames = [
            'add_batch', 'change_batch', 'view_batch', 'delete_batch',
            'can_approve_batch', 'can_start_production', 'can_cancel_batch', 'add_productionreturn'
        ]
        
        planner_perms = batch_permissions.filter(codename__in=planner_perms_codenames)
        cls.planner_group.permissions.set(planner_perms)
        cls.planner_group.permissions.add(*return_permissions.filter(codename__in=planner_perms_codenames))

        manager_perms = batch_permissions.filter(codename__in=manager_perms_codenames)
        cls.manager_group.permissions.set(manager_perms)
        cls.manager_group.permissions.add(*return_permissions.filter(codename__in=manager_perms_codenames))

        # 4. Create users and assign to groups
        cls.planner_user = User.objects.create_user(username='planner', password='password')
        cls.planner_user.groups.add(cls.planner_group)

        cls.manager_user = User.objects.create_user(username='manager', password='password')
        cls.manager_user.groups.add(cls.manager_group)

        # A user with no special permissions
        cls.basic_user = User.objects.create_user(username='basic', password='password')


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

    @classmethod
    def create_company(cls, name):
        """Helper to create a company."""
        company, _ = Company.objects.get_or_create(name=name)
        return company

    @classmethod
    def create_product(cls, code, name, product_type=Product.ProductType.RAW_MATERIAL):
        """Helper to create a product."""
        product, _ = Product.objects.get_or_create(
            code=code,
            defaults={'name': name, 'product_type': product_type, 'unit': 'Unit'}
        )
        return product

    def get_je_for_object(self, obj, expect_one=True):
        """
        Helper to retrieve JournalEntry/Entries linked to a specific object.
        - If expect_one is True (default), it uses .get() and expects a single JE.
        - If expect_one is False, it returns a queryset.
        """
        from django.contrib.contenttypes.models import ContentType
        from .models import JournalEntry
        
        content_type = ContentType.objects.get_for_model(obj.__class__)
        qs = JournalEntry.objects.filter(content_type=content_type, object_id=obj.id)
        if expect_one:
            return qs.get()
        return qs

    @classmethod
    def create_inventory_log(cls, company, product, quantity, base_unit_price, po_item=None, log_date=None):
        """Helper to create a released inventory log for testing."""
        log_time = log_date if log_date else timezone.now()

        vat_amount = Decimal('0.000')
        wht_amount = Decimal('0.000')
        
        if po_item:
            base_value = Decimal(str(base_unit_price)) * Decimal(str(quantity))
            vat_amount = base_value * po_item.vat_rate
            wht_amount = base_value * po_item.withholding_tax_rate

        log = InventoryLog.objects.create(
            company=company,
            product=product,
            quantity=quantity,
            base_unit_price=Decimal(str(base_unit_price)),
            po_item=po_item,
            timestamp=log_time,
            release_timestamp=log_time,
            status=InventoryLog.Status.RELEASED,
            vat_amount=vat_amount,
            withholding_tax_amount=wht_amount
        )
        # The pre_save signal should calculate costing_unit_price
        log.refresh_from_db()
        return log

    def assertJournalEntry(self, je, expected_lines, source_object=None):
        """
        Asserts a JournalEntry has the expected lines and properties. This provides
        clear, debuggable output if an assertion fails.

        :param je: The JournalEntry instance to check.
        :param expected_lines: A list of dicts, each representing a line.
            e.g., [{'account': self.accounts['...'], 'debit': Decimal('100'), 'sub_ledger': obj},
                   {'account': self.accounts['...'], 'credit': Decimal('100')}]
        :param source_object: The expected source object for the JE.
        """
        from .models import JournalEntryLine

        self.assertIsNotNone(je, "The Journal Entry to be checked should not be None.")

        if source_object:
            self.assertEqual(je.source_object, source_object, f"JE source object mismatch. Expected {source_object}, got {je.source_object}.")

        actual_lines = list(je.lines.all())
        self.assertEqual(
            len(actual_lines), len(expected_lines),
            f"Expected {len(expected_lines)} lines, but found {len(actual_lines)}."
        )

        # This check is critical for financial integrity
        je.validate_balance()

        # Match each expected line against the actual lines
        matched_actual_lines = []
        for expected in expected_lines:
            found_match = False
            for actual in actual_lines:
                if actual in matched_actual_lines:
                    continue

                entry_type = JournalEntryLine.EntryType.DEBIT if 'debit' in expected else JournalEntryLine.EntryType.CREDIT
                expected_amount = expected.get('debit') or expected.get('credit')

                if (actual.account == expected['account'] and
                    actual.entry_type == entry_type and
                    actual.amount == expected_amount and
                    actual.sub_ledger_object == expected.get('sub_ledger')):
                    matched_actual_lines.append(actual)
                    found_match = True
                    break
            
            if not found_match:
                expected_str = f"  - Account: {expected['account'].code}, "
                if 'debit' in expected: expected_str += f"Debit: {expected['debit']}"
                if 'credit' in expected: expected_str += f"Credit: {expected['credit']}"
                if 'sub_ledger' in expected: expected_str += f", Sub-Ledger: {expected.get('sub_ledger')}"
                
                actuals_str = "\n".join([
                    f"  - Account: {l.account.code}, Type: {l.entry_type}, Amount: {l.amount}, Sub-Ledger: {l.sub_ledger_object}"
                    for l in je.lines.all()
                ])
                self.fail(f"Could not find matching JE line for:\n[Expected]\n{expected_str}\n\n[Actual Lines Found]\n{actuals_str}")
