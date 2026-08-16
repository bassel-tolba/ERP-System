// gipcco_project/static/layout/js/inventory_counts_logic.js

function initInventoryCountsLogic(container = document) {
    console.log("--- [GIPCCO DEBUG] ---: initInventoryCountsLogic: Initializing logic on container:", container);

    const allocationContent = container.querySelector('#variance-allocation-content');
    if (!allocationContent) {
        console.log("--- [GIPCCO DEBUG] ---: No variance allocation content found. Exiting.");
        return;
    }
    console.log("--- [GIPCCO DEBUG] ---: Found variance allocation content. Proceeding.");

    const finalAllocations = {}; // Stores user's choices for final submission

    // --- 1. Modal Population ---
    allocationContent.addEventListener('show.bs.modal', async function (event) {
        console.log("--- [GIPCCO DEBUG] ---: Event 'show.bs.modal' triggered.");
        const modal = event.target;
        if (!modal.id.startsWith('allocationModal_')) return;

        const button = event.relatedTarget;
        const productId = button.dataset.productId;
        const productType = button.dataset.productType;
        const variance = parseFloat(button.dataset.variance);
        const itemId = button.dataset.itemId;
        
        // --- FIX: Store the product ID on the modal itself for later access ---
        modal.dataset.productId = productId;

        console.log(`--- [GIPCCO DEBUG] ---: MODAL OPENING. Item ID: ${itemId}, Product ID: ${productId}, Product Type: ${productType}.`);
        console.log(`--- [GIPCCO DEBUG] ---: TOTAL VARIANCE TO ALLOCATE: ${variance}`);
        
        const modalBody = modal.querySelector('.allocation-details');
        modalBody.innerHTML = `<div class="text-center"><div class="spinner-border" role="status"><span class="visually-hidden">تحميل...</span></div></div>`;

        try {
            const apiUrl = `/api/product/${productId}/stock_sources/`;
            console.log(`--- [GIPCCO DEBUG] ---: Fetching stock sources from: ${apiUrl}`);
            const response = await fetch(apiUrl);
            const data = await response.json();
            console.log("--- [GIPCCO DEBUG] ---: API Response Received:", data);
            
            let contentHtml = `
                <p class="fs-5">إجمالي الفرق للتخصيص: <strong class="variance-total text-${variance < 0 ? 'danger' : 'success'}">${variance.toFixed(2)}</strong></p>
                <input type="hidden" class="item-id" value="${itemId}">
                <div class="form-check form-switch my-2">
                    <input class="form-check-input" type="checkbox" role="switch" id="includeQuarantinedToggle" checked>
                    <label class="form-check-label" for="includeQuarantinedToggle">إظهار الكميات تحت الفحص</label>
                </div>
                <div class="table-responsive" style="max-height: 300px;">
                    <table class="table table-sm">
                        <thead><tr><th>المصدر</th><th>التاريخ</th><th>الحالة</th><th>الكمية المتبقية</th><th style="width: 150px;">كمية التسوية</th></tr></thead>
                        <tbody>`;

            if (data.sources && data.sources.length > 0) {
                data.sources.forEach(source => {
                    const isQuarantined = source.status === 'quarantined';
                    const statusBadge = `<span class="badge bg-${isQuarantined ? 'warning' : 'success'}">${source.status_display}</span>`;
                    contentHtml += `
                        <tr data-status="${source.status}">
                            <td>${source.identifier}</td>
                            <td>${source.date}</td>
                            <td>${statusBadge}</td>
                            <td>${source.remaining_quantity.toFixed(2)}</td>
                            <td><input type="number" class="form-control form-control-sm allocation-input" data-source-type="${source.type}" data-source-id="${source.id}" data-remaining="${source.remaining_quantity}" step="any"></td>
                        </tr>`;
                });
            } else {
                contentHtml += '<tr><td colspan="5" class="text-center">لا توجد مصادر مخزون متاحة.</td></tr>';
            }

            contentHtml += `</tbody></table></div>
                <div class="row mt-3">
                    <div class="col-md-6"><label class="form-label">سبب التسوية</label><select class="form-select form-select-sm reason-code"></select></div>
                    <div class="col-md-6"><label class="form-label">ملاحظات</label><input type="text" class="form-control form-control-sm notes"></div>
                </div>
                <div class="d-flex justify-content-between mt-2">
                    <span>الإجمالي المخصص: <strong class="total-allocated">0.00</strong></span>
                    <span class="text-danger allocation-warning"></span>
                </div>`;
            
            console.log("--- [GIPCCO DEBUG] ---: Generated Modal HTML. Injecting into modal body.");
            modalBody.innerHTML = contentHtml;

            const reasonCodes = window.getDataFromIsland('reasonCodesData');
            const reasonSelect = modal.querySelector('.reason-code');
            if (reasonCodes && reasonSelect) {
                console.log("--- [GIPCCO DEBUG] ---: Populating reason codes dropdown.");
                reasonCodes.forEach(code => {
                    reasonSelect.innerHTML += `<option value="${code[0]}">${code[1]}</option>`;
                });
            }

            if (productType === 'منتج نهائي' && variance < 0) {
                console.log("--- [GIPCCO DEBUG] ---: Finished good shortage detected. Adding auto-distribute button.");
                const footer = modal.querySelector('.modal-footer');
                const existingBtn = footer.querySelector('.auto-distribute-btn');
                if (existingBtn) existingBtn.remove();
                
                const autoButton = document.createElement('button');
                autoButton.type = 'button';
                autoButton.className = 'btn btn-info me-auto auto-distribute-btn';
                autoButton.textContent = 'توزيع تلقائي للعجز';
                footer.prepend(autoButton);
            }

        } catch (error) {
            console.error("--- [GIPCCO DEBUG] ---: Failed to fetch stock sources:", error);
            modalBody.innerHTML = '<p class="text-danger">فشل تحميل مصادر المخزون. يرجى المحاولة مرة أخرى.</p>';
        }
    });

    // --- 2. Modal Actions ---
    allocationContent.addEventListener('click', async function(event) { // --- ADDED async HERE ---
        const modal = event.target.closest('.modal');
        if (!modal) return;

        if (event.target.classList.contains('save-allocation-btn')) {
            console.log("--- [GIPCCO DEBUG] ---: 'Save Allocation' button clicked.");
            const itemId = modal.querySelector('.item-id').value;
            const variance = parseFloat(modal.querySelector('.variance-total').textContent);
            const totalAllocated = parseFloat(modal.querySelector('.total-allocated').textContent);

            console.log(`--- [GIPCCO DEBUG] ---: SAVE VALIDATION:`);
            console.log(`--- [GIPCCO DEBUG] ---:   > Required Total (Variance): ${variance}`);
            console.log(`--- [GIPCCO DEBUG] ---:   > Actual Total Allocated:    ${totalAllocated}`);
            console.log(`--- [GIPCCO DEBUG] ---:   > Checking if Math.abs(${totalAllocated} - ${variance}) > 0.01`);


            if (Math.abs(totalAllocated - variance) > 0.01) {
                console.warn("--- [GIPCCO DEBUG] ---: VALIDATION FAILED: Allocated amount must equal variance.");
                modal.querySelector('.allocation-warning').textContent = 'يجب أن يساوي المبلغ المخصص الفرق.';
                return;
            }
            console.log("--- [GIPCCO DEBUG] ---: VALIDATION PASSED.");

            const allocations = [];
            modal.querySelectorAll('.allocation-input').forEach(input => {
                if (input.value && parseFloat(input.value) !== 0) {
                    allocations.push({
                        source_type: input.dataset.sourceType,
                        source_id: input.dataset.sourceId,
                        quantity: input.value
                    });
                }
            });

            finalAllocations[itemId] = {
                type: 'manual',
                allocations: allocations,
                reason: modal.querySelector('.reason-code').value,
                notes: modal.querySelector('.notes').value
            };
            
            console.log(`--- [GIPCCO DEBUG] ---: Stored manual allocation for item ${itemId}:`, finalAllocations[itemId]);
            updateStatusBadge(itemId, 'تم التخصيص', 'success');
            bootstrap.Modal.getInstance(modal).hide();
        }

        if (event.target.classList.contains('auto-distribute-btn')) {
            console.log("--- [GIPCCO DEBUG] ---: 'Auto-Distribute' button clicked. Opening selection modal.");
            event.preventDefault(); // Prevent any default action
            
            const mainModal = event.target.closest('.modal');
            // --- FIX: Read the product ID from the modal's dataset ---
            const productId = mainModal.dataset.productId;

            const autoDistributeModalEl = document.getElementById('autoDistributeModal');
            const autoDistributeModal = new bootstrap.Modal(autoDistributeModalEl);
            const batchListContainer = autoDistributeModalEl.querySelector('#autoDistributeBatchList');
            
            batchListContainer.innerHTML = `<div class="text-center"><div class="spinner-border" role="status"></div></div>`;
            autoDistributeModal.show();

            // Fetch sources and populate the new modal
            try {
                const response = await fetch(`/api/product/${productId}/stock_sources/`);
                const data = await response.json();
                
                let tableHtml = `<table class="table table-sm"><thead><tr><th><input type="checkbox" class="form-check-input" id="selectAllBatches"></th><th>المصدر</th><th>التاريخ</th><th>الحالة</th><th>الكمية المتبقية</th></tr></thead><tbody>`;
                if (data.sources && data.sources.length > 0) {
                    data.sources.forEach(source => {
                        if (source.type === 'receipt') { // Only show finished good receipts
                            const isQuarantined = source.status === 'quarantined';
                            const statusBadge = `<span class="badge bg-${isQuarantined ? 'warning' : 'success'}">${source.status_display}</span>`;
                            tableHtml += `
                                <tr>
                                    <td><input type="checkbox" class="form-check-input batch-select-check" value="${source.id}"></td>
                                    <td>${source.identifier}</td>
                                    <td>${source.date}</td>
                                    <td>${statusBadge}</td>
                                    <td>${source.remaining_quantity.toFixed(2)}</td>
                                </tr>`;
                        }
                    });
                } else {
                    tableHtml += `<tr><td colspan="5" class="text-center">لا توجد دفعات متاحة.</td></tr>`;
                }
                tableHtml += `</tbody></table>`;
                batchListContainer.innerHTML = tableHtml;

                // Add event listener for the "Select All" checkbox
                autoDistributeModalEl.querySelector('#selectAllBatches').addEventListener('change', function(e) {
                    autoDistributeModalEl.querySelectorAll('.batch-select-check').forEach(checkbox => {
                        checkbox.checked = e.target.checked;
                    });
                });

                // Add event listener for the final confirmation button
                autoDistributeModalEl.querySelector('#confirmAutoDistributionBtn').addEventListener('click', function() {
                    const selectedIds = Array.from(autoDistributeModalEl.querySelectorAll('.batch-select-check:checked')).map(cb => parseInt(cb.value));
                    
                    if (selectedIds.length === 0) {
                        // Optionally, show an error message
                        console.warn("--- [GIPCCO DEBUG] ---: No batches selected for auto-distribution.");
                        return;
                    }

                    const itemId = mainModal.querySelector('.item-id').value;
                    finalAllocations[itemId] = {
                        type: 'auto_selected',
                        reason: mainModal.querySelector('.reason-code').value,
                        notes: mainModal.querySelector('.notes').value,
                        receipt_ids: selectedIds // --- NEW: Add the selected IDs ---
                    };
                    
                    console.log(`--- [GIPCCO DEBUG] ---: Stored 'auto_selected' allocation for item ${itemId}:`, finalAllocations[itemId]);
                    updateStatusBadge(itemId, `توزيع تلقائي (${selectedIds.length} دفعة)`, 'info');
                    
                    // Hide both modals
                    autoDistributeModal.hide();
                    bootstrap.Modal.getInstance(mainModal).hide();
                });

            } catch (error) {
                console.error("--- [GIPCCO DEBUG] ---: Failed to populate auto-distribute modal:", error);
                batchListContainer.innerHTML = `<p class="text-danger">فشل تحميل الدفعات.</p>`;
            }
        }
    });

    // --- 3. Real-time Calculation & Filtering ---
    allocationContent.addEventListener('input', function(event) {
        const modal = event.target.closest('.modal');
        if (!modal) return;

        // --- Filtering Logic ---
        if (event.target.id === 'includeQuarantinedToggle') {
            console.log(`--- [GIPCCO DEBUG] ---: Quarantined toggle changed. Is checked: ${event.target.checked}`);
            const rows = modal.querySelectorAll('tbody tr[data-status]');
            rows.forEach(row => {
                if (row.dataset.status === 'quarantined') {
                    row.style.display = event.target.checked ? '' : 'none';
                }
            });
            return; // Stop further processing for this event
        }

        // --- Calculation Logic ---
        if (event.target.classList.contains('allocation-input')) {
            const variance = parseFloat(modal.querySelector('.variance-total').textContent);
            const currentInput = event.target;
            const currentValue = parseFloat(currentInput.value);
            console.log(`--- [GIPCCO DEBUG] ---: INPUT EVENT: User typed '${currentInput.value}' into an allocation field.`);

            // Enforce the correct sign based on the variance type (overage/shortage)
            if (!isNaN(currentValue) && currentValue !== 0) {
                if (variance > 0 && currentValue < 0) {
                    // For overages, the allocation must be positive
                    currentInput.value = Math.abs(currentValue);
                    console.log(`--- [GIPCCO DEBUG] ---: Corrected input to positive for overage: ${currentInput.value}`);
                } else if (variance < 0 && currentValue > 0) {
                    // For shortages, the allocation must be negative
                    currentInput.value = -Math.abs(currentValue);
                    console.log(`--- [GIPCCO DEBUG] ---: Corrected input to negative for shortage: ${currentInput.value}`);
                }
            }

            const inputs = modal.querySelectorAll('.allocation-input');
            let totalAllocated = 0;
            inputs.forEach(input => {
                totalAllocated += parseFloat(input.value || 0);
            });
            modal.querySelector('.total-allocated').textContent = totalAllocated.toFixed(2);
            console.log(`--- [GIPCCO DEBUG] ---: Recalculated running total. New total: ${totalAllocated.toFixed(2)}`);
            modal.querySelector('.allocation-warning').textContent = '';
        }
    });

    // --- 4. Form Submission ---
    const allocationForm = container.querySelector('#allocationForm');
    if (allocationForm) {
        allocationForm.addEventListener('submit', function(event) {
            console.log("--- [GIPCCO DEBUG] ---: Allocation form submitted.");
            event.preventDefault();
            const hiddenInput = document.createElement('input');
            hiddenInput.type = 'hidden';
            hiddenInput.name = 'final_allocations';
            hiddenInput.value = JSON.stringify(finalAllocations);
            console.log("--- [GIPCCO DEBUG] ---: Submitting with final allocations JSON:", hiddenInput.value);
            this.appendChild(hiddenInput);
            this.submit();
        });
    }

    // --- 5. Helper Functions ---
    function updateStatusBadge(itemId, text, color) {
        console.log(`--- [GIPCCO DEBUG] ---: updateStatusBadge: Updating item ${itemId} to status '${text}' with color '${color}'.`);
        const row = allocationContent.querySelector(`tr[data-item-id="${itemId}"]`);
        if (row) {
            const statusCell = row.querySelector('.allocation-status');
            statusCell.innerHTML = `<span class="badge bg-${color}">${text}</span>`;
            const allocateBtn = row.querySelector('.allocate-btn');
            allocateBtn.classList.remove('btn-primary');
            allocateBtn.classList.add('btn-secondary');
            allocateBtn.textContent = 'تعديل التخصيص';
        }
        checkIfAllAllocated();
    }

    function checkIfAllAllocated() {
        const allRows = allocationContent.querySelectorAll('tbody tr[data-item-id]');
        const allocatedCount = Object.keys(finalAllocations).length;
        console.log(`--- [GIPCCO DEBUG] ---: checkIfAllAllocated: ${allocatedCount} of ${allRows.length} items are allocated.`);
        if (allRows.length > 0 && allRows.length === allocatedCount) {
            console.log("--- [GIPCCO DEBUG] ---: All items allocated. Enabling Post button.");
            container.querySelector('#postAdjustmentsBtn').disabled = false;
        } else {
            container.querySelector('#postAdjustmentsBtn').disabled = true;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log("--- [GIPCCO DEBUG] ---: DOMContentLoaded: Running initInventoryCountsLogic for initial page load.");
    initInventoryCountsLogic();
});
if (window.pageInitializers) {
    console.log("--- [GIPCCO DEBUG] ---: Attaching initInventoryCountsLogic to dynamic content loader.");
    window.pageInitializers['#variance-allocation-content'] = initInventoryCountsLogic;
}
