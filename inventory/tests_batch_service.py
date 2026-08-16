from decimal import Decimal
from django.utils import timezone
from datetime import datetime
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from .test_base import AccountingServiceBaseTestCase
from .models import Batch, BatchItem, InventoryLog, JournalEntry, FinishedProductReceipt
from .services import batch_service, costing_service

class TestBatchService(AccountingServiceBaseTestCase):
    """
    Test suite for the batch_service.py module.
    This class tests the business logic for creating, updating, and deleting
    production batches and their items, ensuring data integrity and correct
    integration with accounting and costing systems.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rm_log = InventoryLog.objects.create(
            product=cls.raw_material,
            quantity=100.0,
            base_unit_price=Decimal('10.000'),
            status=InventoryLog.Status.RELEASED,
            release_timestamp=timezone.make_aware(datetime(2025, 9, 1, 10, 0, 0)),
            timestamp=timezone.make_aware(datetime(2025, 9, 1, 9, 0, 0)),
            qc_no="RM-LOG-001"
        )
        cls.pkg_log = InventoryLog.objects.create(
            product=cls.packaging_material,
            quantity=100.0,
            base_unit_price=Decimal('5.500'),
            status=InventoryLog.Status.RELEASED,
            release_timestamp=timezone.make_aware(datetime(2025, 9, 2, 10, 0, 0)),
            timestamp=timezone.make_aware(datetime(2025, 9, 2, 9, 0, 0)),
            qc_no="PKG-LOG-001"
        )

    def setUp(self):
        """
        Ensure each test starts with a clean slate. To delete the Batch objects
        created by the base class, we must first delete the FinishedProductReceipts
        that have a PROTECT relationship to them.
        """
        super().setUp()
        # Delete in order of dependency to avoid ProtectedError
        FinishedProductReceipt.objects.all().delete()
        BatchItem.objects.all().delete()
        Batch.objects.all().delete()

    def test_create_batch_success(self):
        """
        Verify that `create_batch` successfully creates a Batch, its items,
        and generates the correct journal entry by integrating costing internally.
        """
        creation_date = datetime(2025, 9, 10).date()
        items_data = [
            {'product_id': self.raw_material.id, 'theoretical_quantity': 50.0, 'actual_quantity': 50.0, 'source_log_id': self.rm_log.id},
            {'product_id': self.packaging_material.id, 'theoretical_quantity': 50.0, 'actual_quantity': 50.0, 'source_log_id': self.pkg_log.id},
        ]

        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-TEST-01",
            batch_number_from="B001",
            creation_date=creation_date,
            items_data=items_data,
            machine_hours_consumed=10.5,
            labor_hours_consumed=20.0
        )
        
        # Costing logic is now internal to the service call.

        self.assertEqual(Batch.objects.count(), 1)
        self.assertEqual(BatchItem.objects.count(), 2)

        created_batch = Batch.objects.first()
        self.assertEqual(created_batch.shop_order_number, "SO-TEST-01")

        # Verify cost snapshot is set correctly on the BatchItem by the service
        rm_item = created_batch.items.get(primitive_product=self.raw_material)
        self.assertEqual(rm_item.cost_at_consumption, Decimal('10.000'))

        je = JournalEntry.objects.get(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        )
        self.assertIsNotNone(je)
        
        total_debits = je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total']
        expected_total_cost = (Decimal('50.0') * Decimal('10.000')) + (Decimal('50.0') * Decimal('5.500'))
        self.assertEqual(total_debits, expected_total_cost)

    def test_create_batch_insufficient_stock_fails(self):
        """
        Verify that `create_batch` raises a ValidationError if stock is insufficient
        and that no database objects are created.
        """
        items_data = [
            {'product_id': self.raw_material.id, 'theoretical_quantity': 101.0, 'actual_quantity': 101.0, 'source_log_id': self.rm_log.id},
        ]

        with self.assertRaises(ValidationError) as cm:
            batch_service.create_batch(
                template_id=self.test_template.id,
                shop_order_number="SO-FAIL-01",
                batch_number_from="B-FAIL-01",
                creation_date=datetime(2025, 9, 10).date(),
                items_data=items_data
            )
        
        self.assertIn("كمية غير كافية", str(cm.exception))
        self.assertEqual(Batch.objects.count(), 0)
        self.assertEqual(BatchItem.objects.count(), 0)

    def test_create_continuation_batch_success(self):
        """
        Verify that a continuation batch is created correctly with a parent link.
        """
        parent_batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-PARENT-01",
            batch_number_from="B-PARENT-01",
            creation_date=datetime(2025, 9, 11).date(),
            items_data=[{'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.rm_log.id}]
        )

        continuation_batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-PARENT-01",
            batch_number_from="B-CONT-01",
            creation_date=datetime(2025, 9, 12).date(),
            items_data=[{'product_id': self.packaging_material.id, 'theoretical_quantity': 5.0, 'actual_quantity': 5.0, 'source_log_id': self.pkg_log.id}],
            is_continuation=True,
            parent_batch_id=parent_batch.id
        )

        self.assertTrue(continuation_batch.is_continuation)
        self.assertEqual(continuation_batch.parent_batch, parent_batch)
        self.assertEqual(Batch.objects.count(), 2)

    def test_update_batch_success(self):
        """
        Verify that `update_batch` correctly modifies a batch and its items,
        and that the associated journal entry is correctly recreated.
        """
        initial_batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-UPDATE-01",
            batch_number_from="B-UPDATE-01",
            creation_date=datetime(2025, 9, 15).date(),
            items_data=[{'product_id': self.raw_material.id, 'theoretical_quantity': 20.0, 'actual_quantity': 20.0, 'source_log_id': self.rm_log.id}]
        )
        initial_je = JournalEntry.objects.get(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=initial_batch.id
        )
        # Assert initial JE is correct (Service fix handles this now)
        self.assertEqual(initial_je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'], Decimal('200.000'))

        updated_items_data = [
            {'item_id': initial_batch.items.first().id, 'product_id': self.raw_material.id, 'theoretical_quantity': 30.0, 'actual_quantity': 30.0, 'source_log_id': self.rm_log.id}
        ]

        # Service handles costing internally
        recalc_start_date = batch_service.update_batch(
            batch=initial_batch,
            shop_order_number="SO-UPDATE-01-MODIFIED",
            creation_date=datetime(2025, 9, 16).date(),
            batch_number_from="B-UPDATE-01",
            items_data=updated_items_data,
            notes="Updated quantity"
        )
        
        # Recalculation is now internal to the service call.

        initial_batch.refresh_from_db()
        self.assertEqual(initial_batch.shop_order_number, "SO-UPDATE-01-MODIFIED")
        self.assertEqual(initial_batch.items.first().actual_quantity, 30.0)

        self.assertFalse(JournalEntry.objects.filter(pk=initial_je.id).exists())
        new_je = JournalEntry.objects.get(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=initial_batch.id
        )
        self.assertEqual(new_je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'], Decimal('300.000'))

    def test_delete_batch_success(self):
        """
        Verify that `delete_batch` removes the batch, its items, and the associated JE.
        """
        batch_to_delete = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-DELETE-01",
            batch_number_from="B-DELETE-01",
            creation_date=datetime(2025, 9, 18).date(),
            items_data=[{'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.rm_log.id}]
        )
        self.assertEqual(Batch.objects.count(), 1)

        # Service handles deletion and internal MAC recalculation
        batch_service.delete_batch(batch=batch_to_delete)

        self.assertEqual(Batch.objects.count(), 0)
        self.assertEqual(BatchItem.objects.count(), 0)
        self.assertFalse(JournalEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch_to_delete.id
        ).exists())

    def test_add_item_to_batch_success(self):
        """
        Verify that `add_item_to_batch` adds an item and the JE is updated.
        (Fixes required: Pass actual_quantity and source_log_id to service).
        """
        # Initial item: 10 RM @ 10.000 = 100.000
        batch = batch_service.create_batch(
            template_id=self.test_template.id,
            shop_order_number="SO-ADD-ITEM-01",
            batch_number_from="B-ADD-ITEM-01",
            creation_date=datetime(2025, 9, 20).date(),
            items_data=[{'product_id': self.raw_material.id, 'theoretical_quantity': 10.0, 'actual_quantity': 10.0, 'source_log_id': self.rm_log.id}]
        )
        
        initial_je = JournalEntry.objects.get(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        )
        # Assert initial JE is correct (Service fix handles this now)
        self.assertEqual(initial_je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'], Decimal('100.000'))

        # Add new item: 10 PM @ 5.500 = 55.000
        new_item = batch_service.add_item_to_batch(
            batch=batch,
            product_id=self.packaging_material.id,
            theoretical_quantity=10.0,
            actual_quantity=10.0, # Pass required argument
            source_log_id=self.pkg_log.id # Pass required argument
        )
        
        # Costing is now internal to the service call.

        self.assertFalse(JournalEntry.objects.filter(pk=initial_je.id).exists())
        updated_je = JournalEntry.objects.get(
            content_type=ContentType.objects.get_for_model(Batch),
            object_id=batch.id
        )
        expected_new_cost = (Decimal('10.0') * Decimal('10.000')) + (Decimal('10.0') * Decimal('5.500'))
        self.assertEqual(updated_je.lines.filter(entry_type='debit').aggregate(total=Sum('amount'))['total'], expected_new_cost)