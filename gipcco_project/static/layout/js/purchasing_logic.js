// static/layout/js/purchasing_logic.js

/**
 * Initializes the logic for both Create and Edit Purchase Order forms.
 * It handles dynamic row addition, deletion, and line total calculations.
 * @param {HTMLElement} container The parent container of the form.
 */
function initPurchaseOrderFormLogic(container) {
    const form = container.querySelector('#createPurchaseOrderForm, #editPurchaseOrderForm');
    if (!form) return;

    // Re-initialization guard
    if (form.dataset.poLogicInitialized) return;
    form.dataset.poLogicInitialized = 'true';

    console.log('%c[PurchaseOrderForm] Initializing logic...', 'color: #8e44ad; font-weight: bold;');

    const tbody = form.querySelector('#po-items-tbody');
    const addItemBtn = form.querySelector("#add-item-btn");
    const productsData = window.getDataFromIsland('products-data', container);
    const initialItemsData = window.getDataFromIsland('po-items-data', container);

    if (!tbody || !addItemBtn || !productsData) {
        console.error('[PurchaseOrderForm] CRITICAL: Missing required elements (#po-items-tbody, #add-item-btn, or #products-data). Halting.');
        return;
    }

    let rowCounter = 0;

    const calculateTotal = (row) => {
        const qty = parseFloat(row.querySelector('input[name="quantity"]').value) || 0;
        const basePrice = parseFloat(row.querySelector('input[name="base_price_per_unit"]').value) || 0;
        const vatRate = parseFloat(row.querySelector('input[name="vat_rate"]').value) || 0;
        const whtRate = parseFloat(row.querySelector('input[name="withholding_tax_rate"]').value) || 0;

        const total = qty * (basePrice * (1 + vatRate / 100));
        const whtAmount = (qty * basePrice) * (whtRate / 100);
        const netPayable = total - whtAmount;

        row.querySelector('.line-total').textContent = total.toFixed(3);
        row.querySelector('.net-payable').textContent = netPayable.toFixed(3);
    };

    const addItemRow = (item = {}) => {
        rowCounter++;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ps-3">
                <select name="product_id" class="form-select" data-row-id="${rowCounter}" required></select>
            </td>
            <td><input type="number" step="any" name="quantity" class="form-control text-center" value="${item.quantity || ''}" required></td>
            <td><input type="number" step="0.001" name="base_price_per_unit" class="form-control text-center" value="${item.base_price_per_unit || ''}" required></td>
            <td><input type="number" step="any" name="vat_rate" class="form-control text-center" value="${item.vat_rate || '14.00'}" required></td>
            <td><input type="number" step="any" name="withholding_tax_rate" class="form-control text-center" value="${item.withholding_tax_rate || '1.00'}"></td>
            <td class="text-center fw-bold line-total">0.000</td>
            <td class="text-center fw-bold text-primary net-payable">0.000</td>
            <td class="text-center pe-3">
                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn"><i class="bi bi-trash"></i></button>
            </td>
        `;
        tbody.appendChild(row);
        
        const newSelect = row.querySelector(`select[data-row-id="${rowCounter}"]`);
        const tomselect = new TomSelect(newSelect, {
            options: productsData.map(p => ({ value: p.id, text: `${p.name} (${p.code})` })),
            placeholder: 'ابحث عن منتج...',
            create: false,
            rtl: true,
            dropdownParent: 'body'
        });

        if (item.product_id) {
            tomselect.setValue(item.product_id);
        }
        
        row.addEventListener('input', () => calculateTotal(row));
        calculateTotal(row);
    };

    tbody.addEventListener('click', function(e) {
        if (e.target.closest('.remove-item-btn')) {
            e.target.closest('tr').remove();
        }
    });

    addItemBtn.addEventListener('click', () => addItemRow());

    // Pre-populate with existing items on edit forms, or add one empty row for create forms
    if (initialItemsData && initialItemsData.length > 0) {
        initialItemsData.forEach(item => addItemRow(item));
    } else {
        addItemRow();
    }
}


/**
 * Initializes the logic for the Create Purchase Return page.
 * It handles fetching available receipts for a supplier and adding item rows.
 * @param {HTMLElement} container The parent container of the form.
 */
function initPurchaseReturnCreateLogic(container) {
    const form = container.querySelector('#createPurchaseReturnForm');
    if (!form) return;

    if (form.dataset.prLogicInitialized) return;
    form.dataset.prLogicInitialized = 'true';
    
    console.log('%c[PurchaseReturnCreate] Initializing logic...', 'color: #27ae60; font-weight: bold;');

    const supplierSelect = form.querySelector('#supplier');
    const addItemBtn = form.querySelector('#add-item-btn');
    const tbody = form.querySelector('#return-items-tbody');
    let rowCounter = 0;
    let receiptOptions = []; // Cache for fetched receipts

    const fetchReceipts = async () => {
        const supplierId = supplierSelect.value;
        if (!supplierId) {
            receiptOptions = [];
            return;
        }
        try {
            const url = window.appUrls.apiSupplierReceipts.replace('0', supplierId);
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to fetch receipts');
            const data = await response.json();
            receiptOptions = data.receipts.map(r => ({
                value: r.id,
                text: `[${r.release_date}] ${r.product_name} (رقم فحص: ${r.qc_no}) - متاح: ${r.quantity_available}`
            }));
        } catch (error) {
            console.error("Error fetching receipts:", error);
            receiptOptions = [];
        }
    };

    const addItemRow = () => {
        rowCounter++;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ps-3">
                <select name="receipt_id" class="form-select" data-row-id="${rowCounter}" required></select>
            </td>
            <td><input type="number" step="any" name="quantity_returned" class="form-control text-center" required></td>
            <td class="text-center pe-3">
                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn"><i class="bi bi-trash"></i></button>
            </td>
        `;
        tbody.appendChild(row);
        
        const newSelect = row.querySelector(`select[data-row-id="${rowCounter}"]`);
        new TomSelect(newSelect, {
            options: receiptOptions,
            placeholder: 'ابحث عن إيصال استلام...',
            create: false,
            rtl: true,
            dropdownParent: 'body'
        });
    };

    supplierSelect.addEventListener('change', async () => {
        await fetchReceipts();
        // Clear table and add a new row with updated options
        tbody.innerHTML = '';
        addItemRow();
    });

    tbody.addEventListener('click', function(e) {
        if (e.target.closest('.remove-item-btn')) {
            e.target.closest('tr').remove();
        }
    });

    addItemBtn.addEventListener('click', addItemRow);

    // Initial setup
    if (tbody.rows.length === 0) {
        addItemRow();
    }
}
