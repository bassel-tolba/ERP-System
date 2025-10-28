# gipcco_project/inventory/tests_batches.py
from datetime import date
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone

from .test_base import AccountingServiceBaseTestCase
from .models import Batch, BatchItem, InventoryLog, FinishedProductReceipt, JournalEntry
from django.contrib.contenttypes.models import ContentType
from .services import batch_service

class BatchesViewsTest(AccountingServiceBaseTestCase):
    """
    Test suite for views related to Batches (Production Plans).
    """
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Create stock that will be used across multiple tests in this class
        now = timezone.now()
        cls.log1 = InventoryLog.objects.create(
            product=cls.raw_material,
            quantity=100.0,
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000"),
            timestamp=now,
            release_timestamp=now
        )
        cls.log2 = InventoryLog.objects.create(
            product=cls.packaging_material,
            quantity=200.0,
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("1.500"),
            timestamp=now,
            release_timestamp=now
        )

    def setUp(self):
        super().setUp()
        self.client.login(username='testuser', password='password')
        # Clean up any batch-related data that might persist between tests
        FinishedProductReceipt.objects.all().delete()
        BatchItem.objects.all().delete()
        Batch.objects.all().delete()

    def test_batches_list_view(self):
        """
        Test that the main batches list view loads correctly.
        """
        # Create a sample batch to be listed
        Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-TEST-001",
            batch_number="B-TEST-001",
            creation_date=timezone.now()
        )
        
        url = reverse('inventory:batches')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/batches.html')
        self.assertContains(response, "SO-TEST-001")
        self.assertIn('batches', response.context)

    def test_batches_list_view_search(self):
        """
        Test the search functionality on the batches list view.
        """
        Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-SEARCH-A",
            batch_number="B-SEARCH-A",
            creation_date=timezone.now()
        )
        Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-SEARCH-B",
            batch_number="B-SEARCH-B",
            creation_date=timezone.now()
        )

        url = reverse('inventory:batches')
        response = self.client.get(url, {'q': 'SO-SEARCH-A'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SO-SEARCH-A")
        self.assertNotContains(response, "SO-SEARCH-B")

    def test_create_batch_view_post_success(self):
        """
        Test successful creation of a new batch via a POST request.
        """
        url = reverse('inventory:create_batch')
        post_data = {
            'template_id': self.test_template.id,
            'shop_order_number': 'SO-NEW-001',
            'batch_number_from': '101',
            'batch_number_to': '',
            'creation_date': date.today().strftime('%Y-%m-%d'),
            'primitive_product_id': [self.raw_material.id, self.packaging_material.id],
            'theoretical_quantity': [10.0, 20.0],
            'actual_quantity': [10.0, 20.0],
            'source_log_id': [self.log1.id, self.log2.id],
        }

        response = self.client.post(url, post_data, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Batch.objects.filter(shop_order_number='SO-NEW-001').exists())
        new_batch = Batch.objects.get(shop_order_number='SO-NEW-001')
        self.assertEqual(new_batch.items.count(), 2)
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': new_batch.pk}))
        self.assertContains(response, "تم إنشاء أمر التشغيل &#x27;SO-NEW-001&#x27; وتحديث التكاليف بنجاح.")

    def test_create_batch_view_post_insufficient_stock(self):
        """
        Test that creating a batch fails if the requested quantity exceeds available stock.
        """
        url = reverse('inventory:create_batch')
        post_data = {
            'template_id': self.test_template.id,
            'shop_order_number': 'SO-FAIL-001',
            'batch_number_from': '201',
            'creation_date': date.today().strftime('%Y-%m-%d'),
            'primitive_product_id': [self.raw_material.id],
            'theoretical_quantity': [101.0], # More than available in log1
            'actual_quantity': [101.0],
            'source_log_id': [self.log1.id],
        }

        response = self.client.post(url, post_data, follow=True)
        
        self.assertFalse(Batch.objects.filter(shop_order_number='SO-FAIL-001').exists())
        self.assertContains(response, "حدث خطأ في البيانات المدخلة")
        self.assertContains(response, "كمية غير كافية للمنتج")

    def test_view_batch_view(self):
        """
        Test that the detail view for a single batch loads correctly.
        """
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-VIEW-001",
            batch_number="B-VIEW-001",
            creation_date=timezone.now()
        )
        url = reverse('inventory:view_batch', kwargs={'pk': batch.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/batch_view.html')
        self.assertContains(response, "SO-VIEW-001")
        self.assertEqual(response.context['batch'], batch)

    def test_cancel_batch_view_success(self):
        """
        Test the non-destructive cancellation of a batch.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number='SO-CANCEL-001',
            batch_number_from='301',
            creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        
        url = reverse('inventory:cancel_batch', kwargs={'pk': batch.pk})
        post_data = {'justification': 'Test cancellation'}
        
        response = self.client.post(url, post_data, follow=True)

        self.assertRedirects(response, reverse('inventory:batches'))
        self.assertContains(response, "تم إلغاء أمر التشغيل وتحديث التكاليف بنجاح.")
        
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.CANCELLED)

    def test_cancel_batch_view_fail_if_receipts_exist(self):
        """
        Test that a batch cannot be cancelled if finished goods have been received against it.
        """
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-CANCEL-FAIL",
            batch_number="B-CANCEL-FAIL",
            creation_date=timezone.now()
        )
        FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FP-001",
            receipt_date=date.today(),
            total_cost=Decimal("100.000"),
            total_quantity_produced=50.0
        )

        url = reverse('inventory:cancel_batch', kwargs={'pk': batch.pk})
        post_data = {'justification': 'This should fail'}
        
        response = self.client.post(url, post_data, follow=True)

        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "لا يمكن إلغاء أمر التشغيل")
        self.assertContains(response, "finished goods have already been received")
        
        batch.refresh_from_db()
        self.assertNotEqual(batch.status, Batch.Status.CANCELLED)

    def test_return_batch_item_view(self):
        """
        Test returning a portion of a consumed item from a batch back to inventory.
        """
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-RETURN-ITEM",
            batch_number="B-RETURN-ITEM",
            creation_date=timezone.now()
        )
        item = BatchItem.objects.create(
            batch=batch,
            primitive_product=self.raw_material,
            theoretical_quantity=20.0,
            actual_quantity=15.0,
            source_log=self.log1
        )

        url = reverse('inventory:return_batch_item', kwargs={'item_pk': item.pk})
        post_data = {
            'quantity': 5.0,
            'return_date': date.today().strftime('%Y-%m-%d'),
            'notes': 'Returned excess'
        }

        response = self.client.post(url, post_data, follow=True)

        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "تم إرجاع المادة من أمر التشغيل بنجاح.")
        self.assertTrue(batch.production_returns.filter(quantity=5.0).exists())


class BatchServiceTests(AccountingServiceBaseTestCase):
    """
    Test suite for the batch_service layer to test business logic in isolation.
    """
    def setUp(self):
        super().setUp()
        # Clean up batch data before each test
        BatchItem.objects.all().delete()
        Batch.objects.all().delete()
        
        # Create fresh stock for each test to ensure isolation
        now = timezone.now()
        self.log1 = InventoryLog.objects.create(
            product=self.raw_material,
            quantity=100.0,
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000"),
            timestamp=now,
            release_timestamp=now
        )
        self.log2 = InventoryLog.objects.create(
            product=self.packaging_material,
            quantity=200.0,
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("1.500"),
            timestamp=now,
            release_timestamp=now
        )
        self.zero_cost_log = InventoryLog.objects.create(
            product=self.mro_product,
            quantity=100.0,
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("0.000"), # Zero price
            timestamp=now,
            release_timestamp=now
        )

    def test_create_batch_zero_cost_no_je(self):
        """
        Verify that creating a batch with a total consumption cost of zero
        does NOT create a journal entry.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number='SO-ZERO-COST',
            batch_number_from='401',
            creation_date=date.today(),
            items_data=[
                {'product_id': self.mro_product.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.zero_cost_log.id}
            ]
        )

        # Assert that no Journal Entry was created for this batch
        je_exists = JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).exists()
        self.assertFalse(je_exists, "A journal entry was created for a zero-cost batch, but none was expected.")

    def test_cancel_batch_zero_cost_success(self):
        """
        Verify that cancelling a zero-cost batch (which has no JE) succeeds
        without raising an error. This confirms the recent fix.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-CANCEL-ZERO',
            batch_number_from='402', creation_date=date.today(),
            items_data=[
                {'product_id': self.mro_product.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.zero_cost_log.id}
            ]
        )
        # Pre-condition: Assert that no JE was created
        je_exists = JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).exists()
        self.assertFalse(je_exists, "Pre-condition failed: JE should not exist for zero-cost batch.")

        # Act: Cancel the batch
        cancelled_batch = batch_service.cancel_batch(batch, self.test_user, "Test zero cost cancel")

        # Assert
        self.assertEqual(cancelled_batch.status, Batch.Status.CANCELLED)
        # The absence of an exception is the main success criteria.

    def test_update_batch_deletes_and_recreates_je(self):
        """
        Verify that the update_batch service correctly deletes the old JE
        and creates a new one reflecting the updated values.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-UPDATE-TEST',
            batch_number_from='501', creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        original_je = self.get_je_for_object(batch)
        self.assertAlmostEqual(original_je.total_debit, Decimal("100.000"))

        # Act: Update the batch with a different quantity
        batch_service.update_batch(
            batch=batch,
            shop_order_number='SO-UPDATE-TEST', batch_number_from='501',
            creation_date=date.today(),
            items_data=[
                {'item_id': batch.items.first().id, 'product_id': self.raw_material.id, 'theoretical_quantity': 20.0, 'actual_quantity': 20.0, 'source_log_id': self.log1.id}
            ]
        )

        # Assert
        self.assertFalse(JournalEntry.objects.filter(pk=original_je.pk).exists(), "Old journal entry was not deleted.")
        new_je = self.get_je_for_object(batch)
        self.assertNotEqual(original_je.pk, new_je.pk, "A new journal entry was not created.")
        self.assertAlmostEqual(new_je.total_debit, Decimal("200.000"), "New JE does not reflect the updated value.")

    def test_add_item_to_batch_creates_separate_je(self):
        """
        Verify that add_item_to_batch creates its own separate, auditable
        journal entry linked to the BatchItem, not the parent Batch.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-ADD-ITEM',
            batch_number_from='601', creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        self.assertEqual(JournalEntry.objects.count(), 1)
        original_je = self.get_je_for_object(batch)

        # Act: Add a new item to the batch
        new_item = batch_service.add_item_to_batch(
            batch=batch,
            product_id=self.packaging_material.id,
            theoretical_quantity=5.0,
            actual_quantity=5.0,
            source_log_id=self.log2.id
        )

        # Assert
        self.assertEqual(JournalEntry.objects.count(), 2)
        self.assertTrue(JournalEntry.objects.filter(pk=original_je.pk).exists(), "Original JE was deleted or modified.")
        
        supplemental_je = self.get_je_for_object(new_item)
        self.assertNotEqual(original_je.pk, supplemental_je.pk)
        self.assertAlmostEqual(supplemental_je.total_debit, Decimal("7.500"), "Supplemental JE has incorrect value.")
