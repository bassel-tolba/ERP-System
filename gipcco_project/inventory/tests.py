from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import ProtectedError

from .models import (
    Account, Product, Company, Customer, FiscalYear, FinancialPeriod,
    GeneralAccountingSettings, ProductTypeAccountingSettings, InventoryLog,
    JournalEntry, JournalEntryLine, ShopOrderTemplate, Batch, BatchItem,
    FinishedProductReceipt, SalesOrder, SalesOrderItem, FinishedProductDispatch,
    BankAccount, Payment, InventoryCount, InventoryAdjustment, Employee,
    InventoryConsumption, ProductionReturn, CostPool, AllocationDriver,
    ExpenseLog, OverheadAllocationRun, PurchaseOrder, PurchaseOrderItem,
    OpeningBalance, EmployeeAdvance, EmployeeAdvanceSettlement
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

class AccountingServiceBaseTestCase(TestCase):
    """
    A base test case that sets up a scalable and reusable testing environment
    for accounting-related services.
    """
    @classmethod
    def setUpTestData(cls):
        """
        Set up non-modified objects used by all test methods in this class.
        This is run once for the entire test case.
        """
        super().setUpTestData()

        # 1. Create Fiscal Year and an Open Period
        cls.fiscal_year = FiscalYear.objects.create(
            name="Test Fiscal Year 2025",
            start_date="2025-01-01",
            end_date="2025-12-31"
        )
        cls.period = FinancialPeriod.objects.create(
            fiscal_year=cls.fiscal_year,
            name="September 2025",
            start_date="2025-09-01",
            end_date="2025-09-30",
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

        # 4. Configure Product Type Accounting Settings
        ProductTypeAccountingSettings.objects.create(
            product_type=Product.ProductType.RAW_MATERIAL,
            inventory_account=cls.accounts['1020201'],
            cogs_or_expense_account=cls.accounts['50101'] # Not typically used for RM, but required
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

        # 6. Create a Bank Account for transactions
        cls.bank_account = BankAccount.objects.create(
            name="Test Bank Account",
            gl_account=cls.accounts['1020102'] # النقدية بالبنوك
        )
        cls.secondary_bank_account = BankAccount.objects.create(
            name="Secondary Test Bank Account",
            gl_account=cls.accounts['1020103']
        )

        # 7. Create a Test User and Employee
        cls.test_user = User.objects.create_user(username='testuser', password='password')
        cls.employee = Employee.objects.create(
            employee_id='E-001',
            first_name='Test',
            last_name='Employee'
        )

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


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# VIEW TESTS
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

class TestViews(AccountingServiceBaseTestCase):
    """
    Test suite for the application's views.
    """
    @classmethod
    def setUpTestData(cls):
        """Set up data for the entire test class."""
        super().setUpTestData()
        # The user is already created in the parent class's setUpTestData.
        # We just need to create a client and log in once.
        cls.client = Client()
        cls.client.login(username='testuser', password='password')

    def setUp(self):
        """This method will run before each test."""
        pass # No per-test setup needed now

    def test_dashboard_index_view_get(self):
        """
        Verify that the main dashboard page loads correctly via a GET request.
        """
        response = self.client.get(reverse('inventory:index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/dashboard.html')
        self.assertIn('active_page', response.context)
        self.assertEqual(response.context['active_page'], 'index')

    def test_create_company_view_post(self):
        """
        Verify that creating a new company via a POST request succeeds and redirects.
        """
        company_count_before = Company.objects.count()
        response = self.client.post(reverse('inventory:companies'), {'name': 'New Test Company'})
        
        self.assertEqual(response.status_code, 302) # Should redirect
        self.assertRedirects(response, reverse('inventory:companies'))
        self.assertEqual(Company.objects.count(), company_count_before + 1)
        self.assertTrue(Company.objects.filter(name='New Test Company').exists())

    def test_create_product_view_post(self):
        """
        Verify that creating a new product via a POST request succeeds and redirects.
        """
        product_count_before = Product.objects.count()
        product_data = {
            'name': 'Test Product',
            'code': 'TP-001',
            'product_type': Product.ProductType.RAW_MATERIAL,
            'unit': 'KG'
        }
        response = self.client.post(reverse('inventory:products'), product_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:products'))
        self.assertEqual(Product.objects.count(), product_count_before + 1)
        new_product = Product.objects.get(code='TP-001')
        self.assertEqual(new_product.name, 'Test Product')

    def test_release_from_quarantine_view_post(self):
        """
        Verify that releasing an item from quarantine via POST request works.
        """
        # Arrange: Create a quarantined inventory log
        log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=50.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.QUARANTINED,
            base_unit_price=Decimal("10.000")
        )
        
        release_data = {
            'qc_no': 'QC-RELEASE-001',
            'release_date': timezone.now().strftime('%Y-%m-%d')
        }

        # Act
        response = self.client.post(reverse('inventory:release_material_from_quarantine', kwargs={'pk': log.pk}), release_data)

        # Assert
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:quarantine_list'))
        
        log.refresh_from_db()
        self.assertEqual(log.status, InventoryLog.Status.RELEASED)
        self.assertEqual(log.qc_no, 'QC-RELEASE-001')
        self.assertIsNotNone(log.release_timestamp)

    def test_api_get_sellable_stock(self):
        """
        Verify that the sellable stock API returns correct data.
        """
        # Arrange: Create a finished product receipt that is released and has stock.
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-API-001",
            batch_number="B-API-001",
            creation_date=timezone.now(),
        )
        FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-API-001",
            receipt_date=timezone.now().date(),
            total_cost=Decimal("1000.000"),
            total_quantity_produced=100.0,
            status=FinishedProductReceipt.Status.RELEASED
        )

        # Act
        response = self.client.get(reverse('inventory:api_get_sellable_stock'))

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['product_name'], self.final_product.name)
        self.assertEqual(data[0]['batch_number'], 'FPB-API-001')
        self.assertEqual(data[0]['available_qty'], 100.0)

    def test_create_batch_view_post(self):
        """
        Verify that creating a new batch via POST request works correctly.
        """
        # Arrange: Ensure there is stock for the raw material in the template
        log = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=100.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000")
        )

        batch_data = {
            'template_id': self.test_template.id,
            'shop_order_number': 'SO-VIEW-TEST-01',
            'batch_number_from': 'B-VIEW-TEST-01',
            'batch_number_to': '',
            'creation_date': timezone.now().strftime('%Y-%m-%d'),
            'primitive_product_id': [self.raw_material.id],
            'theoretical_quantity': [10.0],
            'actual_quantity': [10.0],
            'source_log_id': [log.id]
        }
        
        # Act
        response = self.client.post(reverse('inventory:create_batch'), batch_data)
        
        # Assert
        self.assertEqual(response.status_code, 302) # Should redirect to view_batch
        self.assertTrue(Batch.objects.filter(shop_order_number='SO-VIEW-TEST-01').exists())
        new_batch = Batch.objects.get(shop_order_number='SO-VIEW-TEST-01')
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': new_batch.pk}))
        self.assertEqual(new_batch.items.count(), 1)
        self.assertEqual(new_batch.items.first().actual_quantity, 10.0)

    def test_create_purchase_order_view_post(self):
        """
        Verify that creating a new purchase order via POST request works.
        """
        po_count_before = PurchaseOrder.objects.count()
        po_data = {
            'po_number': 'PO-VIEW-TEST-01',
            'supplier_id': self.supplier.id,
            'order_date': timezone.now().strftime('%Y-%m-%d'),
            'product_id': [self.raw_material.id],
            'quantity': [100],
            'base_price_per_unit': [15.0],
            'vat_rate': [14],
            'withholding_tax_rate': [1]
        }

        response = self.client.post(reverse('inventory:create_purchase_order'), po_data)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:purchase_orders'))
        self.assertEqual(PurchaseOrder.objects.count(), po_count_before + 1)
        new_po = PurchaseOrder.objects.get(po_number='PO-VIEW-TEST-01')
        self.assertEqual(new_po.items.count(), 1)
        self.assertEqual(new_po.items.first().quantity_ordered, 100)

    def test_create_sales_order_view_post(self):
        """
        Verify that creating a new sales order via a POST request works.
        """
        # Arrange: Create a finished product receipt to sell
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-SALE-VIEW-01",
            batch_number="B-SALE-VIEW-01",
            creation_date=timezone.now(),
        )
        receipt = FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-SALE-VIEW-01",
            receipt_date=timezone.now().date(),
            total_cost=Decimal("5000.000"),
            total_quantity_produced=100.0,
            status=FinishedProductReceipt.Status.RELEASED
        )

        so_count_before = SalesOrder.objects.count()
        so_data = {
            'customer_id': self.customer.id,
            'order_date': timezone.now().strftime('%Y-%m-%d'),
            'so_number': 'SO-VIEW-SALE-01',
            'receipt_id': [receipt.id],
            'quantity': [20],
            'base_price_per_unit': [150.0],
            'vat_rate': [14]
        }

        response = self.client.post(reverse('inventory:create_sales_order'), so_data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(SalesOrder.objects.filter(so_number='SO-VIEW-SALE-01').exists())
        new_so = SalesOrder.objects.get(so_number='SO-VIEW-SALE-01')
        self.assertRedirects(response, reverse('inventory:view_sales_order', kwargs={'pk': new_so.pk}))
        self.assertEqual(SalesOrder.objects.count(), so_count_before + 1)
        self.assertEqual(new_so.items.count(), 1)
        self.assertEqual(new_so.items.first().quantity_ordered, 20)

    def test_api_get_po_items(self):
        """
        Verify that the API to get PO items returns correct data.
        """
        # Arrange
        po = PurchaseOrder.objects.create(
            supplier=self.supplier,
            order_date=timezone.now().date(),
            po_number="PO-API-TEST-01"
        )
        po_item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=self.raw_material,
            quantity_ordered=100.0,
            base_price_per_unit=Decimal("10.000")
        )
        # Receive some of it
        InventoryLog.objects.create(
            product=self.raw_material,
            po_item=po_item,
            quantity=30.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.now(), # FIX: Add release timestamp
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000")
        )

        # Act
        response = self.client.get(reverse('inventory:api_get_po_items', kwargs={'po_id': po.id}))

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['product_id'], self.raw_material.id)
        self.assertAlmostEqual(data[0]['quantity_remaining'], 70.0)

