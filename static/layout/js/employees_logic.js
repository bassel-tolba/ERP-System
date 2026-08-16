// gipcco_project/static/layout/js/employees_logic.js

function initManageEmployeesLogic(container) {
    const modalEl = container.querySelector('#employeeModal');
    if (!modalEl) return;

    const modal = new bootstrap.Modal(modalEl);
    const form = modalEl.querySelector('#employeeForm');
    const modalTitle = modalEl.querySelector('.modal-title');
    
    const actionInput = form.querySelector('#form_action');
    const pkInput = form.querySelector('#form_employee_pk');
    const employeeIdInput = form.querySelector('#form_employee_id');
    const firstNameInput = form.querySelector('#form_first_name');
    const lastNameInput = form.querySelector('#form_last_name');
    const jobTitleInput = form.querySelector('#form_job_title');
    const isActiveSwitch = form.querySelector('#form_is_active');

    // Handle opening the modal for editing
    container.querySelectorAll('.edit-employee-btn').forEach(button => {
        button.addEventListener('click', () => {
            modalTitle.textContent = "تعديل بيانات الموظف";
            actionInput.value = 'edit';
            pkInput.value = button.dataset.pk;
            
            employeeIdInput.value = button.dataset.employeeId;
            firstNameInput.value = button.dataset.firstName;
            lastNameInput.value = button.dataset.lastName;
            jobTitleInput.value = button.dataset.jobTitle;
            isActiveSwitch.checked = button.dataset.isActive === 'true';
        });
    });

    // Reset modal on close for the "Create New" case
    modalEl.addEventListener('hidden.bs.modal', () => {
        modalTitle.textContent = "إضافة موظف جديد";
        form.reset();
        actionInput.value = 'create';
        pkInput.value = '';
        isActiveSwitch.checked = true; // Default to active
    });
}

function initEmployeeFinancialsDashboardLogic(container) {
    // No specific JS needed for the dashboard right now, but the hook is here.
}

function initEmployeeAdvanceDetailLogic(container) {
    const settleModalEl = container.querySelector('#settleAdvanceModal');
    if (!settleModalEl) return;

    const settleModal = new bootstrap.Modal(settleModalEl);
    const containerEl = container.querySelector('#employee-advances-container');
    const apiUrl = containerEl.dataset.unsettledApiUrl;
    
    const form = settleModalEl.querySelector('#settleAdvanceForm');
    const itemsInput = form.querySelector('#settlement_items_input');
    const tableBody = form.querySelector('#settlement-transactions-body');
    const loadingSpinner = form.querySelector('#settlement-transactions-loading');
    const noItemsMsg = form.querySelector('#no-settlements-message');
    const totalSelectedEl = form.querySelector('#modal_total_selected');
    const unsettledAmountEl = form.querySelector('#modal_unsettled_amount');
    const confirmBtn = form.querySelector('#confirmSettlementBtn');
    const selectAllCheckbox = form.querySelector('#select_all_settlements');

    let currentAdvanceId = null;
    let currentUnsettledAmount = 0;

    container.querySelectorAll('.settle-advance-btn').forEach(button => {
        button.addEventListener('click', async () => {
            currentAdvanceId = button.dataset.advanceId;
            currentUnsettledAmount = parseFloat(button.dataset.unsettledAmount);
            
            form.action = `/employees/financials/settle/${currentAdvanceId}/`;
            unsettledAmountEl.textContent = currentUnsettledAmount.toFixed(3);
            
            // Reset state
            tableBody.innerHTML = '';
            totalSelectedEl.textContent = '0.000';
            confirmBtn.disabled = true;
            noItemsMsg.classList.add('d-none');
            loadingSpinner.classList.remove('d-none');
            selectAllCheckbox.checked = false;

            try {
                const response = await fetch(apiUrl);
                if (!response.ok) throw new Error('Network response was not ok.');
                const data = await response.json();

                loadingSpinner.classList.add('d-none');
                if (data.transactions && data.transactions.length > 0) {
                    populateTable(data.transactions);
                } else {
                    noItemsMsg.classList.remove('d-none');
                }
            } catch (error) {
                console.error("Failed to fetch unsettled transactions:", error);
                loadingSpinner.classList.add('d-none');
                noItemsMsg.textContent = "Error loading transactions.";
                noItemsMsg.classList.remove('d-none');
            }
        });
    });

    function populateTable(transactions) {
        transactions.forEach(trx => {
            const row = `
                <tr data-amount="${trx.amount}" data-id="${trx.id}" data-type="${trx.type}">
                    <td><input class="form-check-input settlement-checkbox" type="checkbox"></td>
                    <td>${trx.date}</td>
                    <td><span class="badge bg-info">${trx.type_display}</span></td>
                    <td>${trx.description}</td>
                    <td class="text-end">${parseFloat(trx.amount).toFixed(3)}</td>
                </tr>
            `;
            tableBody.insertAdjacentHTML('beforeend', row);
        });
    }

    function updateTotals() {
        let total = 0;
        const selectedItems = [];
        
        tableBody.querySelectorAll('.settlement-checkbox:checked').forEach(checkbox => {
            const row = checkbox.closest('tr');
            const amount = parseFloat(row.dataset.amount);
            total += amount;
            selectedItems.push({
                id: row.dataset.id,
                type: row.dataset.type,
                amount: amount
            });
        });

        totalSelectedEl.textContent = total.toFixed(3);
        itemsInput.value = JSON.stringify(selectedItems);

        if (total > 0 && total <= currentUnsettledAmount) {
            confirmBtn.disabled = false;
        } else {
            confirmBtn.disabled = true;
        }
    }

    tableBody.addEventListener('change', (e) => {
        if (e.target.classList.contains('settlement-checkbox')) {
            updateTotals();
        }
    });
    
    selectAllCheckbox.addEventListener('change', (e) => {
        tableBody.querySelectorAll('.settlement-checkbox').forEach(checkbox => {
            checkbox.checked = e.target.checked;
        });
        updateTotals();
    });

    form.addEventListener('submit', (e) => {
        const totalSelected = parseFloat(totalSelectedEl.textContent);
        if (totalSelected > currentUnsettledAmount) {
            e.preventDefault();
            alert('Total selected amount cannot exceed the unsettled amount of the advance.');
        }
    });
}
