# gipcco_project/inventory/tests_costing.py

from decimal import Decimal
from django.utils import timezone

# Import the base test case from the new base file
from .test_base import AccountingServiceBaseTestCase
from .models import (
    InventoryLog, Batch, BatchItem, InventoryAdjustment, InventoryCount,
    ProductionReturn, Product, SalesOrder, SalesOrderItem, FinishedProductDispatch,
    JournalEntry, JournalEntryLine, ShopOrderTemplate, ProductTypeAccountingSettings,
    FinishedProductReceipt
)
from .services import costing_service

class TestCostingService(AccountingServiceBaseTestCase):
    """
    Test suite for functions in `costing_service.py`.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

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
            cost_at_consumption=Decimal("10.000")
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
            cost_at_consumption=Decimal("10.000")
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


class TestCostingWithOpeningBalance(AccountingServiceBaseTestCase):
    """
    Tests to verify that operations are correctly costed when starting
    from an opening balance created via the new "operational record" method.
    """
    def setUp(self):
        """Clear journal entries before each test to ensure isolation."""
        super().setUp()
        JournalEntry.objects.all().delete()

    def test_operations_with_raw_material_opening_balance(self):
        """
        Verify that consumption costing is correct when inventory starts
        from an opening balance log and is followed by another purchase.
        """
        # 1. Arrange: Create the opening balance as a standard InventoryLog
        # This represents the physical stock at go-live.
        ts_ob = timezone.make_aware(timezone.datetime(2025, 9, 1, 9, 0, 0))
        InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=100.0,
            timestamp=ts_ob, release_timestamp=ts_ob,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )

        # 2. Arrange: A subsequent purchase at a different price
        ts_purchase = timezone.make_aware(timezone.datetime(2025, 9, 5, 10, 0, 0))
        InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=50.0,
            timestamp=ts_purchase, release_timestamp=ts_purchase,
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("13.000")
        )

        # 3. Arrange: A consumption event after both receipts
        ts_consumption = timezone.make_aware(timezone.datetime(2025, 9, 10, 11, 0, 0))
        batch = Batch.objects.create(
            template=self.test_template, shop_order_number="SO-OB-1", batch_number="B-OB-1",
            creation_date=ts_consumption
        )
        item_to_cost = BatchItem.objects.create(
            batch=batch, primitive_product=self.raw_material,
            theoretical_quantity=60.0, actual_quantity=60.0
        )

        # 4. Act: Trigger the master recalculation service
        costing_service.recalculate_cost_history_for_product(
            self.raw_material.id,
            start_datetime=ts_ob
        )

        # 5. Assert
        # a) Verify the cost_at_consumption for the batch item
        item_to_cost.refresh_from_db()
        # Expected MAC at time of consumption:
        # Value = (100 * 10.00) + (50 * 13.00) = 1000 + 650 = 1650
        # Quantity = 100 + 50 = 150
        # MAC = 1650 / 150 = 11.00
        expected_mac_at_consumption = Decimal("11.000")
        self.assertAlmostEqual(item_to_cost.cost_at_consumption, expected_mac_at_consumption, places=3)

        # b) Verify the final MAC on the product object
        self.raw_material.refresh_from_db()
        # Expected final state:
        # Final Quantity = 150 - 60 = 90
        # Final Value = 1650 - (60 * 11.00) = 1650 - 660 = 990
        # Final MAC = 990 / 90 = 11.00
        expected_final_mac = Decimal("11.000")
        self.assertAlmostEqual(self.raw_material.moving_average_cost, expected_final_mac, places=3)

        # c) Verify the final inventory state using the state function
        final_state = costing_service.get_inventory_state_at_datetime(
            self.raw_material.id, timezone.make_aware(timezone.datetime(2025, 9, 28, 0, 0, 0))
        )
        self.assertEqual(final_state['quantity'], Decimal('90.0'))
        self.assertAlmostEqual(final_state['value'], Decimal('990.000'), places=3)

    def test_operations_with_finished_good_opening_balance(self):
        """
        Verify that a sale of a finished good that exists from an opening
        balance is correctly costed and generates the correct COGS journal entry.
        """
        # 1. Arrange: Create a unique final product for this test to avoid conflicts
        unique_final_product = Product.objects.create(
            name="Unique IV Drip Bag 500ml",
            code="UFP-IVDRIP-500",
            product_type=Product.ProductType.FINAL_PRODUCT,
            unit="Bag"
        )
        # ProductTypeAccountingSettings are already created in the base class setup.
        # No need to create them again.

        # Create the opening balance for a finished good using the
        # "Migration Batch" method.
        mig_template = ShopOrderTemplate.objects.create(
            name="MIG-TPL-FP-01", final_product=unique_final_product
        )
        mig_batch = Batch.objects.create(
            template=mig_template, shop_order_number="MIG-SO-FP-01", batch_number="MIGRATION",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 1, 8, 0, 0))
        )
        # This receipt represents the physical, costed stock at go-live.
        # Its creation will trigger a JE (Debit FG Inv, Credit WIP), which is
        # expected and will be balanced by the full opening balance JE.
        ob_receipt = FinishedProductReceipt.objects.create(
            batch=mig_batch, individual_batch_number="FPB-OB-001",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 1, 9, 0, 0)),
            total_quantity_produced=500.0,
            total_cost=Decimal("25000.000"), # Unit cost = 50.00
            status=FinishedProductReceipt.Status.RELEASED
        )

        # 2. Arrange: A subsequent production receipt at a different cost
        prod_batch = Batch.objects.create(
            template=mig_template, shop_order_number="PROD-SO-FP-01", batch_number="PROD-01",
            creation_date=timezone.make_aware(timezone.datetime(2025, 9, 10, 8, 0, 0))
        )
        prod_receipt = FinishedProductReceipt.objects.create(
            batch=prod_batch, individual_batch_number="FPB-PROD-001",
            receipt_date=timezone.make_aware(timezone.datetime(2025, 9, 11, 9, 0, 0)),
            total_quantity_produced=150.0,
            total_cost=Decimal("8250.000"), # Unit cost = 55.00
            status=FinishedProductReceipt.Status.RELEASED
        )

        # 3. Arrange: Create a sales order and dispatch for the opening balance stock.
        so = SalesOrder.objects.create(
            customer=self.customer,
            order_date=timezone.make_aware(timezone.datetime(2025, 9, 15, 10, 0, 0)),
            so_number="SO-OB-SALE-01"
        )
        so_item = SalesOrderItem.objects.create(
            sales_order=so,
            finished_product=ob_receipt,
            quantity_ordered=40.0,
            base_price_per_unit=Decimal("75.000")
        )
        # The dispatch will trigger the sales JE.
        dispatch = FinishedProductDispatch.objects.create(
            sales_order_item=so_item,
            quantity=40.0,
            dispatch_date=timezone.make_aware(timezone.datetime(2025, 9, 16, 11, 0, 0)),
            cost_at_dispatch=Decimal("2000.000") # 40 units * 50.00 unit cost from OB
        )

        # 4. Assert
        # a) Verify the final inventory state of the finished product
        import logging
        logging.basicConfig(level=logging.DEBUG)
        final_state = costing_service.get_inventory_state_at_datetime(
            unique_final_product.id, timezone.make_aware(timezone.datetime(2025, 9, 28, 0, 0, 0))
        )
        # Expected Quantity = 500 (OB) + 150 (Prod) - 40 (Sale) = 610
        # Expected Value = 25000 (OB) + 8250 (Prod) - 2000 (COGS) = 31250
        self.assertEqual(final_state['quantity'], Decimal('610.0'))
        self.assertAlmostEqual(final_state['value'], Decimal('31250.000'), places=3)

        # b) Verify the COGS portion of the sales journal entry
        self.assertEqual(JournalEntry.objects.count(), 3) # 1 for OB, 1 for Prod, 1 for sale
        sales_je = JournalEntry.objects.latest('date')
        self.assertEqual(sales_je.source_object, dispatch)

        cogs_debit_line = sales_je.lines.get(
            account=ProductTypeAccountingSettings.objects.get(product_type=Product.ProductType.FINAL_PRODUCT, inventory_account=self.accounts['1020206']).cogs_or_expense_account,
            entry_type=JournalEntryLine.EntryType.DEBIT
        )
        fg_credit_line = sales_je.lines.get(
            account=self.general_settings.finished_goods_inventory,
            entry_type=JournalEntryLine.EntryType.CREDIT
        )

        expected_cogs = Decimal("2000.000")
        self.assertEqual(cogs_debit_line.amount, expected_cogs)
        self.assertEqual(fg_credit_line.amount, expected_cogs)
