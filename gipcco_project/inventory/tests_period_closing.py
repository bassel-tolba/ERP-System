# gipcco_project/inventory/tests_period_closing.py

from django.urls import reverse
from django.test import Client
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth.models import User, Permission

from .test_base import AccountingServiceBaseTestCase
from .models import (
    FinancialPeriod, PeriodCloseChecklist, BankReconciliation, JournalEntry, 
    BankAccount, SupplierInvoice, CustomerInvoice, FinishedProductReceipt, Batch
)
from .services.period_closing_service import update_checklist_for_period, run_all_period_end_tasks
from .models import OverheadAllocationRun


class TestPeriodClosingCockpit(AccountingServiceBaseTestCase):
    """
    Test suite for the period closing cockpit and its associated logic.
    """
    def setUp(self):
        """This method will run before each test."""
        super().setUp()
        # Add the specific permission required for the close_period_action view.
        change_fp_perm = Permission.objects.get(codename='change_financialperiod')
        self.test_user.user_permissions.add(change_fp_perm)
        # We need to get the user again from DB to refresh its permissions
        self.test_user = User.objects.get(pk=self.test_user.pk)

        self.client = Client()
        self.client.login(username='testuser', password='password')
        # Ensure the checklist exists for the default period
        self.checklist, _ = PeriodCloseChecklist.objects.get_or_create(financial_period=self.period)

    def test_cockpit_view_loads_correctly(self):
        """Verify that the closing cockpit view loads for an open period."""
        response = self.client.get(reverse('inventory:close_period_cockpit', kwargs={'period_id': self.period.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/close_period_cockpit.html')
        self.assertIn('checklist', response.context)

    def test_cockpit_view_redirects_for_closed_period(self):
        """Verify that accessing the cockpit for a closed period redirects."""
        self.period.status = FinancialPeriod.Status.CLOSED
        self.period.save()
        response = self.client.get(reverse('inventory:close_period_cockpit', kwargs={'period_id': self.period.id}))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))

    def test_api_checklist_status_incomplete(self):
        """Verify the checklist API reports incomplete status correctly."""
        # Arrange: Explicitly create an incomplete state by adding a draft manual JE.
        JournalEntry.objects.create(
            date=timezone.make_aware(timezone.datetime.combine(self.period.start_date, timezone.datetime.min.time())),
            description="Draft JE for testing",
            status=JournalEntry.Status.DRAFT
            # content_type is null by default, making it manual
        )

        # Act: Call the API
        response = self.client.get(reverse('inventory:api_period_checklist_status', kwargs={'period_id': self.period.id}))
        
        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertFalse(data['all_banks_reconciled']['status'])
        self.assertFalse(data['no_draft_manual_jes']['status'])
        self.assertFalse(self.checklist.is_overhead_posted)

    def test_api_checklist_status_complete(self):
        """Verify the checklist API reports complete status when all tasks are done."""
        # 1. CORRECTED: Create a reconciled record for EACH bank account in the period.
        for bank_account in BankAccount.objects.all():
            BankReconciliation.objects.create(
                bank_account=bank_account,
                statement_date=self.period.end_date,
                statement_opening_balance=Decimal("1000.00"),
                statement_closing_balance=Decimal("1000.00"),
                status=BankReconciliation.Status.RECONCILED
            )
        
        # 2. Ensure there are no draft JEs in the period
        JournalEntry.objects.filter(
            date__gte=self.period.start_date,
            date__lte=self.period.end_date,
            status=JournalEntry.Status.DRAFT
        ).delete()

        # 3. Manually set the other flags for testing purposes
        self.checklist.is_depreciation_run = True
        self.checklist.is_overhead_posted = True
        self.checklist.save()

        # 4. Call the API
        response = self.client.get(reverse('inventory:api_period_checklist_status', kwargs={'period_id': self.period.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # 5. Assert all checks are now true
        self.assertTrue(data['all_banks_reconciled']['status'])
        self.assertTrue(data['no_draft_manual_jes']['status'])
        self.assertTrue(data['is_inventory_valuation_run']['status']) # Default true
        
        # Check the overall completeness from the model property
        self.period.refresh_from_db()
        # We need to manually update the checklist flags that the service doesn't handle
        update_checklist_for_period(self.period)
        self.assertTrue(self.period.checklist.is_complete)

    def test_close_period_action_fails_if_checklist_incomplete(self):
        """Verify that the final close action fails if the checklist is not complete."""
        self.period.status = FinancialPeriod.Status.PENDING_CLOSE
        self.period.save()
        
        # Checklist is incomplete by default
        response = self.client.post(reverse('inventory:close_period_action', kwargs={'period_id': self.period.id}))
        
        # The view currently redirects, but a more robust implementation might return an error.
        # For now, we check that the status has NOT changed.
        self.assertEqual(response.status_code, 302)
        self.period.refresh_from_db()
        self.assertEqual(self.period.status, FinancialPeriod.Status.PENDING_CLOSE)

    def test_close_period_action_succeeds_if_checklist_complete(self):
        """Verify that the final close action succeeds if the checklist is complete."""
        # Use the period from the test class setup
        period = self.period
        period.status = FinancialPeriod.Status.PENDING_CLOSE
        period.save()

        # Make the checklist complete by satisfying ALL conditions explicitly

        # 1. Delete draft JEs for the period
        JournalEntry.objects.filter(
            date__gte=period.start_date,
            date__lte=period.end_date,
            status=JournalEntry.Status.DRAFT,
            content_type__isnull=True
        ).delete()

        # 2. Create reconciled records for all bank accounts for the period.
        for bank_account in BankAccount.objects.all():
            BankReconciliation.objects.create(
                bank_account=bank_account,
                statement_date=period.end_date,
                statement_opening_balance=Decimal("1000.00"),
                statement_closing_balance=Decimal("1000.00"),
                status=BankReconciliation.Status.RECONCILED
            )
        
        # 3. Ensure no draft invoices exist for the period.
        SupplierInvoice.objects.filter(
            invoice_date__gte=period.start_date,
            invoice_date__lte=period.end_date,
            status=SupplierInvoice.InvoiceStatus.DRAFT
        ).delete()
        CustomerInvoice.objects.filter(
            invoice_date__gte=period.start_date,
            invoice_date__lte=period.end_date,
            status=CustomerInvoice.InvoiceStatus.DRAFT
        ).delete()

        # 4. --- NEW: Set up data for and run the master period-end task orchestrator ---
        
        # a) Create a FinishedProductReceipt with driver data to allow overhead to run
        batch = Batch.objects.create(
            template=self.test_template,
            shop_order_number="SO-CLOSE-TEST",
            batch_number="B-CLOSE-TEST",
            creation_date=period.start_date,
            machine_hours_consumed=10
        )
        FinishedProductReceipt.objects.create(
            batch=batch,
            individual_batch_number="FPB-CLOSE-TEST",
            receipt_date=period.end_date,
            total_cost=Decimal("100.00"),
            total_quantity_produced=10
        )
        
        # b) Create the OverheadAllocationRun instance that the service will find
        OverheadAllocationRun.objects.create(
            financial_period=period,
            cost_pool=self.parent_pool,
            allocation_driver=self.machine_hours_driver,
        )

        # c) Call the master service to run all automated tasks (Depreciation, Amortization, etc.)
        run_all_period_end_tasks(period)
        
        # 5. Now, call the update service one last time to refresh calculated fields
        #    and get the final checklist object for assertion.
        final_checklist = update_checklist_for_period(period)

        # 6. Sanity Check: Verify the state is complete before making the request.
        self.assertTrue(
            final_checklist.is_complete,
            "The checklist's is_complete property returned False before the final POST request."
        )

        # 7. Act: Post to the close action view.
        response = self.client.post(reverse('inventory:close_period_action', kwargs={'period_id': period.id}))
        
        # 8. Assert: The redirect should now be to the fiscal year list, and the status updated.
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))
        
        period.refresh_from_db()
        self.assertEqual(period.status, FinancialPeriod.Status.CLOSED)
