from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from datetime import date

from .test_base import AccountingServiceBaseTestCase
from .models import (
    ExpenseRequest, InventoryConsumption, PrepaidExpense, ExpenseLog, JournalEntry,
    FixedAsset, InventoryLog, Product
)
from .services import expense_service, approval_service, accounting_service

class TestExpenseWorkflow(AccountingServiceBaseTestCase):
    def setUp(self):
        super().setUp()
        JournalEntry.objects.all().delete()
        # Create a fixed asset to be used in capitalization tests
        self.fixed_asset = FixedAsset.objects.create(
            asset_tag="CAP-ASSET-01",
            name="Test Capital Asset",
            gl_account=self.accounts['10101'], # آلات ومعدات
            accumulated_depreciation_account=self.accounts['2020501'], # مجمع إهلاك - آلات ومعدات
            depreciation_expense_account=self.accounts['5020501'], # مصروف إهلاك - آلات ومعدات
            purchase_cost=Decimal("10000.000"),
            purchase_date=self.period.start_date,
            depreciation_start_date=self.period.start_date,
            useful_life_years=5
        )
        # Create an MRO product to be used in tests
        self.mro_product = Product.objects.create(
            name="Test MRO Product for Workflow",
            code="MRO-WF-TEST-001",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=False
        )
        # Create an amortizable product
        self.amortizable_product = Product.objects.create(
            name="Test Amortizable Product for Workflow",
            code="AMORT-WF-TEST-001",
            product_type=Product.ProductType.MRO,
            unit="Unit",
            is_amortizable=True
        )
        # Create stock for the products
        InventoryLog.objects.create(
            product=self.mro_product,
            quantity=50.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("25.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 2, 10, 0, 0))
        )
        InventoryLog.objects.create(
            product=self.amortizable_product,
            quantity=10.0,
            timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("1200.000"),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 3, 10, 0, 0))
        )

    def test_create_and_cancel_request(self):
        """Confirms a request can be created and then cancelled without creating any financial records."""
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("100.00"),
            request_date=date(2025, 9, 10),
            description="Test direct expense",
            cost_pool=self.child_pool_maintenance,
            category=ExpenseLog.Category.MAINTENANCE,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD
        )
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)

        expense_service.cancel_pending_request(request.id, self.test_user)
        request.refresh_from_db()

        self.assertEqual(request.status, ExpenseRequest.Status.CANCELLED)
        self.assertEqual(JournalEntry.objects.count(), 2) # Only the setup logs
        self.assertEqual(InventoryConsumption.objects.count(), 0)
        self.assertEqual(ExpenseLog.objects.count(), 0)

    def test_create_and_reject_request(self):
        """Confirms a request can be rejected, again with no financial impact."""
        request = expense_service.request_inventory_expense(
            user=self.test_user,
            product=self.mro_product,
            quantity=Decimal("2.0"),
            request_date=date(2025, 9, 11),
            description="Test inventory expense",
            cost_pool=self.child_pool_maintenance
        )
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)

        approval_service.reject_request(request.id, self.test_user, "Not approved budget.")
        request.refresh_from_db()

        self.assertEqual(request.status, ExpenseRequest.Status.REJECTED)
        self.assertIn("Not approved budget", request.rejection_reason)
        self.assertEqual(JournalEntry.objects.count(), 2) # Only the setup logs
        self.assertEqual(InventoryConsumption.objects.count(), 0)

    def test_reject_capitalization_request(self):
        """Ensures a capitalization request can be rejected with no financial impact."""
        initial_cost = self.fixed_asset.purchase_cost
        
        request = expense_service.request_inventory_capitalization(
            user=self.test_user,
            product=self.mro_product,
            quantity=Decimal("5.0"),
            request_date=date(2025, 9, 16),
            description="Attempt to capitalize MRO items",
            fixed_asset=self.fixed_asset
        )
        
        self.assertEqual(request.status, ExpenseRequest.Status.PENDING)
        
        # Reject the request
        rejection_reason="This is not a capitalizable expense."
        approval_service.reject_request(request.id, self.test_user, rejection_reason)
        
        request.refresh_from_db()
        self.fixed_asset.refresh_from_db()
        
        # Assertions
        self.assertEqual(request.status, ExpenseRequest.Status.REJECTED)
        self.assertEqual(request.rejection_reason, rejection_reason)
        self.assertEqual(self.fixed_asset.purchase_cost, initial_cost) # Asset cost should not change
        self.assertEqual(JournalEntry.objects.count(), 2) # Only setup JEs
        self.assertEqual(InventoryConsumption.objects.count(), 0)

    def test_approve_inventory_prepaid_request_creates_all_objects(self):
        """Asserts that approving a prepaid request correctly creates all linked objects."""
        request = expense_service.request_inventory_prepaid(
            user=self.test_user,
            product=self.amortizable_product,
            quantity=Decimal("1.0"),
            request_date=date(2025, 9, 15),
            description="Annual software license",
            asset_account=self.general_settings.prepaid_expenses_account,
            expense_account=self.accounts['50207'], # Insurance Expense
            start_date=date(2025, 9, 15),
            end_date=date(2026, 9, 14)
        )
        
        approval_service.approve_request(request.id, self.test_user)

        # Assertions
        self.assertEqual(InventoryConsumption.objects.count(), 1)
        self.assertEqual(PrepaidExpense.objects.count(), 1)
        self.assertEqual(JournalEntry.objects.count(), 3) # 2 setup logs + 1 consumption JE

        consumption = InventoryConsumption.objects.first()
        prepaid = PrepaidExpense.objects.first()
        je = JournalEntry.objects.latest('date')

        self.assertEqual(prepaid.source_content_object, consumption)
        self.assertEqual(je.source_object, consumption)
        self.assertEqual(prepaid.initial_amount, consumption.cost_at_consumption)
        
        debit_line = je.lines.get(entry_type='debit')
        credit_line = je.lines.get(entry_type='credit')
        self.assertEqual(debit_line.account, self.general_settings.prepaid_expenses_account)
        self.assertEqual(credit_line.account, accounting_service._get_product_inventory_account(self.amortizable_product))

    def test_approve_capitalization_request_updates_asset_cost(self):
        """Asserts that approving a capitalization request correctly increases the asset's cost."""
        initial_cost = self.fixed_asset.purchase_cost
        
        request = expense_service.request_inventory_capitalization(
            user=self.test_user,
            product=self.mro_product,
            quantity=Decimal("10.0"),
            request_date=date(2025, 9, 12),
            description="Capitalize spare parts onto asset",
            fixed_asset=self.fixed_asset
        )
        
        approval_service.approve_request(request.id, self.test_user)
        
        consumption = InventoryConsumption.objects.get(source_request=request)
        self.fixed_asset.refresh_from_db()
        
        expected_cost = initial_cost + consumption.cost_at_consumption
        self.assertEqual(self.fixed_asset.purchase_cost, expected_cost)

    def test_approve_direct_expense_request_creates_expense_log(self):
        """Asserts that approving a direct expense request creates the corresponding ExpenseLog."""
        request = expense_service.request_direct_expense(
            user=self.test_user,
            amount=Decimal("250.00"),
            request_date=date(2025, 9, 13),
            description="Urgent repairs",
            cost_pool=self.child_pool_maintenance,
            category=ExpenseLog.Category.MAINTENANCE,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD
        )
        
        approval_service.approve_request(request.id, self.test_user)
        
        self.assertEqual(ExpenseLog.objects.count(), 1)
        log = ExpenseLog.objects.first()
        self.assertEqual(log.source_request, request)
        self.assertEqual(log.amount, request.amount)
        self.assertEqual(log.cost_pool, request.cost_pool)

    def test_cannot_approve_non_pending_request(self):
        """Ensures that an already processed request cannot be approved again."""
        request = expense_service.request_direct_expense(
            user=self.test_user, amount=Decimal("50.00"), request_date=date(2025, 9, 14),
            description="Test", cost_pool=self.child_pool_rent, category=ExpenseLog.Category.RENT,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD
        )
        
        # Approve it once
        approval_service.approve_request(request.id, self.test_user)
        
        # Try to approve again
        with self.assertRaises(PermissionDenied):
            approval_service.approve_request(request.id, self.test_user)
            
        # Create and reject another request
        request2 = expense_service.request_direct_expense(
            user=self.test_user, amount=Decimal("60.00"), request_date=date(2025, 9, 15),
            description="Test 2", cost_pool=self.child_pool_rent, category=ExpenseLog.Category.RENT,
            classification=ExpenseLog.Classification.MANUFACTURING_OVERHEAD
        )
        approval_service.reject_request(request2.id, self.test_user, "Rejected")
        
        # Try to approve the rejected one
        with self.assertRaises(PermissionDenied):
            approval_service.approve_request(request2.id, self.test_user)

    def test_correct_approved_expense_creates_reversing_je(self):
        """Approves a request, then corrects it, asserting a reversing JE is created."""
        request = expense_service.request_inventory_expense(
            user=self.test_user,
            product=self.mro_product,
            quantity=Decimal("4.0"),
            request_date=date(2025, 9, 20),
            description="Expense for production line A",
            cost_pool=self.child_pool_maintenance
        )
        approval_service.approve_request(request.id, self.test_user)
        
        self.assertEqual(JournalEntry.objects.count(), 3) # 2 setup + 1 consumption
        original_je = JournalEntry.objects.latest('date')
        
        # Now, correct it
        accounting_service.correct_approved_expense(
            request_id=request.id,
            user=self.test_user,
            justification="Wrong quantity expensed, should have been 2 units."
        )
        
        self.assertEqual(JournalEntry.objects.count(), 4)
        reversing_je = JournalEntry.objects.latest('date')
        
        self.assertNotEqual(original_je.id, reversing_je.id)
        self.assertIn("Reversal of JE-", reversing_je.description)
        
        original_debits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='debit')}
        original_credits = {l.account.code: l.amount for l in original_je.lines.filter(entry_type='credit')}
        
        new_debits = {l.account.code: l.amount for l in reversing_je.lines.filter(entry_type='debit')}
        new_credits = {l.account.code: l.amount for l in reversing_je.lines.filter(entry_type='credit')}
        
        self.assertEqual(original_debits, new_credits)
        self.assertEqual(original_credits, new_debits)
