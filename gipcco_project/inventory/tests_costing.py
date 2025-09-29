# gipcco_project/inventory/tests_costing.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case and models from existing tests
from .tests import AccountingServiceBaseTestCase
from .models import (
    InventoryLog, Batch, BatchItem, InventoryAdjustment, InventoryCount,
    ProductionReturn, OpeningBalance
)
from .services import costing_service

class TestCostingService(AccountingServiceBaseTestCase):
    """
    Test suite for functions in `costing_service.py`.
    """
    def test_get_inventory_state_at_datetime_complex_scenario(self):
        """
        Verify that get_inventory_state_at_datetime correctly calculates quantity
        and value through a series of chronological transactions.
        """
        # 1. Arrange: Create a sequence of transactions for self.raw_material
        # Sept 5: Receive 100 units @ 10.00 each. State: 100 units, 1000.00 value
        ts1 = timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0))
        log1 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=100.0,
            timestamp=ts1,
            release_timestamp=ts1,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )

        # Sept 10: Consume 20 units. Avg cost is 10.00. State: 80 units, 800.00 value
        batch1 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-CS-1", batch_number="B-CS-1",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 10, 11, 0, 0))
        )
        BatchItem.objects.create(
            batch=batch1, primitive_product=self.raw_material,
            theoretical_quantity=20.0,
            actual_quantity=20.0,
            cost_at_consumption=Decimal("10.000"), source_type='inventory_log'
        )

        # Sept 15: Receive 50 units @ 12.00 each. State: 130 units, 800 + 600 = 1400.00 value
        ts2 = timezone.make_aware(timezone.datetime(2025, 9, 15, 12, 0, 0))
        log2 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=50.0,
            timestamp=ts2,
            release_timestamp=ts2,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("12.000")
        )

        # Sept 20: Adjust out 5 units (shortage). Avg cost is 1400/130 = 10.769.
        # Value reduction: 5 * 10.769 = 53.845.
        # State: 125 units, 1400 - 53.845 = 1346.155 value
        InventoryAdjustment.objects.create(
            product=self.raw_material, adjustment_quantity=-5.0,
            adjustment_date=timezone.make_aware(timezone.datetime(2025, 9, 20, 13, 0, 0)),
            cost_at_adjustment=Decimal("10.769"), reason_code='SHRINKAGE',
            source_log=log1, inventory_count=InventoryCount.objects.create(count_date=timezone.now().date(), reason="test", created_by=self.test_user)
        )

        # Sept 25: Return 10 units to stock. Value based on original source (log1 @ 10.00)
        # State: 135 units, 1346.155 + 100 = 1446.155 value
        ProductionReturn.objects.create(
            product=self.raw_material, source_log=log1,
            quantity=10.0, return_date=timezone.make_aware(timezone.datetime(2025, 9, 25, 14, 0, 0)),
            notes="Excess material from Batch B-TEST-001"
        )

        # 2. Act & Assert: Check the state at various points in time
        # Before anything happens
        state_initial = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 1, 0, 0, 0))
        )
        self.assertEqual(state_initial['quantity'], Decimal('0'))
        self.assertEqual(state_initial['value'], Decimal('0'))

        # After first receipt
        state_after_log1 = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 6, 0, 0, 0))
        )
        self.assertEqual(state_after_log1['quantity'], Decimal('100.0'))
        self.assertAlmostEqual(state_after_log1['value'], Decimal('1000.000'), places=3)

        # After consumption
        state_after_consume = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 11, 0, 0, 0))
        )
        self.assertEqual(state_after_consume['quantity'], Decimal('80.0'))
        self.assertAlmostEqual(state_after_consume['value'], Decimal('800.000'), places=3)

        # After second receipt
        state_after_log2 = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 16, 0, 0, 0))
        )
        self.assertEqual(state_after_log2['quantity'], Decimal('130.0'))
        self.assertAlmostEqual(state_after_log2['value'], Decimal('1400.000'), places=3)

        # After adjustment (Note: cost_at_adjustment is a snapshot, so we use its value)
        state_after_adj = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 21, 0, 0, 0))
        )
        self.assertEqual(state_after_adj['quantity'], Decimal('125.0'))
        self.assertAlmostEqual(state_after_adj['value'], Decimal('1346.155'), places=3)

        # After return
        state_final = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 26, 0, 0, 0))
        )
        self.assertEqual(state_final['quantity'], Decimal('135.0'))
        self.assertAlmostEqual(state_final['value'], Decimal('1446.155'), places=3)

    def test_recalculate_cost_history_for_product_after_correction(self):
        """
        Verify that recalculate_cost_history_for_product correctly updates
        downstream consumption costs and the final product MAC after a
        historical correction.
        """
        # 1. Arrange: Create an initial sequence of transactions
        # Sept 5: Receive 100 units @ WRONG price of 10.00.
        ts1 = timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0))
        log1 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=100.0,
            timestamp=ts1,
            release_timestamp=ts1,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )

        # Sept 10: Consume 20 units. Cost is INCORRECTLY recorded as 10.00.
        batch1 = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-RCL-1", batch_number="B-RCL-1",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 10, 11, 0, 0))
        )
        item_to_recalculate = BatchItem.objects.create(
            batch=batch1, primitive_product=self.raw_material,
            theoretical_quantity=20.0,
            actual_quantity=20.0,
            cost_at_consumption=Decimal("10.000"), source_type='inventory_log'
        )

        # Sept 15: Receive 50 units @ 12.00.
        ts2 = timezone.make_aware(timezone.datetime(2025, 9, 15, 12, 0, 0))
        log2 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=50.0,
            timestamp=ts2,
            release_timestamp=ts2,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("12.000")
        )
        
        # Pre-recalculation state:
        # Stock: 130 units (100-20+50)
        # Value: 1400.00 (100*10 - 20*10 + 50*12)
        # MAC: 1400 / 130 = 10.769
        self.raw_material.moving_average_cost = Decimal("10.769")
        self.raw_material.save()

        # 2. Act
        # a) Correct the historical error
        log1.base_unit_price = Decimal("11.500") # Correct price is 11.50
        log1.save()

        # b) Trigger the recalculation from the date of the change
        costing_service.recalculate_cost_history_for_product(
            self.raw_material.id,
            start_datetime=log1.release_timestamp
        )

        # 3. Assert
        # a) Assert that the downstream BatchItem's cost was updated
        item_to_recalculate.refresh_from_db()
        # The cost should now be the correct MAC at the time of consumption (Sept 10),
        # which was based purely on the corrected price of the first log.
        self.assertAlmostEqual(item_to_recalculate.cost_at_consumption, Decimal("11.500"), places=3)

        # b) Assert the final Moving Average Cost on the product is correct
        self.raw_material.refresh_from_db()
        # Expected final state calculation:
        # Value of log1 = 100 * 11.50 = 1150.00
        # Value consumed = 20 * 11.50 = 230.00
        # Value of log2 = 50 * 12.00 = 600.00
        # Final Value = 1150 - 230 + 600 = 1520.00
        # Final Quantity = 100 - 20 + 50 = 130.0
        # Final MAC = 1520.00 / 130.0 = 11.692
        expected_mac = Decimal("1520.000") / Decimal("130.0")
        self.assertAlmostEqual(self.raw_material.moving_average_cost, expected_mac, places=3)

    def test_costing_with_opening_balance(self):
        """
        Verify that an OpeningBalance is correctly included in cost calculations.
        """
        # 1. Arrange
        # Sept 1: Opening balance of 50 units with a total value of 525.00 (unit cost 10.50)
        OpeningBalance.objects.create(
            product=self.raw_material,
            quantity=50.0,
            balance_date=timezone.make_aware(timezone.datetime(2025, 9, 1, 0, 0, 0)),
            total_value=Decimal("525.000")
        )

        # Sept 5: Receive 100 units @ 12.00 each.
        ts1 = timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0))
        InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=100.0,
            timestamp=ts1,
            release_timestamp=ts1,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("12.000")
        )

        # 2. Act: Get the state after the receipt
        state = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 6, 0, 0, 0))
        )

        # 3. Assert
        # Expected Quantity = 50 (OB) + 100 (Log) = 150
        # Expected Value = 525 (OB) + (100 * 12) = 525 + 1200 = 1725
        self.assertEqual(state['quantity'], Decimal('150.0'))
        self.assertAlmostEqual(state['value'], Decimal('1725.000'), places=3)

        # Verify MAC calculation
        mac = state['value'] / state['quantity']
        expected_mac = Decimal("1725.000") / Decimal("150.0") # 11.50
        self.assertAlmostEqual(mac, expected_mac, places=3)
