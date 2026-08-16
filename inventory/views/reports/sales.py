# gipcco_project/inventory/views/reports/sales.py
import logging
from datetime import date
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.template.loader import render_to_string
from weasyprint import HTML
from ...services.reports import sales_reports
from ...services import excel_export_service

logger = logging.getLogger(__name__)

def sales_by_customer_report(request: HttpRequest) -> HttpResponse:
    """
    Generates and displays the 'Sales by Customer' report.
    """
    # Set default date range to the last 30 days
    default_start = (timezone.now() - timezone.timedelta(days=30)).date()
    default_end = timezone.now().date()

    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        # Handle invalid date format gracefully
        start_date = default_start
        end_date = default_end
        start_date_str = default_start.strftime('%Y-%m-%d')
        end_date_str = default_end.strftime('%Y-%m-%d')

    logger.info(f"Requesting 'Sales by Customer' report for period: {start_date} to {end_date}")

    report_payload = sales_reports.get_sales_by_customer_data(start_date, end_date)

    context = {
        'active_page': 'reports',
        'report_data': report_payload['data'],
        'grand_total': report_payload['grand_total'],
        'start_date': start_date_str,
        'end_date': end_date_str,
    }

    if 'export_pdf' in request.GET:
        logger.info("Exporting 'Sales by Customer' report to PDF.")
        html_string = render_to_string('inventory/reports/sales/sales_by_customer_pdf.html', context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Sales_by_Customer_{start_date_str}_to_{end_date_str}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    if 'export_excel' in request.GET:
        logger.info("Exporting 'Sales by Customer' report to Excel.")
        return excel_export_service.export_sales_by_customer_to_excel(
            report_data=report_payload['data'],
            grand_total=report_payload['grand_total'],
            start_date=start_date,
            end_date=end_date
        )

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/reports/sales/partials/sales_by_customer_content.html', context)

    return render(request, 'inventory/reports/sales/sales_by_customer.html', context)


def sales_by_product_report(request: HttpRequest) -> HttpResponse:
    """
    Generates and displays the 'Sales by Product' report.
    """
    default_start = (timezone.now() - timezone.timedelta(days=30)).date()
    default_end = timezone.now().date()

    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        start_date = default_start
        end_date = default_end
        start_date_str = default_start.strftime('%Y-%m-%d')
        end_date_str = default_end.strftime('%Y-%m-%d')

    logger.info(f"Requesting 'Sales by Product' report for period: {start_date} to {end_date}")

    report_payload = sales_reports.get_sales_by_product_data(start_date, end_date)

    context = {
        'active_page': 'reports',
        'report_data': report_payload['data'],
        'grand_total': report_payload['grand_total'],
        'start_date': start_date_str,
        'end_date': end_date_str,
    }

    if 'export_pdf' in request.GET:
        logger.info("Exporting 'Sales by Product' report to PDF.")
        html_string = render_to_string('inventory/reports/sales/sales_by_product_pdf.html', context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Sales_by_Product_{start_date_str}_to_{end_date_str}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    if 'export_excel' in request.GET:
        logger.info("Exporting 'Sales by Product' report to Excel.")
        return excel_export_service.export_sales_by_product_to_excel(
            report_data=report_payload['data'],
            grand_total=report_payload['grand_total'],
            start_date=start_date,
            end_date=end_date
        )

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/reports/sales/partials/sales_by_product_content.html', context)

    return render(request, 'inventory/reports/sales/sales_by_product.html', context)


def sales_order_backlog_report(request: HttpRequest) -> HttpResponse:
    """
    Generates and displays the 'Sales Order Backlog' report.
    """
    logger.info("Requesting 'Sales Order Backlog' report.")

    report_payload = sales_reports.get_sales_order_backlog_data()

    context = {
        'active_page': 'reports',
        'report_data': report_payload['data'],
    }

    if 'export_pdf' in request.GET:
        logger.info("Exporting 'Sales Order Backlog' report to PDF.")
        html_string = render_to_string('inventory/reports/sales/sales_order_backlog_pdf.html', context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Sales_Order_Backlog_{date.today()}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    if 'export_excel' in request.GET:
        logger.info("Exporting 'Sales Order Backlog' report to Excel.")
        return excel_export_service.export_sales_order_backlog_to_excel(
            report_data=report_payload['data']
        )

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/reports/sales/partials/sales_order_backlog_content.html', context)

    return render(request, 'inventory/reports/sales/sales_order_backlog.html', context)
