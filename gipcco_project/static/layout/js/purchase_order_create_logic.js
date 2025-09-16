// static/layout/js/purchase_order_create_logic.js

function initPurchaseOrderCreateLogic(container) {
    // Gatekeeper check: Find a unique element for this page.
    const addItemBtn = container.querySelector("#add-item-btn");

    // If the button doesn't exist, this isn't the PO create page, so do nothing.
    if (addItemBtn) {
        
        // Re-initialization guard: Only run the logic once.
        if (!addItemBtn.dataset.poLogicInitialized) {
            console.log('%c[PurchaseOrderCreate] Initializing logic...', 'color: #8e44ad; font-weight: bold;');
            addItemBtn.dataset.poLogicInitialized = 'true';

            const tbody = container.querySelector('#po-items-tbody');
            const productsDataElement = container.querySelector('#products-data');

            if (!tbody || !productsDataElement) {
                console.error('[PurchaseOrderCreate] CRITICAL: Missing #po-items-tbody or #products-data. Halting.');
                return;
            }

            const productsData = JSON.parse(productsDataElement.textContent);
            console.log(`[PurchaseOrderCreate] Successfully loaded ${productsData.length} products from JSON data island.`);
            
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

            const addItemRow = () => {
                console.log('[PurchaseOrderCreate] addItemRow() called.');
                rowCounter++;
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td class="ps-3">
                        <select name="product_id" class="form-select" data-row-id="${rowCounter}" required></select>
                    </td>
                    <td><input type="number" step="any" name="quantity" class="form-control text-center" required></td>
                    <td><input type="number" step="0.001" name="base_price_per_unit" class="form-control text-center" required></td>
                    <td><input type="number" step="any" name="vat_rate" class="form-control text-center" value="14.00" required></td>
                    <td><input type="number" step="any" name="withholding_tax_rate" class="form-control text-center" value="1.00"></td>
                    <td class="text-center fw-bold line-total">0.000</td>
                    <td class="text-center fw-bold text-primary net-payable">0.000</td>
                    <td class="text-center pe-3">
                        <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn"><i class="bi bi-trash"></i></button>
                    </td>
                `;
                tbody.appendChild(row);
                
                const newSelect = row.querySelector(`select[data-row-id="${rowCounter}"]`);
                
                // Initialize TomSelect with RTL and dropdownParent fixes
                new TomSelect(newSelect, {
                    options: productsData.map(p => ({ value: p.id, text: `${p.name} (${p.code})` })),
                    placeholder: 'ابحث عن منتج...',
                    create: false,
                    rtl: true,
                    // ====== THIS IS THE FIX ======
                    dropdownParent: 'body'
                });
                
                row.addEventListener('input', () => calculateTotal(row));
                calculateTotal(row); // Call initially to set values
            };

            tbody.addEventListener('click', function(e) {
                if (e.target.closest('.remove-item-btn')) {
                    e.target.closest('tr').remove();
                }
            });

            console.log('[PurchaseOrderCreate] Attaching event listener to Add Item button.');
            addItemBtn.addEventListener('click', addItemRow);
            
            if (tbody.rows.length === 0) {
                addItemRow();
            }
        }
    }
}