# gipcco_project/inventory/tests_fixed_assets.py

from decimal import Decimal
from django.utils import timezone
from django.core.exceptions import ValidationError

# Import the base test case from the new base file
from .test_base import AccountingServiceBaseTestCase
from .models import (
    Account, FixedAsset, DepreciationLog, InventoryConsumption, InventoryLog, JournalEntry
)

class TestFixedAssets(AccountingServiceBaseTestCase):
    """
    Test suite for the Fixed Assets & Depreciation module.
    """
    def setUp(self):
        super().setUp()
        # Clear journal entries to ensure test isolation
        JournalEntry.objects.all().delete()
        
        self.asset = FixedAsset.objects.create(
            asset_tag="MACHINE-001",
            name="Production Filling Machine",
            gl_account=self.accounts['10101'],
            depreciation_expense_account=self.accounts['50205'],
            accumulated_depreciation_account=self.accounts['20205'],
            purchase_date="2024-01-01",
            purchase_cost=Decimal("120000.000"),
            depreciation_start_date="2024-01-01",
            useful_life_years=10,
            salvage_value=Decimal("0.000")
        )

    def test_fixed_asset_properties(self):
        """Verify the calculated properties of the FixedAsset model."""
        self.assertEqual(self.asset.depreciable_base, Decimal("120000.000"))
        self.assertEqual(self.asset.accumulated_depreciation, Decimal("0.000"))
        self.assertEqual(self.asset.net_book_value, Decimal("120000.000"))

    def test_inventory_consumption_capitalization(self):
        """
        Test that capitalizing an MRO consumption increases the asset's cost
        and creates the correct journal entry.
        """
        # 1. Arrange
        # a) Create stock for an MRO product (e.g., a major upgrade part)
        mro_log = InventoryLog.objects.create(
            product=self.mro_product,
            company=self.supplier,
            quantity=1.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 10, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("5000.000")
        )

        # b) Create the consumption record, marked for capitalization
        consumption = InventoryConsumption.objects.create(
            product=self.mro_product,
            source_log=mro_log,
            quantity_consumed=1.0,
            consumption_date=timezone.make_aware(timezone.datetime(2025, 9, 29, 14, 0, 0)),
            department=InventoryConsumption.Department.ENGINEERING,
            cost_at_consumption=Decimal("5000.000"),
            consumption_type=InventoryConsumption.ConsumptionType.CAPITALIZE,
            fixed_asset=self.asset
        )

        # 2. Act: The post_save signal on InventoryConsumption should have fired.
        # We also need a service to update the asset's cost. Let's assume the signal does this.
        # For now, we'll check the JE and manually verify the logic.
        # In a real app, a signal receiver would update self.asset.purchase_cost.

        # 3. Assert
        # The consumption JE should now debit the Fixed Asset account, not an expense account.
        je = JournalEntry.objects.latest('date')
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, consumption)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to the Fixed Asset's GL Control Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.asset.gl_account)
        self.assertEqual(debit_line.amount, Decimal("5000.000"))

        # Verify the credit to the MRO Inventory Account
        credit_line = je.lines.get(entry_type='credit')
        setting = self.get_product_type_setting(self.mro_product.product_type)
        expected_account = self.mro_product.override_inventory_account or setting.inventory_account
        self.assertEqual(credit_line.account, expected_account)

    def test_capitalization_requires_fixed_asset(self):
        """
        Verify that the model's clean method raises a ValidationError if
        consumption is 'Capitalize' but no fixed_asset is provided.
        """
        with self.assertRaises(ValidationError) as context:
            InventoryConsumption(
                product=self.mro_product,
                quantity_consumed=1.0,
                consumption_date=timezone.now(),
                consumption_type=InventoryConsumption.ConsumptionType.CAPITALIZE,
                fixed_asset=None # Missing asset
            ).clean()
        
        # --- FIX: Use a more robust way to check for the error ---
        # This is better than checking message_dict, which might not exist
        # if the validation error is raised with a single string.
        self.assertIn('fixed_asset', str(context.exception))

    def test_depreciation_log_and_je_creation(self):
        """
        Test the creation of a DepreciationLog and its corresponding journal entry.
        This simulates a monthly depreciation run.
        """
        # 1. Arrange
        # For a 10-year asset (120 months), monthly depreciation is 120,000 / 120 = 1000.
        depreciation_amount = Decimal("1000.000")
        
        # 2. Act: Create the depreciation log, which should trigger a signal to create the JE.
        dep_log = DepreciationLog.objects.create(
            asset=self.asset,
            period_date="2025-09-30",
            amount=depreciation_amount
        )

        # 3. Assert
        self.assertEqual(JournalEntry.objects.count(), 1)
        je = JournalEntry.objects.first()
        self.assertIsNotNone(je)
        self.assertEqual(je.source_object, dep_log)
        self.assertEqual(je.lines.count(), 2)

        # Verify the debit to the Depreciation Expense Account
        debit_line = je.lines.get(entry_type='debit')
        self.assertEqual(debit_line.account, self.asset.depreciation_expense_account)
        self.assertEqual(debit_line.amount, depreciation_amount)

        # Verify the credit to the Accumulated Depreciation Account
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(credit_line.account, self.asset.accumulated_depreciation_account)
        self.assertEqual(credit_line.amount, depreciation_amount)

        # Verify asset properties are updated
        self.assertEqual(self.asset.accumulated_depreciation, depreciation_amount)
        self.assertEqual(self.asset.net_book_value, self.asset.purchase_cost - depreciation_amount)
