# gipcco_project/inventory/tests_batches.py
from datetime import date
from decimal import Decimal
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum

from .test_base import AccountingServiceBaseTestCase
from .models import Batch, BatchItem, InventoryLog, FinishedProductReceipt, JournalEntry, ProductionReturn
from django.contrib.contenttypes.models import ContentType
from .services import batch_service

class BatchesViewsTest(AccountingServiceBaseTestCase):
    """
    Test suite for views related to Batches (Production Plans).
    """
    def setUp(self):
        super().setUp()
        self.client.login(username='testuser', password='password')
        # Clean up any batch-related data that might persist between tests
        FinishedProductReceipt.objects.all().delete()
        ProductionReturn.objects.all().delete()
        BatchItem.objects.all().delete()
        Batch.objects.all().delete()
        JournalEntry.objects.all().delete()

        # Create stock that will be used across multiple tests in this class
        # Create stock using the standardized helper to ensure all fields are correctly populated
        self.log1 = self.create_inventory_log(
            company=self.supplier,
            product=self.raw_material,
            quantity=100.0,
            base_unit_price="10.000"
        )
        self.log2 = self.create_inventory_log(
            company=self.supplier,
            product=self.packaging_material,
            quantity=200.0,
            base_unit_price="1.500"
        )

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
        # NEW: Assert status is Draft and no JE exists
        self.assertEqual(new_batch.status, Batch.Status.DRAFT)
        self.assertFalse(JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=new_batch.id
        ).exists())
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': new_batch.pk}))
        # NEW: Assert the updated success message for draft creation
        self.assertContains(response, "تم إنشاء مسودة أمر التشغيل &#x27;SO-NEW-001&#x27; بنجاح.")

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

    def test_batch_workflow_views(self):
        """
        Test the full batch workflow from Draft -> Submitted -> Approved -> In Progress -> Cancelled.
        """
        # 1. Create a draft batch first
        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number='SO-WORKFLOW-001',
            batch_number_from='301',
            creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        self.assertEqual(batch.status, Batch.Status.DRAFT)

        # 2. Submit for Approval
        submit_url = reverse('inventory:submit_batch', kwargs={'pk': batch.pk})
        response = self.client.post(submit_url, follow=True)
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "تم إرسال أمر التشغيل للموافقة.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.PENDING_APPROVAL)
        self.assertEqual(batch.submitted_by, self.test_user)

        # 3. Approve
        approve_url = reverse('inventory:approve_batch', kwargs={'pk': batch.pk})
        response = self.client.post(approve_url, follow=True)
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "تمت الموافقة على أمر التشغيل.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.APPROVED)
        self.assertEqual(batch.approved_by, self.test_user)

        # 4. Start Production
        start_url = reverse('inventory:start_production', kwargs={'pk': batch.pk})
        response = self.client.post(start_url, follow=True)
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "تم بدء الإنتاج لأمر التشغيل.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.IN_PROGRESS)
        # Assert that the JE was created at this stage
        self.assertTrue(self.get_je_for_object(batch))

        # 5. Cancel the In-Progress Batch
        cancel_url = reverse('inventory:cancel_batch', kwargs={'pk': batch.pk})
        post_data = {'justification': 'Test cancellation'}
        response = self.client.post(cancel_url, post_data, follow=True)
        self.assertRedirects(response, reverse('inventory:batches'))
        self.assertContains(response, "تم إلغاء أمر التشغيل وتحديث التكاليف بنجاح.")
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.CANCELLED)
        # Assert that a reversing JE was created (now 2 JEs total for this object's lifecycle)
        self.assertEqual(JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).count(), 2)

    def test_reject_batch_workflow(self):
        """
        Test that a batch can be rejected and returned to Draft status.
        """
        # 1. Create a draft batch
        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number='SO-REJECT-001',
            batch_number_from='302',
            creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 5.0, 'actual_quantity': 5.0, 'source_log_id': self.log1.id}
            ]
        )
        self.assertEqual(batch.status, Batch.Status.DRAFT)

        # 2. Submit for Approval
        batch = batch_service.submit_batch_for_approval(batch, self.test_user)
        self.assertEqual(batch.status, Batch.Status.PENDING_APPROVAL)

        # 3. Reject the batch
        reject_url = reverse('inventory:reject_batch', kwargs={'pk': batch.pk})
        post_data = {'justification': 'Test rejection'}
        response = self.client.post(reject_url, post_data, follow=True)
        self.assertRedirects(response, reverse('inventory:view_batch', kwargs={'pk': batch.pk}))
        self.assertContains(response, "تم إرجاع أمر التشغيل إلى مسودة.")
        
        batch.refresh_from_db()
        self.assertEqual(batch.status, Batch.Status.DRAFT)
        self.assertIsNone(batch.submitted_by)
        self.assertIsNone(batch.submitted_at)
        self.assertFalse(self.get_je_for_object(batch, expect_one=False).exists(), "A JE was created for a rejected batch.")

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
        The batch must be IN_PROGRESS for this to be a valid action.
        """
        # Create and move batch to IN_PROGRESS
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number="SO-RETURN-ITEM",
            batch_number_from="B-RETURN-ITEM", creation_date=timezone.now().date(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 20.0, 'actual_quantity': 15.0, 'source_log_id': self.log1.id}
            ]
        )
        batch = batch_service.submit_batch_for_approval(batch, self.test_user)
        batch = batch_service.approve_batch(batch, self.test_user)
        batch = batch_service.start_batch_production(batch)
        
        item = batch.items.first()

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
        FinishedProductReceipt.objects.all().delete()
        BatchItem.objects.all().delete()
        Batch.objects.all().delete()
        JournalEntry.objects.all().delete()
        
        # Create fresh stock for each test to ensure isolation, dated in the past
        from datetime import timedelta
        log_date = timezone.now() - timedelta(days=1)

        self.log1 = self.create_inventory_log(
            company=self.supplier,
            product=self.raw_material,
            quantity=100.0,
            base_unit_price="10.000",
            log_date=log_date
        )
        self.log2 = self.create_inventory_log(
            company=self.supplier,
            product=self.packaging_material,
            quantity=200.0,
            base_unit_price="5.500",
            log_date=log_date
        )
        self.zero_cost_log = self.create_inventory_log(
            company=self.supplier,
            product=self.mro_product,
            quantity=100.0,
            base_unit_price="0.000",
            log_date=log_date
        )

    def test_start_production_zero_cost_no_je(self):
        """
        Verify that starting production on a batch with a total consumption cost of zero
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
        batch = batch_service.submit_batch_for_approval(batch, self.test_user)
        batch = batch_service.approve_batch(batch, self.test_user)
        
        # Act: Start production
        batch_service.start_batch_production(batch)

        # Assert that no Journal Entry was created for this batch
        je_exists = JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).exists()
        self.assertFalse(je_exists, "A journal entry was created for a zero-cost batch, but none was expected.")

    def test_cancel_batch_of_draft_succeeds(self):
        """
        Verify that cancelling a DRAFT batch succeeds without creating a reversing JE.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-CANCEL-DRAFT',
            batch_number_from='402', creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        self.assertEqual(batch.status, Batch.Status.DRAFT)
        
        # Act: Cancel the batch
        cancelled_batch = batch_service.cancel_batch(batch, self.test_user, "Test draft cancel")

        # Assert
        self.assertEqual(cancelled_batch.status, Batch.Status.CANCELLED)
        je_exists = JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).exists()
        self.assertFalse(je_exists, "A journal entry was created when cancelling a draft batch.")

    def test_update_draft_batch_success(self):
        """
        Verify that the update_batch service correctly modifies a DRAFT batch.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-UPDATE-DRAFT',
            batch_number_from='501', creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        self.assertEqual(batch.items.first().actual_quantity, 10.0)

        # Act: Update the batch with a different quantity
        batch_service.update_batch(
            batch=batch,
            shop_order_number='SO-UPDATE-DRAFT', batch_number_from='501',
            creation_date=date.today(),
            items_data=[
                {'item_id': batch.items.first().id, 'product_id': self.raw_material.id, 'theoretical_quantity': 20.0, 'actual_quantity': 20.0, 'source_log_id': self.log1.id}
            ]
        )

        # Assert
        batch.refresh_from_db()
        self.assertEqual(batch.items.first().actual_quantity, 20.0)
        je_exists = JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        ).exists()
        self.assertFalse(je_exists, "A journal entry was created when updating a draft batch.")

    def test_update_in_progress_batch_fails(self):
        """
        Verify that updating a batch that is not in DRAFT status fails.
        """
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-UPDATE-FAIL',
            batch_number_from='502', creation_date=date.today(),
            items_data=[{'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}]
        )
        batch.status = Batch.Status.IN_PROGRESS
        batch.save()

        with self.assertRaises(ValidationError):
            batch_service.update_batch(
                batch=batch, shop_order_number='SO-UPDATE-FAIL', batch_number_from='502',
                creation_date=date.today(), items_data=[]
            )

    def test_add_item_to_in_progress_batch_creates_separate_je(self):
        """
        Verify that add_item_to_batch on an IN_PROGRESS batch creates its own
        separate, auditable journal entry linked to the BatchItem.
        """
        # Create, approve, and start a batch
        batch = batch_service.create_batch(
            template_id=self.test_template.id, shop_order_number='SO-ADD-ITEM',
            batch_number_from='601', creation_date=date.today(),
            items_data=[
                {'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.log1.id}
            ]
        )
        batch = batch_service.submit_batch_for_approval(batch, self.test_user)
        batch = batch_service.approve_batch(batch, self.test_user)
        batch = batch_service.start_batch_production(batch)
        
        # Assert that one JE is linked to the batch itself
        batch_je_qs = self.get_je_for_object(batch, expect_one=False)
        self.assertEqual(batch_je_qs.count(), 1)
        original_je = batch_je_qs.first()

        # Act: Add a new item to the batch
        new_item = batch_service.add_item_to_batch(
            batch=batch,
            product_id=self.packaging_material.id,
            theoretical_quantity=5.0,
            actual_quantity=5.0,
            source_log_id=self.log2.id
        )

        # Assert: Check that a new JE is linked to the new_item
        supplemental_je = self.get_je_for_object(new_item)
        self.assertIsNotNone(supplemental_je)
        
        self.assertNotEqual(original_je.pk, supplemental_je.pk)
        
        # Correctly calculate the total debit for the assertion
        total_debit = supplemental_je.lines.filter(entry_type='D').aggregate(total=Sum('amount'))['total'] or Decimal('0.0')
        self.assertAlmostEqual(total_debit, Decimal("27.500"), "Supplemental JE has incorrect value (5 * 5.5).")

