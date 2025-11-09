# gipcco_project/inventory/views/reports/ar.py
import logging
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.template.loader import render_to_string
from ...services.reports import ar_reports
from ...services import excel_export_service
from ...models import Customer
from weasyprint import HTML
from datetime import date

logger = logging.getLogger(__name__)

def ar_aging_report(request: HttpRequest) -> HttpResponse:
    as_of_date_str = request.GET.get('as_of_date', timezone.now().strftime('%Y-%m-%d'))

    # Clean up the date string to handle malformed URLs where 'export_pdf' might be appended with '?' instead of '&'
    if '?' in as_of_date_str:
        as_of_date_str = as_of_date_str.split('?')[0]

    logger.info(f"AR Aging Report: Generating report for date: {as_of_date_str}")
    
    report_payload = ar_reports.get_ar_aging_data(as_of_date=as_of_date_str)
    context = {
        'active_page': 'reports',
        'report_data': report_payload['data'],
        'totals': report_payload['totals'],
        'as_of_date': as_of_date_str,
    }

    if 'export_pdf' in request.GET:
        logger.info("AR Aging Report: Exporting to PDF.")
        html_string = render_to_string('inventory/reports/ar/ar_aging_pdf.html', context)
        
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        # --- CHANGE HERE: Hardcoded Arabic filename ---
        filename = f"تقرير_الذمم_المدينة_{as_of_date_str}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    if 'export_excel' in request.GET:
        logger.info("AR Aging Report: Exporting to Excel.")
        return excel_export_service.export_ar_aging_to_excel(
            report_data=report_payload['data'],
            totals=report_payload['totals'],
            as_of_date=as_of_date_str
        )

    if 'X-Partial-Request' in request.headers:
        return render(request, 'inventory/reports/ar/partials/aging_content.html', context)
        
    return render(request, 'inventory/reports/ar/aging.html', context)



def ar_customer_detail_api(request: HttpRequest, customer_id: int) -> HttpResponse:
    """
    API view to return the detailed HTML for a single customer's aging report,
    with an option to export as a PDF.
    """
    as_of_date_str = request.GET.get('as_of_date', timezone.now().strftime('%Y-%m-%d'))
    
    details = ar_reports.get_customer_ar_details(
        customer_id=customer_id,
        as_of_date=as_of_date_str
    )
    
    if not details:
        return HttpResponse("Customer details not found.", status=404)

    context = {
        'details': details,
        'customer_id': customer_id,
        'as_of_date': as_of_date_str,
    }

    if 'export_pdf' in request.GET:
        logger.info(f"Exporting AR customer detail report to PDF for customer_id: {customer_id}")
        html_string = render_to_string('inventory/reports/ar/ar_customer_detail_pdf.html', context)
        
        html = HTML(string=html_string, base_url=request.build_absolute_uri())
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        customer_name = details.get('customer').name.replace(" ", "_")
        filename = f"AR_Detail_{customer_name}_{as_of_date_str}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    
    return render(request, 'inventory/reports/ar/partials/_customer_aging_detail.html', context)


def customer_statement_report(request: HttpRequest) -> HttpResponse:
    """
    Generates a Customer Statement report, showing all transactions for a
    selected customer over a given period.
    """
    customer_id = request.GET.get('customer')
    # Use timezone.now() for defaults
    default_start = (timezone.now() - timezone.timedelta(days=30)).date()
    default_end = timezone.now().date()

    start_date_str = request.GET.get('start_date', default_start.strftime('%Y-%m-%d'))
    end_date_str = request.GET.get('end_date', default_end.strftime('%Y-%m-%d'))

    # Convert to date objects for the service
    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        # Handle invalid date format gracefully
        start_date = default_start
        end_date = default_end
        start_date_str = default_start.strftime('%Y-%m-%d')
        end_date_str = default_end.strftime('%Y-%m-%d')


    customers = Customer.objects.all().order_by('name')
    context = {
        'active_page': 'reports',
        'customers': customers,
        'start_date': start_date_str,
        'end_date': end_date_str,
        'customer': None, # Ensure customer is in context
        'transactions': [],
    }

    if customer_id:
        report_payload = ar_reports.get_customer_statement_data(
            customer_id=int(customer_id),
            start_date=start_date,
            end_date=end_date
        )
        if report_payload:
            context.update(report_payload)

        if 'export_pdf' in request.GET:
            logger.info(f"Exporting customer statement to PDF for customer_id: {customer_id}")
            html_string = render_to_string('inventory/reports/ar/customer_statement_pdf.html', context)
            
            html = HTML(string=html_string, base_url=request.build_absolute_uri())
            pdf = html.write_pdf()

            response = HttpResponse(pdf, content_type='application/pdf')
            customer_name = report_payload.get('customer').name.replace(" ", "_")
            filename = f"Statement_{customer_name}_{start_date_str}_to_{end_date_str}.pdf"
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            return response

        if 'export_excel' in request.GET:
            logger.info(f"Exporting customer statement to Excel for customer_id: {customer_id}")
            return excel_export_service.export_customer_statement_to_excel(
                customer=report_payload['customer'],
                start_date=start_date,
                end_date=end_date,
                opening_balance=report_payload['opening_balance'],
                transactions=report_payload['transactions'],
                closing_balance=report_payload['closing_balance']
            )

    return render(request, 'inventory/reports/ar/customer_statement.html', context)
