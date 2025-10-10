// static/layout/js/financials_logic.js

function initSupplierInvoiceListLogic(container) {
  // Logic for the supplier invoice list page, if any is needed in the future.
  // For now, it's a simple page.
}

function initCustomerInvoiceListLogic(container) {
  // Logic for the customer invoice list page.
}

function initCreateSupplierInvoiceLogic(container) {
  const supplierSelect = container.querySelector("#supplier");
  const itemsTableBody = container.querySelector("#items-table-body");
  const totalAmountSpan = container.querySelector("#total-amount");
  const noItemsRow = container.querySelector("#no-items-row");
  const loadingSpinner = container.querySelector("#items-loading");
  const sourceTypeInput = container.querySelector("#source_type");
  const tabs = container.querySelectorAll('#invoice-source-tabs .nav-link');
  const selectAllCheckbox = container.querySelector('#select-all-items');

  if (!supplierSelect || !itemsTableBody || !sourceTypeInput) return;

  let currentSource = 'receipts'; // Default source

  const updateTotal = () => {
    let total = 0;
    itemsTableBody.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
      total += parseFloat(checkbox.dataset.value);
    });
    totalAmountSpan.textContent = total.toFixed(3);
  };

  const renderTable = (source, data) => {
    itemsTableBody.innerHTML = ''; // Clear previous data
    if (source === 'receipts') {
      itemsTableBody.closest('table').querySelector('thead').innerHTML = `
        <tr>
          <th style="width: 5%;"><input class="form-check-input" type="checkbox" id="select-all-items" title="تحديد الكل"></th>
          <th>تاريخ الإفراج</th>
          <th>رقم الفحص</th>
          <th>المنتج</th>
          <th>الكمية</th>
          <th class="text-end">القيمة</th>
        </tr>
      `;
      data.forEach(item => {
        const row = `
          <tr>
            <td><input class="form-check-input item-checkbox" type="checkbox" name="item_ids" value="${item.id}" data-value="${item.total_value}"></td>
            <td>${item.release_date}</td>
            <td>${item.qc_no || 'N/A'}</td>
            <td>${item.product_name}</td>
            <td>${item.quantity} ${item.unit}</td>
            <td class="text-end">${parseFloat(item.total_value).toFixed(3)}</td>
          </tr>
        `;
        itemsTableBody.insertAdjacentHTML("beforeend", row);
      });
    } else if (source === 'expenses') {
      itemsTableBody.closest('table').querySelector('thead').innerHTML = `
        <tr>
          <th style="width: 5%;"><input class="form-check-input" type="checkbox" id="select-all-items" title="تحديد الكل"></th>
          <th>تاريخ المصروف</th>
          <th>الوصف</th>
          <th>الفئة</th>
          <th>رقم الطلب</th>
          <th class="text-end">المبلغ</th>
        </tr>
      `;
      data.forEach(item => {
        const row = `
          <tr>
            <td><input class="form-check-input item-checkbox" type="checkbox" name="item_ids" value="${item.id}" data-value="${item.amount}"></td>
            <td>${item.date}</td>
            <td>${item.description}</td>
            <td>${item.category}</td>
            <td>#${item.request_id}</td>
            <td class="text-end">${parseFloat(item.amount).toFixed(3)}</td>
          </tr>
        `;
        itemsTableBody.insertAdjacentHTML("beforeend", row);
      });
    }
    // Re-bind the select-all checkbox logic after re-rendering the header
    const newSelectAllCheckbox = itemsTableBody.closest('table').querySelector('#select-all-items');
    if (newSelectAllCheckbox) {
        newSelectAllCheckbox.addEventListener('change', (e) => {
            itemsTableBody.querySelectorAll('.item-checkbox').forEach(checkbox => {
                checkbox.checked = e.target.checked;
            });
            updateTotal();
        });
    }
  };

  const fetchData = async () => {
    const supplierId = supplierSelect.value;
    itemsTableBody.innerHTML = "";
    totalAmountSpan.textContent = "0.000";
    noItemsRow.classList.add("d-none");
    loadingSpinner.classList.remove("d-none");

    if (!supplierId) {
      loadingSpinner.classList.add("d-none");
      noItemsRow.classList.remove("d-none");
      noItemsRow.textContent = "يرجى اختيار مورد لعرض البنود المتاحة.";
      return;
    }

    try {
      const url = currentSource === 'receipts' 
        ? window.appUrls.apiUninvoicedReceipts.replace('0', supplierId)
        : window.appUrls.apiUninvoicedExpenses.replace('0', supplierId);
        
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Network response was not ok (${response.status})`);
      const data = await response.json();
      
      loadingSpinner.classList.add("d-none");
      const items = data.receipts || data.expenses;

      if (items.length === 0) {
        noItemsRow.classList.remove("d-none");
        noItemsRow.textContent = "لا توجد بنود متاحة لهذا المورد.";
        return;
      }
      
      renderTable(currentSource, items);

    } catch (error) {
      console.error(`Failed to fetch ${currentSource}:`, error);
      loadingSpinner.classList.add("d-none");
      noItemsRow.textContent = "حدث خطأ أثناء تحميل البيانات.";
      noItemsRow.classList.remove("d-none");
    }
  };

  tabs.forEach(tab => {
    tab.addEventListener('show.bs.tab', event => {
      currentSource = event.target.dataset.source;
      sourceTypeInput.value = currentSource;
      fetchData();
    });
  });

  supplierSelect.addEventListener("change", fetchData);

  itemsTableBody.addEventListener("change", event => {
    if (event.target.classList.contains('item-checkbox')) {
      updateTotal();
    }
  });
}

function initCreateCustomerInvoiceLogic(container) {
  const soSelect = container.querySelector("#sales_order");
  const dispatchesTableBody = container.querySelector("#dispatches-table-body");
  const totalAmountSpan = container.querySelector("#total-amount");
  const noDispatchesRow = container.querySelector("#no-dispatches-row");
  const loadingSpinner = container.querySelector("#dispatches-loading");

  if (!soSelect || !dispatchesTableBody) return;
  
  const updateTotal = () => {
    let total = 0;
    dispatchesTableBody.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
      total += parseFloat(checkbox.dataset.value);
    });
    totalAmountSpan.textContent = total.toFixed(3);
  };

  dispatchesTableBody.addEventListener("change", event => {
    if (event.target.type === "checkbox") {
      updateTotal();
    }
  });
  
  soSelect.addEventListener("change", async event => {
    const soId = event.target.value;
    dispatchesTableBody.innerHTML = "";
    totalAmountSpan.textContent = "0.000";
    noDispatchesRow.classList.add("d-none");
    loadingSpinner.classList.remove("d-none");

    if (!soId) {
      loadingSpinner.classList.add("d-none");
      noDispatchesRow.classList.remove("d-none");
      return;
    }
    
    try {
      const url = window.appUrls.apiUninvoicedDispatches.replace("<soId>", soId);
      const response = await fetch(url);
      if (!response.ok) throw new Error("Network response was not ok");
      const data = await response.json();
      
      loadingSpinner.classList.add("d-none");
      
      if (data.dispatches.length === 0) {
        noDispatchesRow.classList.remove("d-none");
        return;
      }

      data.dispatches.forEach(d => {
        const row = `
          <tr>
            <td><input class="form-check-input" type="checkbox" name="dispatch_ids" value="${d.id}" data-value="${d.total_value}"></td>
            <td>${d.dispatch_date}</td>
            <td>${d.product_name}</td>
            <td>${d.quantity} ${d.unit}</td>
            <td class="text-end">${parseFloat(d.total_value).toFixed(3)}</td>
          </tr>
        `;
        dispatchesTableBody.insertAdjacentHTML("beforeend", row);
      });
    } catch (error) {
        console.error("Failed to fetch dispatches:", error);
        loadingSpinner.classList.add("d-none");
        noDispatchesRow.querySelector('td').textContent = "حدث خطأ أثناء تحميل البيانات.";
        noDispatchesRow.classList.remove("d-none");
    }
  });
}

// ====================================================================
// NEW AND IMPROVED JOURNAL ENTRY LOGIC
// ====================================================================
function initJournalEntryCreateLogic(container) {
    const form = container.querySelector('#journalEntryForm');
    if (!form) return;

    const formsetContainer = form.querySelector('#formset-container');
    const addRowBtn = form.querySelector('#add-form-row');
    const totalForms = form.querySelector('#id_lines-TOTAL_FORMS');
    const emptyFormTemplate = form.querySelector('#empty-form-template');
    
    // Sticky footer elements
    const debitTotalEl = form.querySelector('#debit-total');
    const creditTotalEl = form.querySelector('#credit-total');
    const differenceTotalEl = form.querySelector('#difference-total');
    const saveBtn = form.querySelector('#save-je-btn');

    const updateTotals = () => {
        let totalDebit = 0;
        let totalCredit = 0;

        formsetContainer.querySelectorAll('.formset-row').forEach(row => {
            const deleteCheckbox = row.querySelector('input[id$="-DELETE"]');
            if (deleteCheckbox && deleteCheckbox.checked) {
                return; // Skip deleted rows
            }
            
            const debitInput = row.querySelector('.debit-input');
            const creditInput = row.querySelector('.credit-input');
            
            totalDebit += parseFloat(debitInput.value) || 0;
            totalCredit += parseFloat(creditInput.value) || 0;
        });
        
        const difference = totalDebit - totalCredit;

        debitTotalEl.textContent = totalDebit.toFixed(3);
        creditTotalEl.textContent = totalCredit.toFixed(3);
        differenceTotalEl.textContent = difference.toFixed(3);

        if (Math.abs(difference) < 0.0001 && totalDebit > 0) {
            differenceTotalEl.classList.remove('text-danger');
            differenceTotalEl.classList.add('text-success');
            saveBtn.disabled = false;
        } else {
            differenceTotalEl.classList.add('text-danger');
            differenceTotalEl.classList.remove('text-success');
            saveBtn.disabled = true;
        }
    };

    const syncHiddenForm = (row) => {
        const debitInput = row.querySelector('.debit-input');
        const creditInput = row.querySelector('.credit-input');
        const amountField = row.querySelector('input[id$="-amount"]');
        const entryTypeField = row.querySelector('select[id$="-entry_type"]');
        
        const debitValue = parseFloat(debitInput.value) || 0;
        const creditValue = parseFloat(creditInput.value) || 0;

        if (debitValue > 0) {
            amountField.value = debitValue;
            entryTypeField.value = 'debit';
        } else {
            amountField.value = creditValue;
            entryTypeField.value = 'credit';
        }
    };
    
    const addRow = () => {
        const formNum = parseInt(totalForms.value);
        const newFormHtml = emptyFormTemplate.innerHTML.replace(/__prefix__/g, formNum);
        
        formsetContainer.insertAdjacentHTML('beforeend', newFormHtml);
        totalForms.value = formNum + 1;
        
        const newRow = formsetContainer.querySelector(`#row-${formNum}`);
        
        // Initialize TomSelect on the new account selector
        const newSelect = newRow.querySelector('select[id$="-account"]');
        if (newSelect) {
            new TomSelect(newSelect, {
                rtl: true,
                placeholder: "ابحث أو اختر حساب...",
                create: false,
                dropdownParent: "body",
            });
        }
        
        newRow.querySelector('.debit-input').focus();
        updateTotals();
    };

    formsetContainer.addEventListener('input', (e) => {
        const target = e.target;
        if (target.classList.contains('debit-input') || target.classList.contains('credit-input')) {
            const row = target.closest('.formset-row');
            // Ensure only one of debit/credit has a value
            if (target.classList.contains('debit-input') && target.value) {
                row.querySelector('.credit-input').value = '';
            } else if (target.classList.contains('credit-input') && target.value) {
                row.querySelector('.debit-input').value = '';
            }
            syncHiddenForm(row);
            updateTotals();
        }
    });

    formsetContainer.addEventListener('click', (e) => {
        const removeBtn = e.target.closest('.remove-form-row');
        if (removeBtn) {
            const row = removeBtn.closest('.formset-row');
            const deleteCheckbox = row.querySelector('input[id$="-DELETE"]');
            if (deleteCheckbox) {
                deleteCheckbox.checked = true;
                row.style.display = 'none';
                updateTotals();
            }
        }
    });

    addRowBtn.addEventListener('click', addRow);
    
    // Add new row on Enter key in last input of last row
    formsetContainer.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const lastRow = formsetContainer.querySelector('.formset-row:not([style*="display: none"]):last-of-type');
            const creditInput = lastRow.querySelector('.credit-input');
            if(document.activeElement === creditInput){
                 e.preventDefault();
                 addRow();
            }
        }
    });

    // Initialize logic for existing rows
    formsetContainer.querySelectorAll('.formset-row').forEach(row => {
        syncHiddenForm(row); // Initial sync for pre-populated forms (e.g., on error)
    });
    updateTotals(); // Initial calculation
}

