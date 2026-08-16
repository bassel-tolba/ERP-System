# gipcco_project/inventory/services/reports/sales_reports.py
import logging
from datetime import date
from decimal import Decimal
from django.db.models import Sum, Count, F, Q, Subquery, OuterRef, FloatField
from django.db.models.functions import Coalesce

from ...models import Customer, CustomerInvoice, Product, SalesOrderItem, SalesOrder, CustomerInvoiceItem, FinishedProductDispatch

logger = logging.getLogger(__name__)


def get_sales_by_customer_data(start_date: date, end_date: date):
    """
    Generates a summary of sales revenue broken down by each customer for a specific period.
    """
    logger.info(f"Generating 'Sales by Customer' report for period: {start_date} to {end_date}")

    sales_data = CustomerInvoice.objects.filter(
        invoice_date__range=(start_date, end_date),
        status__in=[
            CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT,
            CustomerInvoice.InvoiceStatus.PARTIALLY_PAID,
            CustomerInvoice.InvoiceStatus.PAID
        ]
    ).values(
        'customer__name'
    ).annotate(
        invoice_count=Count('id', distinct=True),
        total_sales=Sum('total_amount')
    ).order_by('-total_sales')

    report_data = list(sales_data)
    
    grand_total = sum(item['total_sales'] for item in report_data)

    logger.info(f"Successfully generated sales data for {len(report_data)} customers.")
    
    return {
        'data': report_data,
        'grand_total': grand_total,
        'start_date': start_date,
        'end_date': end_date
    }


def get_sales_by_product_data(start_date: date, end_date: date):
    """
    Generates a report ranking products by their sales performance over a specific period.
    """
    logger.info(f"Generating 'Sales by Product' report for period: {start_date} to {end_date}")

    # We'll aggregate from CustomerInvoiceItem and trace back to the product
    sales_data = CustomerInvoiceItem.objects.filter(
        invoice__invoice_date__range=(start_date, end_date),
        invoice__status__in=[
            CustomerInvoice.InvoiceStatus.AWAITING_PAYMENT,
            CustomerInvoice.InvoiceStatus.PARTIALLY_PAID,
            CustomerInvoice.InvoiceStatus.PAID
        ]
    ).values(
        'dispatch__sales_order_item__finished_product__batch__template__final_product__name',
        'dispatch__sales_order_item__finished_product__batch__template__final_product__unit'
    ).annotate(
        total_quantity_sold=Sum('dispatch__quantity'),
        total_revenue=Sum('amount')
    ).order_by('-total_revenue')

    # Clean up the keys for easier template access
    report_data = [
        {
            'product_name': item['dispatch__sales_order_item__finished_product__batch__template__final_product__name'],
            'unit': item['dispatch__sales_order_item__finished_product__batch__template__final_product__unit'],
            'total_quantity_sold': item['total_quantity_sold'],
            'total_revenue': item['total_revenue']
        }
        for item in sales_data
    ]

    grand_total_revenue = sum(item['total_revenue'] for item in report_data)

    logger.info(f"Successfully generated sales data for {len(report_data)} products.")

    return {
        'data': report_data,
        'grand_total': grand_total_revenue,
        'start_date': start_date,
        'end_date': end_date
    }


def get_sales_order_backlog_data():
    """
    Generates a report of all open sales order items that have not been fully shipped.
    """
    logger.info("Generating 'Sales Order Backlog' report.")

    # Subquery to calculate the total quantity dispatched for each sales order item
    dispatched_subquery = FinishedProductDispatch.objects.filter(
        sales_order_item=OuterRef('pk')
    ).values('sales_order_item').annotate(
        total_shipped=Sum('quantity')
    ).values('total_shipped')

    # Find all sales order items that are not fully fulfilled
    backlog_items = SalesOrderItem.objects.select_related(
        'sales_order__customer',
        'finished_product__batch__template__final_product'
    ).annotate(
        quantity_shipped=Coalesce(Subquery(dispatched_subquery, output_field=FloatField()), 0.0)
    ).annotate(
        quantity_backlog=F('quantity_ordered') - F('quantity_shipped')
    ).filter(
        quantity_backlog__gt=0.001,
        sales_order__status__in=[SalesOrder.Status.PENDING, SalesOrder.Status.PARTIALLY_SHIPPED]
    ).order_by('sales_order__order_date', 'sales_order__so_number')

    report_data = [
        {
            'so_number': item.sales_order.so_number,
            'order_date': item.sales_order.order_date,
            'customer_name': item.sales_order.customer.name,
            'product_name': item.finished_product.batch.template.final_product.name,
            'quantity_ordered': item.quantity_ordered,
            'quantity_shipped': item.quantity_shipped,
            'quantity_backlog': item.quantity_backlog,
            'unit': item.finished_product.batch.template.final_product.unit,
        }
        for item in backlog_items
    ]

    logger.info(f"Found {len(report_data)} backlogged sales order items.")

    return {
        'data': report_data
    }
