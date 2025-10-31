// static/layout/js/purchasing_logic.js

/**
 * Initializes the logic for both Create and Edit Purchase Order forms.
 * It handles dynamic row addition, deletion, and line total calculations.
 * @param {HTMLElement} container The parent container of the form.
 */
function initPurchaseOrderFormLogic(container) {
    const form = container.querySelector('#createPurchaseOrderForm, #editPurchaseOrderForm');
    if (!form) return;

    if (form.dataset.poLogicInitialized) return;
    form.dataset.poLogicInitialized = 'true';

    console.log('%c[PurchaseOrderForm] Initializing new logic with allocation limits...', 'color: #8e44ad; font-weight: bold;');

    // --- Get Elements ---
    const itemsTbody = form.querySelector('#po-items-tbody');
    const addItemBtn = form.querySelector("#add-item-btn");
    const lcTbody = form.querySelector('#landed-costs-tbody');
    const addLcBtn = form.querySelector('#add-lc-btn');
    const allocationBadge = form.querySelector('#allocation-total-badge');
    
    // --- Get Data Islands ---
    const productsData = window.getDataFromIsland('products-data', container);
    const landedCostTypesData = window.getDataFromIsland('landed-cost-types-data', container);
    const initialItemsData = window.getDataFromIsland('po-items-data', container);
    const initialLcData = window.getDataFromIsland('po-landed-costs-data', container);

    if (!itemsTbody || !addItemBtn || !lcTbody || !addLcBtn || !productsData || !landedCostTypesData || !allocationBadge) {
        console.error('[PurchaseOrderForm] CRITICAL: Missing required elements for new logic. Halting.');
        return;
    }

    let itemRowCounter = 0;

    // --- Calculation Engine ---
    const updateAllTotals = () => {
        // 1. Calculate total estimated landed costs from its table
        let totalLandedCosts = 0;
        lcTbody.querySelectorAll('input[name="lc_estimated_amount"]').forEach(input => {
            totalLandedCosts += parseFloat(input.value) || 0;
        });

        // 2. Calculate total allocation percentage and update badge
        let totalAllocation = 0;
        itemsTbody.querySelectorAll('input[name="landed_cost_allocation_percentage"]').forEach(input => {
            totalAllocation += parseFloat(input.value) || 0;
        });

        if (allocationBadge) {
            allocationBadge.textContent = `إجمالي التوزيع: ${totalAllocation.toFixed(2)}%`;
            // Use a small tolerance for floating point comparisons
            if (Math.abs(totalAllocation - 100.0) < 0.01 && totalLandedCosts > 0) {
                allocationBadge.classList.remove('bg-secondary', 'bg-danger');
                allocationBadge.classList.add('bg-success');
            } else if (totalLandedCosts === 0 && totalAllocation === 0) {
                allocationBadge.classList.remove('bg-success', 'bg-danger');
                allocationBadge.classList.add('bg-secondary');
            } else {
                allocationBadge.classList.remove('bg-secondary', 'bg-success');
                allocationBadge.classList.add('bg-danger');
            }
        }

        // 3. Update each item row based on the new total
        itemsTbody.querySelectorAll('tr').forEach(row => {
            calculateRowTotals(row, totalLandedCosts);
        });
    };

    const calculateRowTotals = (row, totalLandedCosts) => {
        const qty = parseFloat(row.querySelector('input[name="quantity"]').value) || 0;
        const basePrice = parseFloat(row.querySelector('input[name="base_price_per_unit"]').value) || 0;
        const vatRate = parseFloat(row.querySelector('input[name="vat_rate"]').value) || 0;
        const whtRate = parseFloat(row.querySelector('input[name="withholding_tax_rate"]').value) || 0;
        const allocationPercent = parseFloat(row.querySelector('input[name="landed_cost_allocation_percentage"]').value) || 0;

        const baseAmount = qty * basePrice;
        const vatAmount = baseAmount * (vatRate / 100);
        const whtAmount = baseAmount * (whtRate / 100);
        
        const allocatedLandedCost = totalLandedCosts * (allocationPercent / 100);
        const totalEstimatedCost = baseAmount + vatAmount + allocatedLandedCost;
        const netPayable = baseAmount + vatAmount - whtAmount;

        row.querySelector('.line-total').textContent = totalEstimatedCost.toFixed(3);
        row.querySelector('.net-payable').textContent = netPayable.toFixed(3);
    };

    // --- Row Management ---
    const addItemRow = (item = {}) => {
        itemRowCounter++;
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ps-3 align-middle">
                <select name="product_id" class="form-select" data-row-id="${itemRowCounter}" required></select>
            </td>
            <td class="align-middle"><input type="number" step="any" name="quantity" class="form-control text-center" value="${item.quantity || ''}" required></td>
            <td class="align-middle"><input type="number" step="0.001" name="base_price_per_unit" class="form-control text-center" value="${item.base_price_per_unit || ''}" required></td>
            <td class="align-middle"><input type="number" step="any" name="vat_rate" class="form-control text-center" value="${item.vat_rate || '14.00'}" required></td>
            <td class="align-middle"><input type="number" step="any" name="withholding_tax_rate" class="form-control text-center" value="${item.withholding_tax_rate || '1.00'}"></td>
            <td class="align-middle"><input type="number" step="0.01" name="landed_cost_allocation_percentage" class="form-control text-center" value="${item.landed_cost_allocation_percentage || '0.00'}"></td>
            <td class="text-center fw-bold align-middle line-total">0.000</td>
            <td class="text-center fw-bold align-middle text-primary net-payable">0.000</td>
            <td class="text-center pe-3 align-middle">
                <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn"><i class="bi bi-trash"></i></button>
            </td>
        `;
        itemsTbody.appendChild(row);
        
        const newSelect = row.querySelector(`select[data-row-id="${itemRowCounter}"]`);
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

        row.addEventListener('input', (e) => {
            // Capping logic for allocation percentage
            if (e.target.name === 'landed_cost_allocation_percentage') {
                let currentVal = parseFloat(e.target.value) || 0;
                let otherTotal = 0;
                itemsTbody.querySelectorAll('input[name="landed_cost_allocation_percentage"]').forEach(input => {
                    if (input !== e.target) {
                        otherTotal += parseFloat(input.value) || 0;
                    }
                });

                if (currentVal < 0) {
                    e.target.value = '0.00';
                } else if (currentVal + otherTotal > 100) {
                    const newVal = 100 - otherTotal;
                    e.target.value = newVal.toFixed(2);
                }
            }
            updateAllTotals();
        });
        updateAllTotals();
    };

    const addLandedCostRow = (lcItem = {}) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="ps-3 align-middle">
                <select name="lc_cost_type_id" class="form-select">
                    <option value="">اختر النوع...</option>
                    ${landedCostTypesData.map(lct => `<option value="${lct.id}" ${lcItem.cost_type_id == lct.id ? 'selected' : ''}>${lct.name}</option>`).join('')}
                </select>
            </td>
            <td class="align-middle">
                <input type="number" step="0.001" name="lc_estimated_amount" class="form-control" value="${lcItem.estimated_amount || ''}">
            </td>
            <td class="text-center pe-3 align-middle">
                <button type="button" class="btn btn-sm btn-outline-danger remove-lc-btn"><i class="bi bi-trash"></i></button>
            </td>
        `;
        lcTbody.appendChild(row);
        row.addEventListener('input', updateAllTotals);
        updateAllTotals();
    };

    // --- Event Listeners ---
    addItemBtn.addEventListener('click', () => addItemRow());
    addLcBtn.addEventListener('click', () => addLandedCostRow());

    itemsTbody.addEventListener('click', function(e) {
        const removeBtn = e.target.closest('.remove-item-btn');
        if (removeBtn) {
            removeBtn.closest('tr').remove();
            updateAllTotals();
        }
    });

    lcTbody.addEventListener('click', function(e) {
        const removeBtn = e.target.closest('.remove-lc-btn');
        if (removeBtn) {
            removeBtn.closest('tr').remove();
            updateAllTotals();
        }
    });

    form.addEventListener('submit', function(e) {
        let totalLandedCosts = 0;
        lcTbody.querySelectorAll('input[name="lc_estimated_amount"]').forEach(input => {
            totalLandedCosts += parseFloat(input.value) || 0;
        });

        if (totalLandedCosts > 0) {
            let totalAllocation = 0;
            itemsTbody.querySelectorAll('input[name="landed_cost_allocation_percentage"]').forEach(input => {
                totalAllocation += parseFloat(input.value) || 0;
            });

            if (Math.abs(totalAllocation - 100.0) > 0.01) {
                e.preventDefault();
                alert(`يجب أن يكون مجموع نسب توزيع تكاليف الشحن 100%. المجموع الحالي هو: ${totalAllocation.toFixed(2)}%`);
            }
        }
    });

    // --- Initial Population (for Edit form) ---
    if (initialLcData && initialLcData.length > 0) {
        initialLcData.forEach(lcItem => addLandedCostRow(lcItem));
    }
    if (initialItemsData && initialItemsData.length > 0) {
        initialItemsData.forEach(item => addItemRow(item));
    } else {
        addItemRow(); // Add one empty row for create form
    }
    
    updateAllTotals(); // Final calculation on load
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
