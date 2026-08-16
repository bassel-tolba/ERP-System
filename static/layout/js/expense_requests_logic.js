document.addEventListener('DOMContentLoaded', function() {
    const requestTypeSelect = document.getElementById('request_type');
    const dynamicFieldsContainer = document.getElementById('dynamic-fields-container');
    const allFieldGroups = dynamicFieldsContainer.querySelectorAll('.request-fields');

    // --- NEW: Settlement Method Logic ---
    const settlementMethodSelect = document.getElementById('settlement_method');
    const supplierFieldGroup = document.getElementById('supplier-field-group');
    const bankAccountFieldGroup = document.getElementById('bank-account-field-group');
    const supplierSelect = document.getElementById('supplier');
    const bankAccountSelect = document.getElementById('bank_account');

    function handleSettlementChange() {
        const selectedMethod = settlementMethodSelect.value;

        // Hide both and disable inputs first
        supplierFieldGroup.style.display = 'none';
        bankAccountFieldGroup.style.display = 'none';
        if (supplierSelect.tomselect) supplierSelect.tomselect.disable();
        if (bankAccountSelect.tomselect) bankAccountSelect.tomselect.disable();

        if (selectedMethod === 'ACCRUE_AND_PAY_LATER') {
            supplierFieldGroup.style.display = 'block';
            if (supplierSelect.tomselect) supplierSelect.tomselect.enable();
        } else if (selectedMethod === 'DIRECT_PAYMENT') {
            bankAccountFieldGroup.style.display = 'block';
            if (bankAccountSelect.tomselect) bankAccountSelect.tomselect.enable();
        }
    }

    if (settlementMethodSelect) {
        settlementMethodSelect.addEventListener('change', handleSettlementChange);
    }
    // --- END NEW LOGIC ---

    // --- NEW: Logic for Invoice Creation from Logs ---
    const invoiceSupplierFilter = document.getElementById('invoice_supplier_filter');
    const logIdsSelect = document.getElementById('log_ids');
    if (invoiceSupplierFilter && logIdsSelect) {
        const logOptions = Array.from(logIdsSelect.options);
        const logIdsTomSelect = new TomSelect(logIdsSelect, {
            plugins: ['remove_button'],
            hideSelected: true,
        });

        invoiceSupplierFilter.addEventListener('change', function() {
            const selectedSupplierId = this.value;
            logIdsTomSelect.clear();
            logIdsTomSelect.clearOptions();

            const filteredOptions = logOptions.filter(option => {
                return !selectedSupplierId || option.dataset.supplier === selectedSupplierId;
            });

            logIdsTomSelect.addOptions(filteredOptions.map(opt => ({ value: opt.value, text: opt.textContent })));
            
            if (selectedSupplierId) {
                logIdsTomSelect.enable();
            } else {
                logIdsTomSelect.disable();
            }
        });
        // Initial state
        logIdsTomSelect.disable();
    }

    // --- NEW: Logic for Employee Advance Settlement ---
    const employeeFilter = document.getElementById('advance_employee_filter');
    const advanceSelectInput = document.getElementById('advance_id');
    const expenseLogSelectInput = document.getElementById('expense_log_id');

    if (employeeFilter && advanceSelectInput && expenseLogSelectInput) {
        const advanceTomSelect = advanceSelectInput.tomselect;
        const expenseLogTomSelect = expenseLogSelectInput.tomselect;
        
        const allAdvanceOptions = advanceTomSelect ? Object.values(advanceTomSelect.options) : [];
        const allExpenseLogOptions = expenseLogTomSelect ? Object.values(expenseLogTomSelect.options) : [];

        employeeFilter.addEventListener('change', function() {
            const selectedEmployeeId = this.value;

            // Filter Advances
            if (advanceTomSelect) {
                advanceTomSelect.clear();
                advanceTomSelect.clearOptions();
                const filteredAdvances = allAdvanceOptions.filter(opt => !selectedEmployeeId || opt.data.employee === selectedEmployeeId);
                advanceTomSelect.addOptions(filteredAdvances);
                selectedEmployeeId ? advanceTomSelect.enable() : advanceTomSelect.disable();
            }

            // Filter Expense Logs
            if (expenseLogTomSelect) {
                expenseLogTomSelect.clear();
                expenseLogTomSelect.clearOptions();
                const filteredLogs = allExpenseLogOptions.filter(opt => !selectedEmployeeId || opt.data.employee === selectedEmployeeId);
                expenseLogTomSelect.addOptions(filteredLogs);
                selectedEmployeeId ? expenseLogTomSelect.enable() : expenseLogTomSelect.disable();
            }
        });

        // Initial state
        if (advanceTomSelect) advanceTomSelect.disable();
        if (expenseLogTomSelect) expenseLogTomSelect.disable();
    }


    if (requestTypeSelect) {
        requestTypeSelect.addEventListener('change', function() {
            const selectedType = this.value;

            // Hide all field groups first
            allFieldGroups.forEach(group => {
                group.style.display = 'none';
                // Disable inputs in hidden groups to prevent submission
                group.querySelectorAll('input, select, textarea').forEach(input => {
                    input.disabled = true;
                    // If it's a TomSelect, disable it via its API
                    if (input.tomselect) {
                        input.tomselect.disable();
                    }
                });
            });

            // Find and show the selected group
            const targetGroup = dynamicFieldsContainer.querySelector(`[data-type="${selectedType}"]`);
            if (targetGroup) {
                targetGroup.style.display = 'block';
                // Re-enable inputs in the visible group
                targetGroup.querySelectorAll('input, select, textarea').forEach(input => {
                    input.disabled = false;
                    // If it's a TomSelect, enable it via its API
                    if (input.tomselect) {
                        input.tomselect.enable();
                    }
                });
            }

            // Trigger our new settlement handler when the main type changes, to reset the state
            if (settlementMethodSelect) {
                // Reset selection and then trigger handler to hide fields
                settlementMethodSelect.value = '';
                handleSettlementChange();
            }
        });
    }

    // Initialize TomSelect for all selects with the class
    document.querySelectorAll('.tom-select').forEach((el) => {
        new TomSelect(el, {
            create: false,
            sortField: {
                field: "text",
                direction: "asc"
            }
        });
    });

    // Initialize Flatpickr for date fields
    flatpickr(".flatpickr-date", {
        dateFormat: "Y-m-d",
        defaultDate: "today"
    });

    // Handle Reject Modal
    const rejectModal = document.getElementById('rejectModal');
    if (rejectModal) {
        rejectModal.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            const requestId = button.getAttribute('data-request-id');
            const modalRequestIdInput = rejectModal.querySelector('#rejectRequestId');
            modalRequestIdInput.value = requestId;
        });
    }

    // Handle Correction Modal
    const correctionModal = document.getElementById('correctionModal');
    if (correctionModal) {
        correctionModal.addEventListener('show.bs.modal', function (event) {
            const button = event.relatedTarget;
            const requestId = button.getAttribute('data-request-id');
            const modalRequestIdInput = correctionModal.querySelector('#correctionRequestId');
            modalRequestIdInput.value = requestId;
        });
    }

    // Trigger change event on page load to set initial form state
    if (requestTypeSelect) {
        requestTypeSelect.dispatchEvent(new Event('change'));
    }
});
