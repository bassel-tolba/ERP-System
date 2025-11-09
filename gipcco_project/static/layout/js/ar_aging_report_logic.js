// static/layout/js/ar_aging_report_logic.js

function initArAgingReportLogic(container) {
    const reportContainer = container.querySelector('#report-content');

    if (reportContainer && !reportContainer.dataset.listenerAttached) {
        reportContainer.dataset.listenerAttached = 'true'; // Prevent attaching multiple listeners
        
        reportContainer.addEventListener('click', async function(event) {
            const row = event.target.closest('.customer-row');
            if (!row) return;

            const customerId = row.dataset.customerId;
            // Important: Query for the detail row within the same container context
            const detailRow = reportContainer.querySelector(`#details-for-${customerId}`);
            if (!detailRow) return;
            
            const detailCell = detailRow.querySelector('td');

            // Toggle visibility
            const isVisible = !detailRow.classList.contains('d-none');
            if (isVisible) {
                detailRow.classList.add('d-none');
                detailCell.innerHTML = ''; // Clear content
                row.classList.remove('table-active');
                row.querySelector('i').classList.replace('bi-chevron-up', 'bi-chevron-down');
                return;
            }

            // Close any other open detail rows
            reportContainer.querySelectorAll('.detail-row:not(.d-none)').forEach(openRow => {
                openRow.classList.add('d-none');
                openRow.querySelector('td').innerHTML = '';
                const correspondingCustomerRow = reportContainer.querySelector(`.customer-row[data-customer-id="${openRow.id.replace('details-for-', '')}"]`);
                if (correspondingCustomerRow) {
                    correspondingCustomerRow.classList.remove('table-active');
                    correspondingCustomerRow.querySelector('i').classList.replace('bi-chevron-up', 'bi-chevron-down');
                }
            });

            // Show loading state
            row.classList.add('table-active');
            row.querySelector('i').classList.replace('bi-chevron-down', 'bi-chevron-up');
            detailRow.classList.remove('d-none');
            detailCell.innerHTML = `
                <div class="text-center p-3">
                    <div class="spinner-border spinner-border-sm" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <span class="ms-2">جاري تحميل التفاصيل...</span>
                </div>
            `;

            try {
                const asOfDate = document.getElementById('as_of_date').value;
                const url = `/reports/ar/aging/customer_detail/${customerId}/?as_of_date=${asOfDate}`;
                
                const response = await fetch(url, {
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });

                if (!response.ok) {
                    throw new Error('Failed to fetch details.');
                }

                const html = await response.text();
                detailCell.innerHTML = html;

            } catch (error) {
                console.error('Error fetching customer details:', error);
                detailCell.innerHTML = '<div class="text-center p-3 text-danger">فشل تحميل التفاصيل.</div>';
            }
        });
    }
}
