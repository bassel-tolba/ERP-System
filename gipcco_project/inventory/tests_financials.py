# gipcco_project/inventory/tests_financials.py

from decimal import Decimal
from django.contrib.auth.models import User, Permission
from django.test import Client
from django.urls import reverse
from django.utils import timezone

# Import the base test case from the existing tests file
from .tests import AccountingServiceBaseTestCase

from .models import (
    Company, SupplierInvoice, InventoryLog, Payment, PaymentApplication,
    Customer, SalesOrder, FinishedProductReceipt, FinishedProductDispatch,
    CustomerInvoice, CustomerPaymentApplication, BankTransfer, BankAccount,
    FiscalYear, FinancialPeriod, PeriodClosingAuditLog, Batch, SalesOrderItem,
    SupplierInvoiceItem, CostPool
)

class TestFinancialViews(AccountingServiceBaseTestCase):
    """
    Test suite for views in `financials.py`.
    """
    @classmethod
    def setUpTestData(cls):
        """Set up data for the entire test class."""
        super().setUpTestData()
        # The user is already created in the parent class's setUpTestData.
        # Add permissions needed for financial views
        reopen_perm = Permission.objects.get(codename='can_reopen_period')
        lock_perm = Permission.objects.get(codename='can_permanently_lock_period')
        change_je_perm = Permission.objects.get(codename='change_journalentry')
        change_fp_perm = Permission.objects.get(codename='change_financialperiod')
        
        cls.test_user.user_permissions.add(reopen_perm, lock_perm, change_je_perm, change_fp_perm)
        # We need to get the user again from DB to refresh its permissions
        cls.test_user = User.objects.get(pk=cls.test_user.pk)

    def setUp(self):
        """This method will run before each test to ensure a fresh client login."""
        self.client = Client()
        self.client.login(username='testuser', password='password')

    # A/P Tests
    def test_supplier_invoices_list_view(self):
        """Verify the supplier invoices list view loads and filters correctly."""
        # Create an invoice to test with
        SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-001",
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total_amount=Decimal("100.000")
        )
        
        # Test GET without filters
        response = self.client.get(reverse('inventory:supplier_invoices'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/supplier_invoices.html')
        self.assertEqual(len(response.context['invoices']), 1)

        # Test with supplier filter
        response = self.client.get(reverse('inventory:supplier_invoices'), {'supplier': self.supplier.id})
        self.assertEqual(len(response.context['invoices']), 1)

        # Test with status filter
        response = self.client.get(reverse('inventory:supplier_invoices'), {'status': SupplierInvoice.InvoiceStatus.AWAITING_PAYMENT})
        self.assertEqual(len(response.context['invoices']), 1)

    def test_create_supplier_invoice_view_post_success(self):
        """Verify creating a supplier invoice via POST succeeds."""
        receipt = InventoryLog.objects.create(
            product=self.raw_material,
            company=self.supplier,
            quantity=10.0,
            timestamp=timezone.now(),
            release_timestamp=timezone.make_aware(timezone.datetime(2025, 9, 10, 10, 0, 0)),
            status=InventoryLog.Status.RELEASED,
            base_unit_price=Decimal("10.000")
        )

        invoice_data = {
            'supplier': self.supplier.id,
            'invoice_number': 'INV-SUP-002',
            'invoice_date': '2025-09-25',
            'due_date': '2025-10-25',
            'receipt_ids': [receipt.id]
        }
        
        response = self.client.post(reverse('inventory:create_supplier_invoice'), invoice_data)
        
        self.assertEqual(response.status_code, 302) # Should redirect
        self.assertTrue(SupplierInvoice.objects.filter(invoice_number='INV-SUP-002').exists())
        new_invoice = SupplierInvoice.objects.get(invoice_number='INV-SUP-002')
        self.assertRedirects(response, reverse('inventory:view_supplier_invoice', kwargs={'pk': new_invoice.pk}))
        self.assertEqual(new_invoice.items.count(), 1)
        self.assertEqual(new_invoice.total_amount, Decimal("100.000"))

    def test_apply_payment_to_invoice_view_post_success(self):
        """Verify applying a payment to a supplier invoice works."""
        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier,
            invoice_number="INV-PAY-001",
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total_amount=Decimal("1000.000")
        )
        
        payment_data = {
            'bank_account': self.bank_account.id,
            'payment_date': '2025-09-26',
            'amount': '500.000',
            'description': 'Partial payment'
        }
        
        response = self.client.post(reverse('inventory:apply_payment_to_invoice', kwargs={'pk': invoice.pk}), payment_data)
        
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:view_supplier_invoice', kwargs={'pk': invoice.pk}))
        
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("500.000"))
        self.assertEqual(invoice.status, SupplierInvoice.InvoiceStatus.PARTIALLY_PAID)
        self.assertEqual(Payment.objects.filter(supplier=self.supplier).count(), 1)
        self.assertEqual(PaymentApplication.objects.count(), 1)

    def test_api_get_uninvoiced_receipts(self):
        """Verify the API for uninvoiced receipts works correctly."""
        # 1. Arrange
        # This one should NOT be on an invoice yet
        receipt1 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=10.0,
            timestamp=timezone.now(), release_timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )
        # This one WILL be on an invoice
        receipt2 = InventoryLog.objects.create(
            product=self.raw_material, company=self.supplier, quantity=20.0,
            timestamp=timezone.now(), release_timestamp=timezone.now(),
            status=InventoryLog.Status.RELEASED, base_unit_price=Decimal("10.000")
        )
        invoice = SupplierInvoice.objects.create(
            supplier=self.supplier, invoice_number="API-TEST-INV",
            invoice_date=timezone.now().date(), due_date=timezone.now().date(),
            total_amount=Decimal("200.000")
        )
        SupplierInvoiceItem.objects.create(invoice=invoice, receipt=receipt2, amount=Decimal("200.000"))

        # 2. Act
        response = self.client.get(reverse('inventory:api_get_uninvoiced_receipts', kwargs={'supplier_id': self.supplier.id}))

        # 3. Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['receipts']), 1)
        self.assertEqual(data['receipts'][0]['id'], receipt1.id)

    # A/R Tests
    def test_customer_invoices_list_view(self):
        """Verify the customer invoices list view loads and filters correctly."""
        CustomerInvoice.objects.create(
            customer=self.customer,
            invoice_number="CINV-001",
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total_amount=Decimal("200.000")
        )
        
        response = self.client.get(reverse('inventory:customer_invoices'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/customer_invoices.html')
        self.assertEqual(len(response.context['invoices']), 1)

    def test_create_customer_invoice_view_post_success(self):
        """Verify creating a customer invoice from a sales order dispatch works."""
        receipt = FinishedProductReceipt.objects.create(
            batch=Batch.objects.create(template=self.test_template, shop_order_number="SO-SALE-FIN", batch_number="B-SALE-FIN", creation_date=timezone.now()),
            individual_batch_number="FPB-SALE-FIN",
            receipt_date=timezone.now().date(),
            total_cost=Decimal("5000.000"),
            total_quantity_produced=100.0,
            status=FinishedProductReceipt.Status.RELEASED
        )
        so = SalesOrder.objects.create(customer=self.customer, order_date=timezone.now().date(), so_number="SO-FIN-TEST")
        so_item = SalesOrderItem.objects.create(sales_order=so, finished_product=receipt, quantity_ordered=10.0, base_price_per_unit=Decimal("80.000"), vat_rate=Decimal("0.14"))
        dispatch = FinishedProductDispatch.objects.create(sales_order_item=so_item, quantity=10.0, dispatch_date=timezone.now(), cost_at_dispatch=Decimal("500.000"))

        invoice_data = {
            'sales_order': so.id,
            'invoice_number': 'CINV-002',
            'invoice_date': '2025-09-26',
            'due_date': '2025-10-26',
            'dispatch_ids': [dispatch.id]
        }
        
        response = self.client.post(reverse('inventory:create_customer_invoice'), invoice_data)
        
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CustomerInvoice.objects.filter(invoice_number='CINV-002').exists())
        new_invoice = CustomerInvoice.objects.get(invoice_number='CINV-002')
        self.assertRedirects(response, reverse('inventory:view_customer_invoice', kwargs={'pk': new_invoice.pk}))
        self.assertEqual(new_invoice.items.count(), 1)
        # Expected total: (10 * 80) * 1.14 = 800 * 1.14 = 912
        self.assertEqual(new_invoice.total_amount, Decimal("912.000"))

    def test_apply_payment_to_customer_invoice(self):
        """Verify receiving and applying a payment against a customer invoice works."""
        # 1. Arrange
        # Create an invoice to apply payment to
        invoice = CustomerInvoice.objects.create(
            customer=self.customer,
            invoice_number="CINV-PAY-001",
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            total_amount=Decimal("912.000")
        )
        
        # 2. Act: Create a payment received from the customer
        payment = Payment.objects.create(
            payment_date="2025-09-28",
            amount=Decimal("912.000"),
            bank_account=self.bank_account,
            payment_type=Payment.PaymentType.PAYMENT_IN,
            description="Payment for CINV-PAY-001",
            customer=self.customer
        )
        # Apply it to the invoice
        CustomerPaymentApplication.objects.create(
            payment=payment,
            invoice=invoice,
            amount_applied=Decimal("912.000")
        )
        # Manually trigger the status update that a signal would normally handle
        invoice.amount_paid += Decimal("912.000")
        invoice.update_status()

        # 3. Assert
        invoice.refresh_from_db()
        self.assertEqual(invoice.amount_paid, Decimal("912.000"))
        self.assertEqual(invoice.status, CustomerInvoice.InvoiceStatus.PAID)
        self.assertEqual(payment.total_received_applied, Decimal("912.000"))
        self.assertEqual(payment.unapplied_amount, Decimal("0.000"))

    # Banking Tests
    def test_bank_accounts_dashboard_view_get_and_post_transfer(self):
        """Verify the banking dashboard loads and can create a bank transfer."""
        # Test GET
        response = self.client.get(reverse('inventory:bank_accounts_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/banking_dashboard.html')

        # Test POST for transfer
        transfer_data = {
            'source_account': self.bank_account.id,
            'destination_account': self.secondary_bank_account.id,
            'amount': '2000.000',
            'transfer_date': '2025-09-26',
            'description': 'Test Transfer'
        }
        
        response = self.client.post(reverse('inventory:bank_accounts_dashboard'), transfer_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:bank_accounts_dashboard'))
        self.assertTrue(BankTransfer.objects.filter(amount=Decimal("2000.000")).exists())

    # Period Management Tests
    def test_fiscal_year_list_view_and_create_year(self):
        """Verify the fiscal year list loads and can create a new year."""
        # Test GET
        response = self.client.get(reverse('inventory:fiscal_year_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/fiscal_year_list.html')

        # Test POST to create a new fiscal year with periods
        year_data = {
            'name': 'Test Year 2026',
            'start_date': '2026-01-01',
            'end_date': '2026-12-31',
            'generate_periods': 'on'
        }
        
        response = self.client.post(reverse('inventory:create_fiscal_year'), year_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))
        
        new_year = FiscalYear.objects.get(name='Test Year 2026')
        self.assertIsNotNone(new_year)
        self.assertEqual(new_year.periods.count(), 12)

    def test_edit_fiscal_year_view_post(self):
        """Verify that editing a fiscal year's name works."""
        year_to_edit = FiscalYear.objects.create(
            name="Initial Year Name",
            start_date="2027-01-01",
            end_date="2027-12-31"
        )
        
        edit_data = {
            'name': 'Updated Year Name',
            'start_date': '2027-01-01', # Dates cannot be changed if periods exist, but must be submitted
            'end_date': '2027-12-31'
        }
        
        response = self.client.post(reverse('inventory:edit_fiscal_year', kwargs={'pk': year_to_edit.pk}), edit_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))
        
        year_to_edit.refresh_from_db()
        self.assertEqual(year_to_edit.name, 'Updated Year Name')

    def test_delete_fiscal_year_view_post(self):
        """Verify that a fiscal year without transactions can be deleted."""
        year_to_delete = FiscalYear.objects.create(
            name="Year To Delete",
            start_date="2028-01-01",
            end_date="2028-12-31"
        )
        year_id = year_to_delete.pk
        
        response = self.client.post(reverse('inventory:delete_fiscal_year', kwargs={'pk': year_id}))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))
        
        with self.assertRaises(FiscalYear.DoesNotExist):
            FiscalYear.objects.get(pk=year_id)

    def test_change_period_status_view_post(self):
        """Verify changing a financial period's status works."""
        # Create a specific, closed period for this test to avoid side-effects
        closed_period = FinancialPeriod.objects.create(
            fiscal_year=self.fiscal_year,
            name="August 2025",
            start_date="2025-08-01",
            end_date="2025-08-31",
            status=FinancialPeriod.Status.CLOSED
        )

        # Now try to re-open it
        reopen_data = {
            'new_status': FinancialPeriod.Status.OPEN,
            'justification': 'Testing re-opening'
        }
        
        response = self.client.post(reverse('inventory:change_period_status', kwargs={'period_id': closed_period.id}), reopen_data)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('inventory:fiscal_year_list'))
        
        closed_period.refresh_from_db()
        self.assertEqual(closed_period.status, FinancialPeriod.Status.OPEN)
        self.assertTrue(PeriodClosingAuditLog.objects.filter(financial_period=closed_period, action_type=PeriodClosingAuditLog.ActionType.REOPEN).exists())

    # Cost Pool and Allocation Driver Tests
    def test_cost_pools_list_view_and_crud(self):
        """Verify the Cost Pools view loads and handles Create, Update, and Delete."""
        # 1. Test GET request
        response = self.client.get(reverse('inventory:cost_pools_list'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'inventory/cost_pools_list.html')

        # 2. Test POST to CREATE a new cost pool
        create_data = {
            'action': 'save',
            'name': 'New Test Pool',
            'gl_account': self.accounts['50201'].id # Maintenance Expense
        }
        # Use follow=True to get the final response after the redirect
        response = self.client.post(reverse('inventory:cost_pools_list'), create_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "created successfully") # Check for message text
        self.assertTrue(CostPool.objects.filter(name='New Test Pool').exists())

        # 3. Test POST to EDIT the created cost pool
        pool_to_edit = CostPool.objects.get(name='New Test Pool')
        edit_data = {
            'action': 'save',
            'pool_id': pool_to_edit.id,
            'name': 'Updated Test Pool Name',
            'gl_account': self.accounts['50203'].id # Factory Rent
        }
        response = self.client.post(reverse('inventory:cost_pools_list'), edit_data)
        self.assertEqual(response.status_code, 302)
        pool_to_edit.refresh_from_db()
        self.assertEqual(pool_to_edit.name, 'Updated Test Pool Name')
        self.assertEqual(pool_to_edit.gl_account.id, self.accounts['50203'].id)

        # 4. Test POST to DELETE the cost pool
        pool_id_to_delete = pool_to_edit.id
        delete_data = {
            'action': 'delete',
            'pool_id': pool_id_to_delete
        }
        response = self.client.post(reverse('inventory:cost_pools_list'), delete_data)
        self.assertEqual(response.status_code, 302)
        with self.assertRaises(CostPool.DoesNotExist):
            CostPool.objects.get(pk=pool_id_to_delete)
