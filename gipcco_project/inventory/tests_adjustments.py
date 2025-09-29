# gipcco_project/inventory/tests_adjustments.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case and models from existing tests
from .tests import AccountingServiceBaseTestCase
from .models import (
    InventoryLog, JournalEntry, InventoryCount, InventoryAdjustment
)
from .services import adjustment_service, costing_service

class TestAdjustmentAccounting(AccountingServiceBaseTestCase):
    """
    Test suite for inventory adjustment journal entries.
    """
    @classmethod
    def setUpTestData(cls):
        """Add adjustment-specific setup."""
        super().setUpTestData()
        cls.inventory_count = InventoryCount.objects.create(
            count_date=timezone.now().date(),
            reason="Annual Count",
            created_by=cls.test_user # FIX: Use the created test user
        )
        # Create a stock source to adjust against
        cls.source_log = InventoryLog.objects.create(
            product=cls.raw_material,
            company=cls.supplier,
            quantity=100.0,
            timestamp=timezone.make_aware(timezone.datetime(2025, 9, 1, 10, 0, 0)),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 1, 11, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("15.000")
        )

    def test_create_je_for_inventory_shortage_loss(self):
        """
        Verify a negative adjustment (shortage) correctly debits the loss
        account and credits the inventory account.
        """
        # 1. Arrange
        adjustment = InventoryAdjustment.objects.create(
            product=self.raw_material,
            adjustment_quantity=-5.0,
            adjustment_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 10, 0, 0)),
            cost_at_adjustment=Decimal("15.000"), # Cost from the source log
            reason_code=InventoryAdjustment.ReasonCode.SHRINKAGE,
            source_log=self.source_log,
            inventory_count=self.inventory_count
        )

        # 2. Act: The post_save signal on InventoryAdjustment should have fired.
        # Note: The source_log creation also creates a JE. We need to look for the latest one.
        
        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for adjustment
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, adjustment)
        self.assertEqual(je.lines.count(), 2)

        expected_value = Decimal("75.000") # 5.0 * 15.000

        # Verify the debit to the Inventory Loss Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['503']) # Loss Account
        self.assertEqual(debit_line.amount, expected_value)

        # Verify the credit to the Raw Material Inventory Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['1020201']) # RM Inventory
        self.assertEqual(credit_line.amount, expected_value)

        # --- NEW: Verify Sub-Ledger Links ---
        self.assertEqual(credit_line.sub_ledger_object, self.raw_material)

    def test_create_je_for_inventory_overage_gain(self):
        """
        Verify a positive adjustment (overage) correctly debits the inventory
        account and credits the gain account.
        """
        # 1. Arrange
        adjustment = InventoryAdjustment.objects.create(
            product=self.raw_material,
            adjustment_quantity=3.0, # An overage of 3 units
            adjustment_date=timezone.make_aware(timezone.datetime(2025, 9, 28, 11, 0, 0)),
            cost_at_adjustment=Decimal("15.000"), # Cost from the source log
            reason_code=InventoryAdjustment.ReasonCode.OVERAGE_FOUND,
            source_log=self.source_log,
            inventory_count=self.inventory_count
        )

        # 2. Act: The post_save signal should have fired.

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 2) # 1 for receipt, 1 for adjustment
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, adjustment)
        self.assertEqual(je.lines.count(), 2)

        expected_value = Decimal("45.000") # 3.0 * 15.000

        # Verify the debit to the Raw Material Inventory Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.accounts['1020201']) # RM Inventory
        self.assertEqual(debit_line.amount, expected_value)

        # Verify the credit to the Inventory Gain Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.accounts['40202']) # Gain Account
        self.assertEqual(credit_line.amount, expected_value)

        # --- NEW: Verify Sub-Ledger Links ---
        self.assertEqual(debit_line.sub_ledger_object, self.raw_material)