// --- NEW: Logic for Cost Pool Management ---
function initCostPoolsListLogic(container) {
    const modalEl = container.querySelector('#createCostPoolModal');
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl);
    const form = modalEl.querySelector('#costPoolForm');
    const modalTitle = modalEl.querySelector('.modal-title');
    const poolIdInput = form.querySelector('#pool_id');
    const poolNameInput = form.querySelector('#pool_name');
    const poolParentSelect = form.querySelector('#pool_parent');
    const poolGlAccountSelect = form.querySelector('#pool_gl_account');
    
    // TomSelect instances can be stored to manage them
    let parentTomSelect = poolParentSelect.tomselect;
    let glAccountTomSelect = poolGlAccountSelect.tomselect;

    // Handle opening the modal for editing
    container.querySelectorAll('.edit-cost-pool-btn').forEach(button => {
        button.addEventListener('click', () => {
            const poolId = button.dataset.poolId;
            const poolName = button.dataset.poolName;
            const parentId = button.dataset.poolParentId;
            const glAccountId = button.dataset.poolGlAccountId;

            modalTitle.textContent = "Edit Cost Pool";
            poolIdInput.value = poolId;
            poolNameInput.value = poolName;
            
            if (parentTomSelect) {
                parentTomSelect.setValue(parentId || '');
            } else {
                poolParentSelect.value = parentId || '';
            }
            if (glAccountTomSelect) {
                glAccountTomSelect.setValue(glAccountId || '');
            } else {
                poolGlAccountSelect.value = glAccountId || '';
            }
        });
    });

    // Handle delete button clicks
    container.querySelectorAll('.delete-cost-pool-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            const poolId = button.dataset.poolId;
            const poolName = button.dataset.poolName;
            
            if (confirm(`Are you sure you want to delete the cost pool "${poolName}"? This action cannot be undone.`)) {
                const deleteForm = document.getElementById('deleteCostPoolForm');
                if (deleteForm) {
                    deleteForm.querySelector('#delete_pool_id').value = poolId;
                    deleteForm.submit();
                }
            }
        });
    });

    // Reset modal on open for the "Create New" case, if not triggered by an edit button
    modalEl.addEventListener('show.bs.modal', function (event) {
        // If the modal was triggered by the main "Create New" button
        if (!event.relatedTarget || !event.relatedTarget.classList.contains('edit-cost-pool-btn')) {
            modalTitle.textContent = "Create New Cost Pool";
            form.reset();
            poolIdInput.value = '';
            if (parentTomSelect) {
                parentTomSelect.clear();
            }
            if (glAccountTomSelect) {
                glAccountTomSelect.clear();
            }
        }
    });
}

