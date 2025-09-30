from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db.models import ProtectedError

# Import the base test case from the new central location
from .test_base import AccountingServiceBaseTestCase

from .models import (
    Product, Company, InventoryLog, Batch, FinishedProductReceipt,
    PurchaseOrder, PurchaseOrderItem, SalesOrder, InventoryConsumption
)

# Import tests from other modules to be discovered by the test runner
from .tests_accounting import *
from .tests_financials import *
from .tests_adjustments import *
from .tests_sub_ledger import *
from .tests_banking import *
from .tests_costing import *
from .tests_fixed_assets import *
from .tests_hr import *
from .tests_period_closing import *


# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=
# VIEW TESTS
# =-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=

class TestViews(AccountingServiceBaseTestCase):
    """
    Test suite for the application's views.
    """
    def setUp(self):
        """This method will run before each test."""
        super().setUp()
        # The user is already created in the parent class's setUp.
        # We just need to create a client and log in for each test.
        self.client = Client()
        self.client.login(username='testuser', password='password')

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
        # Arrange: Get initial count of sellable stock
        initial_response = self.client.get(reverse('inventory:api_get_sell_stock'))
        initial_data = initial_response.json()
        initial_count = len(initial_data)

        # Create a new finished product receipt that is released and has stock.
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
        response = self.client.get(reverse('inventory:api_get_sell_stock'))

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), initial_count + 1)
        
        # Find the newly added item in the response to verify its details
        new_item = next((item for item in data if item['batch_number'] == 'FPB-API-001'), None)
        self.assertIsNotNone(new_item)
        self.assertEqual(new_item['product_name'], self.final_product.name)
        self.assertEqual(new_item['available_qty'], 100.0)

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