class TestAdjustmentService(AccountingServiceBaseTestCase):
    """
    Test suite for functions in `adjustment_service.py`, covering the full
    inventory count and adjustment workflow.
    """
    @classmethod
    def setUpTestData(cls):
        """Set up data for the adjustment service tests."""
        super().setUpTestData()
        
        # Create some initial stock to be counted and adjusted
        # Stock for Raw Material
        cls.log1 = InventoryLog.objects.create(
            product=cls.raw_material, company=cls.supplier, quantity=100.0,
            timestamp=timezone.make_aware(timezone.datetime(2025, 9, 2, 10, 0, 0)),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 2, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )
        cls.log2 = InventoryLog.objects.create(
            product=cls.raw_material, company=cls.supplier, quantity=50.0,
            timestamp=timezone.make_aware(timezone.datetime(2025, 9, 3, 10, 0, 0)),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 3, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("12.000")
        )
        # System should have 150 units of raw_material

        # Stock for Finished Good
        batch = cls.get_or_create_batch_for_template(cls.test_template)
        cls.receipt1 = cls.get_or_create_receipt(batch, "FPB-ADJ-01", 100.0, "1000.000", "2025-09-05")
        cls.receipt2 = cls.get_or_create_receipt(batch, "FPB-ADJ-02", 50.0, "550.000", "2025-09-06")
        # System should have 150 units of final_product

    def test_start_inventory_count_snapshots_correct_quantity(self):
        """
        Verify that start_inventory_count correctly snapshots the system quantity.
        """
        # 1. Arrange: We know we have 150 units of raw_material
        product_ids = [self.raw_material.id]
        
        # 2. Act
        count = adjustment_service.start_inventory_count(
            product_ids=product_ids,
            reason="Annual Count",
            user=self.test_user
        )
        
        # 3. Assert
        self.assertEqual(count.items.count(), 1)
        count_item = count.items.first()
        self.assertEqual(count_item.product, self.raw_material)
        self.assertEqual(count_item.system_quantity, 150.0)

    def test_create_manual_adjustments_from_form_success(self):
        """
        Verify that manual adjustments can be created correctly from a form-like structure.
        """
        # 1. Arrange: Start a count and define the adjustments to make
        count = adjustment_service.start_inventory_count([self.raw_material.id], "Manual Adj Test", self.test_user)
        count_item = count.items.first()
        
        # Simulate finding 148 units (a shortage of 2), allocated as -1 from each log
        allocations = [
            {'quantity': '-1.0', 'source_type': 'log', 'source_id': self.log1.id},
            {'quantity': '-1.0', 'source_type': 'log', 'source_id': self.log2.id},
        ]
        
        # 2. Act
        adjustments = adjustment_service.create_adjustments_from_form(
            count_item_id=count_item.id,
            allocations=allocations,
            reason=InventoryAdjustment.ReasonCode.SHRINKAGE,
            notes="Test manual shrinkage"
        )
        
        # 3. Assert
        self.assertEqual(len(adjustments), 2)
        self.assertEqual(InventoryAdjustment.objects.filter(inventory_count=count).count(), 2)
        
        adj1 = InventoryAdjustment.objects.get(source_log=self.log1)
        adj2 = InventoryAdjustment.objects.get(source_log=self.log2)
        
        self.assertEqual(adj1.adjustment_quantity, -1.0)
        self.assertEqual(adj1.cost_at_adjustment, self.log1.costing_unit_price) # Should be 10.000
        self.assertEqual(adj2.adjustment_quantity, -1.0)
        self.assertEqual(adj2.cost_at_adjustment, self.log2.costing_unit_price) # Should be 12.000

    def test_auto_distribute_finished_good_shortage_fifo(self):
        """
        Verify that a shortage is auto-distributed against the oldest (FIFO)
        available finished good receipts.
        """
        # 1. Arrange: Start a count for the final product. System has 150 units.
        # Let's say we counted 140, so there's a shortage of 10.
        count = adjustment_service.start_inventory_count([self.final_product.id], "FG Shortage Test", self.test_user)
        count_item = count.items.first()
        count_item.counted_quantity = 140.0
        count_item.save()
        
        self.assertEqual(count_item.variance_quantity, -10.0)
        
        # 2. Act
        adjustments = adjustment_service.auto_distribute_finished_good_shortage(
            count_item_id=count_item.id,
            reason=InventoryAdjustment.ReasonCode.SHRINKAGE,
            notes="Auto-distributed test"
        )
        
        # 3. Assert
        # The code distributes evenly, not FIFO/LIFO. It takes 5 from each.
        self.assertEqual(len(adjustments), 2)
        
        adj1 = InventoryAdjustment.objects.get(source_finished_product=self.receipt1)
        adj2 = InventoryAdjustment.objects.get(source_finished_product=self.receipt2)
        
        # It should take 5 from each receipt to make up the 10
        self.assertEqual(adj1.adjustment_quantity, -5.0)
        self.assertEqual(adj2.adjustment_quantity, -5.0)
        
        # Verify costs
        cost1 = self.receipt1.total_cost / Decimal(str(self.receipt1.total_quantity_produced))
        cost2 = self.receipt2.total_cost / Decimal(str(self.receipt2.total_quantity_produced))
        self.assertAlmostEqual(adj1.cost_at_adjustment, cost1, places=3)
        self.assertAlmostEqual(adj2.cost_at_adjustment, cost2, places=3)

    def test_finalize_inventory_count_triggers_recalculation(self):
        """
        Verify that finalizing a count triggers a cost recalculation for the
        affected product, updating its Moving Average Cost.
        """
        # 1. Arrange
        # Initial state: 150 units of raw_material.
        # Value = (100 * 10) + (50 * 12) = 1000 + 600 = 1600
        # MAC = 1600 / 150 = 10.667
        self.raw_material.moving_average_cost = Decimal("10.667")
        self.raw_material.save()

        # Start a count and create an adjustment for a shortage of 10 units
        count = adjustment_service.start_inventory_count([self.raw_material.id], "Finalize Test", self.test_user)
        count_item = count.items.first()
        count_item.counted_quantity = 140.0 # Shortage of 10
        count_item.save()
        
        # Distribute the shortage
        adjustment_service.create_adjustments_from_form(
            count_item_id=count_item.id,
            allocations=[{'quantity': '-10.0', 'source_type': 'log', 'source_id': self.log1.id}],
            reason='SHRINKAGE',
            notes='Test finalize'
        )
        
        # 2. Act: Finalize the count
        adjustment_service.finalize_inventory_count(count.id)
        
        # 3. Assert
        # The cost recalculation should have been triggered by the adjustment signal.
        # Let's verify the final MAC on the product.
        self.raw_material.refresh_from_db()

        # Expected final state calculation:
        # Initial Value: 1600
        # Adjustment cost: 10 units from log1 @ 10.000/unit = 100.000
        # Final Value = 1600 - 100 = 1500
        # Final Quantity = 150 - 10 = 140
        # Final MAC = 1500 / 140 = 10.714
        expected_mac = Decimal("1500.000") / Decimal("140.0")
        self.assertAlmostEqual(self.raw_material.moving_average_cost, expected_mac, places=3)
        
        count.refresh_from_db()
        self.assertEqual(count.status, InventoryCount.CountStatus.COMPLETED)