// --- NEW: Logic for Allocation Driver Management ---
function initAllocationDriversListLogic(container) {
    const modalEl = container.querySelector('#createDriverModal');
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl);
    const form = modalEl.querySelector('#driverForm');
    const modalTitle = modalEl.querySelector('.modal-title');
    const driverIdInput = form.querySelector('#driver_id');
    const driverNameInput = form.querySelector('#driver_name');
    const driverDescInput = form.querySelector('#driver_description');

    container.querySelectorAll('.edit-driver-btn').forEach(button => {
        button.addEventListener('click', () => {
            modalTitle.textContent = "Edit Allocation Driver";
            driverIdInput.value = button.dataset.driverId;
            driverNameInput.value = button.dataset.driverName;
            driverDescInput.value = button.dataset.driverDescription;
        });
    });

    modalEl.addEventListener('hidden.bs.modal', () => {
        modalTitle.textContent = "Create New Allocation Driver";
        form.reset();
        driverIdInput.value = '';
    });
}

// --- NEW: Logic for Overhead Allocation Workspace ---
function initOverheadAllocationWorkspaceLogic(container) {
    // This function can be used to add any specific JS logic for the workspace in the future.
    // For now, the forms are handled by the dynamic content loader's default behavior.
    // We can add confirmation modals here if needed.
    container.querySelectorAll('form[action*="overhead_allocation"]').forEach(form => {
        form.addEventListener('submit', (e) => {
            const action = form.querySelector('input[name="action"]').value;
            let message = "Are you sure you want to proceed?";
            if (action === 'calculate_rate') {
                message = "This will calculate the overhead rate based on the current data. Proceed?";
            } else if (action === 'post_to_gl') {
                message = "WARNING: This action is irreversible and will post a journal entry to the General Ledger. Are you absolutely sure you want to proceed?";
            } else if (action === 'apply_to_inventory') {
                message = "WARNING: This will apply the calculated overhead cost to all finished goods in the period. This action cannot be easily undone. Proceed?";
            }
            
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
}

// --- NEW: Logic for Fiscal Year / Period Management ---
function initFiscalYearListLogic(container) {
    const createPeriodModalEl = container.querySelector('#createFinancialPeriodModal');
    if (createPeriodModalEl) {
        const form = createPeriodModalEl.querySelector('#createFinancialPeriodForm');
        const yearIdInput = createPeriodModalEl.querySelector('#modal_fiscal_year_id');
        // The base action URL might be incorrect if loaded dynamically, so we build it fresh.
        // It should look like: /financials/periods/create_period/0/
        const actionParts = window.location.pathname.split('/');
        actionParts.pop(); // remove trailing slash
        actionParts.push('create_period', '0', '');
        const originalAction = actionParts.join('/');


        // Use an event listener on the container to handle dynamically added buttons
        container.addEventListener('click', function(event) {
            const button = event.target.closest('.create-period-btn');
            if (button) {
                const yearId = button.getAttribute('data-year-id');
                if (yearId) {
                    yearIdInput.value = yearId;
                    const newAction = originalAction.replace('/0/', `/${yearId}/`);
                    form.setAttribute('action', newAction);
                }
            }
        });
    }
}


function initReconciliationManageLogic(container) {
    const reconciliationWorkspace = container.querySelector('#reconciliationWorkspace');
    if (!reconciliationWorkspace) return;

    const reconId = reconciliationWorkspace.dataset.reconciliationId;
    const matchUrl = reconciliationWorkspace.dataset.matchUrl;
    const csrfToken = reconciliationWorkspace.dataset.csrfToken;
    const status = reconciliationWorkspace.dataset.status;

    // --- MODAL FOR MATCHING ---
    const confirmationModalEl = container.querySelector('#confirmationModal');
    const confirmationModal = confirmationModalEl ? new bootstrap.Modal(confirmationModalEl) : null;
    const modalBody = container.querySelector('#confirmationModal .modal-body');
    const confirmButton = container.querySelector('#confirmActionBtn');

    // --- NEW: MODAL FOR ADJUSTMENTS ---
    const adjustmentModalEl = container.querySelector('#adjustmentModal');
    const adjustmentModal = adjustmentModalEl ? new bootstrap.Modal(adjustmentModalEl) : null;
    const adjustmentForm = container.querySelector('#adjustmentForm');
    const modalLineId = container.querySelector('#modalLineId');
    const modalLineDescription = container.querySelector('#modalLineDescription');
    const modalLineAmount = container.querySelector('#modalLineAmount');
    const modalDescriptionInput = container.querySelector('#modalDescription');
    const modalAccountSelect = container.querySelector('#modalAccount');
    const modalAccountLabel = container.querySelector('#modalAccountLabel');


    if (!confirmationModal || !modalBody || !confirmButton) {
        console.error("Reconciliation matching modal elements not found.");
        return;
    }
     if (!adjustmentModal || !adjustmentForm) {
        console.error("Reconciliation adjustment modal elements not found.");
        return;
    }

    if (status === "reconciled") {
        reconciliationWorkspace.querySelectorAll('input, button, .statement-line, .internal-transaction').forEach(el => {
            el.disabled = true;
            el.style.pointerEvents = 'none';
        });
        return;
    }

    let selectedLine = null;
    let selectedTrx = null;
    let lastFocusedElement = null; // To store focus for accessibility

    function clearSelections() {
        if (selectedLine) {
            selectedLine.classList.remove('selected');
            selectedLine = null;
        }
        if (selectedTrx) {
            selectedTrx.classList.remove('selected');
            selectedTrx = null;
        }
    }

    reconciliationWorkspace.querySelectorAll('.statement-line').forEach(row => {
        row.addEventListener('click', () => {
            const isCurrentlySelected = row.classList.contains('selected');
            if (selectedLine) selectedLine.classList.remove('selected');
            
            if (isCurrentlySelected) {
                selectedLine = null;
            } else {
                selectedLine = row;
                selectedLine.classList.add('selected');
            }
            checkAndMatch();
        });
    });

    reconciliationWorkspace.querySelectorAll('.internal-transaction').forEach(row => {
        row.addEventListener('click', () => {
            const isCurrentlySelected = row.classList.contains('selected');
            if (selectedTrx) selectedTrx.classList.remove('selected');

            if (isCurrentlySelected) {
                selectedTrx = null;
            } else {
                selectedTrx = row;
                selectedTrx.classList.add('selected');
            }
            checkAndMatch();
        });
    });

    function checkAndMatch() {
        if (!selectedLine || !selectedTrx) return;

        const lineAmount = parseFloat(selectedLine.dataset.amount);
        const trxAmount = parseFloat(selectedTrx.dataset.amount);

        if (Math.abs(lineAmount - trxAmount) < 0.001) {
            modalBody.innerHTML = `
                <p>هل أنت متأكد من أنك تريد مطابقة هذه المعاملات؟</p>
                <ul>
                    <li><strong>كشف الحساب:</strong> ${selectedLine.cells[1].innerText} (${lineAmount.toFixed(2)})</li>
                    <li><strong>معاملة داخلية:</strong> ${selectedTrx.cells[1].innerText} (${trxAmount.toFixed(2)})</li>
                </ul>
            `;
            confirmationModal.show();

            confirmButton.onclick = () => {
                // Ensure selectedLine and selectedTrx are still valid before matching
                if (selectedLine && selectedTrx) {
                    match(selectedLine.dataset.lineId, selectedTrx.dataset.trxId, selectedTrx.dataset.trxType);
                }
                confirmationModal.hide();
            };
        } else {
            showAlert('المبالغ غير متطابقة. يرجى تحديد معاملات بنفس القيمة.', 'warning');
            clearSelections();
        }
    }
    
    // --- NEW: ADJUSTMENT MODAL LOGIC ---
    const expenseAccounts = JSON.parse(document.getElementById('expense-accounts-data').textContent);
    const incomeAccounts = JSON.parse(document.getElementById('income-accounts-data').textContent);

    container.querySelectorAll('.create-adjustment-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            const row = e.target.closest('.statement-line');
            const lineId = row.dataset.lineId;
            const lineAmount = parseFloat(row.dataset.amount);
            const lineDescription = row.dataset.description;

            // Populate modal fields
            modalLineId.value = lineId;
            modalLineDescription.textContent = lineDescription;
            modalLineAmount.textContent = lineAmount.toFixed(3);
            modalDescriptionInput.value = lineDescription; // Pre-fill description

            // Populate account dropdown based on amount
            modalAccountSelect.innerHTML = ''; // Clear previous options
            const accounts = lineAmount < 0 ? expenseAccounts : incomeAccounts;
            modalAccountLabel.textContent = lineAmount < 0 ? 'اختر حساب المصروف' : 'اختر حساب الإيراد';
            
            accounts.forEach(acc => {
                const option = new Option(`${acc.code} - ${acc.name}`, acc.id);
                modalAccountSelect.add(option);
            });
        });
    });

    adjustmentForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const adjustmentUrl = reconciliationWorkspace.dataset.adjustmentUrl;
        const formData = new FormData(adjustmentForm);

        try {
            const response = await fetch(adjustmentUrl, {
                method: 'POST',
                body: formData,
                headers: { 
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken // Add the CSRF token to the header
                }
            });

            // Improved debugging: Check if the response is ok before trying to parse JSON
            if (!response.ok) {
                // Get the raw text of the error response for better debugging
                const errorText = await response.text();
                console.error('Adjustment API Error Response:', errorText);
                throw new Error(`Server responded with status ${response.status}`);
            }

            const data = await response.json();
            if (data.status === 'success') {
                adjustmentModal.hide();
                showAlert('تم إنشاء وتسوية التعديل بنجاح.', 'success');
                if (window.loadContent) {
                    window.loadContent(window.location.href, false);
                } else {
                    location.reload();
                }
            } else {
                showAlert('خطأ في إنشاء التعديل: ' + data.message, 'danger');
            }
        } catch (error) {
            // --- ADDED DEBUGGING ---
            console.error('Full Adjustment Error:', error);
            showAlert('حدث خطأ غير متوقع أثناء إنشاء التعديل.', 'danger');
        }
    });


    if (confirmationModalEl) {
        // --- NEW: Accessibility Fix ---
        // Store the last focused element before the modal opens
        confirmationModalEl.addEventListener('show.bs.modal', () => {
            lastFocusedElement = document.activeElement;
        });
        // When the modal is hidden, clear selections and return focus
        confirmationModalEl.addEventListener('hidden.bs.modal', () => {
            clearSelections();
            if (lastFocusedElement) {
                lastFocusedElement.focus();
            }
        });
    }

    async function match(lineId, trxId, trxType) {
        const formData = new FormData();
        formData.append('line_id', lineId);
        formData.append('trx_id', trxId);
        formData.append('trx_type', trxType);
        formData.append('csrfmiddlewaretoken', csrfToken);

        try {
            const response = await fetch(matchUrl, {
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (window.loadContent) {
                    showAlert('تمت مطابقة المعاملة بنجاح.', 'success');
                    window.loadContent(window.location.href, false);
                } else {
                    location.reload();
                }
            } else {
                showAlert('خطأ في مطابقة المعاملة: ' + data.message, 'danger');
            }
        } catch (error) {
            console.error('Error:', error);
            showAlert('حدث خطأ غير متوقع.', 'danger');
        }
    }

    function showAlert(message, type = 'info') {
        const alertContainer = document.querySelector('#page-content');
        if (!alertContainer) return;

        const alertHTML = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        `;
        alertContainer.insertAdjacentHTML('afterbegin', alertHTML);
    }

    reconciliationWorkspace.querySelectorAll('.unmatch-form').forEach(form => {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!confirm('Are you sure you want to unmatch this transaction?')) {
                return;
            }

            const url = form.action;
            const formData = new FormData(form);

            try {
                const response = await fetch(url, {
                    method: 'POST',
                    body: formData,
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    }
                });
                if (response.ok && response.redirected) {
                    if (window.loadContent) {
                        window.loadContent(response.url, false);
                    } else {
                        window.location.href = response.url;
                    }
                } else {
                    const data = await response.json();
                    showAlert(data.message || 'An error occurred.', 'danger');
                }
            } catch (error) {
                console.error('Unmatch Error:', error);
                showAlert('An unexpected error occurred during unmatching.', 'danger');
            }
        });
    });
}