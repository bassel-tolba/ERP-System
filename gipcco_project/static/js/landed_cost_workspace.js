// gipcco_project/static/js/landed_cost_workspace.js

function initLandedCostWorkspace(container) {
    const workspace = container.querySelector('#landed-cost-workspace');
    if (!workspace || workspace.dataset.initialized) {
        return;
    }
    workspace.dataset.initialized = 'true';

    console.log('%c[LandedCost] Initializing workspace logic...', 'color: #f39c12; font-weight: bold;');

    const invoicesContainer = workspace.querySelector('#invoices-container');
    const receiptsContainer = workspace.querySelector('#receipts-container');
    const allocateBtn = workspace.querySelector('#allocate-btn');
    const totalInvoicesSelected = workspace.querySelector('#total-invoices-selected');
    const totalReceiptsSelected = workspace.querySelector('#total-receipts-selected');

    const INVOICES_URL = window.appUrls.api_get_unallocated_landed_cost_invoices;
    const RECEIPTS_URL = window.appUrls.api_get_receipts_for_allocation;

    const fetchData = async (url, containerElement) => {
        try {
            containerElement.innerHTML = '<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">Loading...</span></div></div>';
            const response = await fetch(url);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error(`Error fetching data from ${url}:`, error);
            containerElement.innerHTML = '<div class="alert alert-danger">Failed to load data. Please try again.</div>';
            return null;
        }
    };

    const renderInvoices = (data) => {
        if (!data || !data.invoices || data.invoices.length === 0) {
            invoicesContainer.innerHTML = '<p class="text-muted text-center">No landed cost invoices are awaiting allocation.</p>';
            return;
        }
        const table = `
            <table class="table table-sm table-hover">
                <thead>
                    <tr>
                        <th><input type="checkbox" class="form-check-input" id="select-all-invoices"></th>
                        <th>Invoice #</th>
                        <th>Vendor</th>
                        <th>Date</th>
                        <th class="text-end">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.invoices.map(inv => `
                        <tr>
                            <td><input type="checkbox" class="form-check-input invoice-checkbox" name="invoice_ids" value="${inv.id}" data-amount="${inv.total_amount}"></td>
                            <td>${inv.invoice_number}</td>
                            <td>${inv.vendor_name}</td>
                            <td>${inv.invoice_date}</td>
                            <td class="text-end">${inv.total_amount}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        invoicesContainer.innerHTML = table;
    };

    const renderReceipts = (data) => {
        if (!data || !data.receipts || data.receipts.length === 0) {
            receiptsContainer.innerHTML = '<p class="text-muted text-center">No available receipts for allocation.</p>';
            return;
        }
        const table = `
            <table class="table table-sm table-hover">
                <thead>
                    <tr>
                        <th><input type="checkbox" class="form-check-input" id="select-all-receipts"></th>
                        <th>Date</th>
                        <th>Product</th>
                        <th>Supplier</th>
                        <th class="text-end">Value</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.receipts.map(r => `
                        <tr>
                            <td><input type="checkbox" class="form-check-input receipt-checkbox" name="receipt_ids" value="${r.id}" data-value="${r.total_value}"></td>
                            <td>${r.release_timestamp}</td>
                            <td>${r.product_name}</td>
                            <td>${r.supplier_name}</td>
                            <td class="text-end">${r.total_value}</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        receiptsContainer.innerHTML = table;
    };

    const updateTotalsAndButton = () => {
        const selectedInvoices = invoicesContainer.querySelectorAll('.invoice-checkbox:checked');
        const selectedReceipts = receiptsContainer.querySelectorAll('.receipt-checkbox:checked');

        let totalInvoiceAmount = 0;
        selectedInvoices.forEach(inv => {
            totalInvoiceAmount += parseFloat(inv.dataset.amount);
        });

        let totalReceiptValue = 0;
        selectedReceipts.forEach(rec => {
            totalReceiptValue += parseFloat(rec.dataset.value);
        });

        totalInvoicesSelected.textContent = `${totalInvoiceAmount.toFixed(3)} (${selectedInvoices.length} invoices)`;
        totalReceiptsSelected.textContent = `${totalReceiptValue.toFixed(3)} (${selectedReceipts.length} receipts)`;

        if (selectedInvoices.length > 0 && selectedReceipts.length > 0) {
            allocateBtn.disabled = false;
        } else {
            allocateBtn.disabled = true;
        }
    };

    const setupEventListeners = () => {
        workspace.addEventListener('change', (e) => {
            if (e.target.matches('.invoice-checkbox, .receipt-checkbox')) {
                updateTotalsAndButton();
            }
            if (e.target.id === 'select-all-invoices') {
                invoicesContainer.querySelectorAll('.invoice-checkbox').forEach(cb => {
                    cb.checked = e.target.checked;
                });
                updateTotalsAndButton();
            }
            if (e.target.id === 'select-all-receipts') {
                receiptsContainer.querySelectorAll('.receipt-checkbox').forEach(cb => {
                    cb.checked = e.target.checked;
                });
                updateTotalsAndButton();
            }
        });
    };

    const loadData = async () => {
        const invoicesData = await fetchData(INVOICES_URL, invoicesContainer);
        const receiptsData = await fetchData(RECEIPTS_URL, receiptsContainer);
        renderInvoices(invoicesData);
        renderReceipts(receiptsData);
        setupEventListeners();
    };

    loadData();
}