class TestValidationAndProtection(AccountingServiceBaseTestCase):
    """
    Tests for model-level validation (clean methods) and deletion protection.
    """
    def test_consumption_of_non_mro_raises_error(self):
        """
        Verify InventoryConsumption.clean() prevents consumption of non-MRO/Consumable items.
        """
        with self.assertRaises(ValidationError) as context:
            # Try to consume a Raw Material, which should not be allowed
            consumption = InventoryConsumption(
                product=self.raw_material,
                quantity_consumed=1.0,
                consumption_date=timezone.now(),
                department=InventoryConsumption.Department.ENGINEERING
            )
            consumption.clean()
        self.assertIn('product', context.exception.message_dict)

    def test_bank_transfer_to_same_account_raises_error(self):
        """
        Verify BankTransfer.clean() prevents transferring to the same account.
        """
        from .models import BankTransfer
        with self.assertRaises(ValidationError) as context:
            transfer = BankTransfer(
                source_account=self.bank_account,
                destination_account=self.bank_account, # Same account
                amount=Decimal("100.00"),
                transfer_date=timezone.now().date()
            )
            transfer.clean()
        self.assertIn('Source and destination accounts cannot be the same', str(context.exception))

    def test_deleting_supplier_with_po_raises_protected_error(self):
        """
        Verify that deleting a Company (supplier) with a linked PurchaseOrder is prevented.
        """
        from django.db.models import ProtectedError
        # 1. Arrange: Create a PO linked to the supplier
        PurchaseOrder.objects.create(
            po_number="PO-PROTECT-01",
            supplier=self.supplier,
            order_date=timezone.now().date()
        )
        
        # 2. Act & Assert: Attempting to delete the supplier should raise ProtectedError
        with self.assertRaises(ProtectedError):
            self.supplier.delete()
