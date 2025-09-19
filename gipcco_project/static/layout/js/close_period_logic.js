// static/layout/js/close_period_logic.js

function initClosePeriodLogic(container) {
    const closePeriodContainer = container.querySelector('#closePeriodContainer');
    if (!closePeriodContainer) return;

    const checklist = closePeriodContainer.querySelector('#checklist');
    const finalizeBtn = closePeriodContainer.querySelector('#finalizeCloseBtn');
    if (!checklist || !finalizeBtn) return;

    const periodId = closePeriodContainer.dataset.periodId;
    if (!periodId) {
        console.error("Could not find period ID in data attribute.");
        return;
    }
    const checklistUrl = `/api/periods/${periodId}/checklist_status/`;

    const updateChecklistItem = (item, result) => {
        const spinner = item.querySelector('.spinner-border');
        if (spinner) spinner.remove();

        let icon;
        if (result.status) {
            icon = document.createElement('i');
            icon.className = 'bi bi-check-circle-fill text-success fs-5';
            item.classList.add('list-group-item-success');
        } else {
            icon = document.createElement('i');
            icon.className = 'bi bi-x-circle-fill text-danger fs-5';
            item.classList.add('list-group-item-danger');
            
            const small = document.createElement('small');
            small.className = 'd-block text-muted mt-1';
            small.textContent = result.message;
            item.querySelector('span:first-child').appendChild(small);

            if (result.details && result.details.length > 0) {
                const detailsList = document.createElement('ul');
                detailsList.className = 'list-unstyled mt-2 mb-0 ps-3';
                result.details.forEach(detail => {
                    const listItem = document.createElement('li');
                    const link = document.createElement('a');
                    link.href = detail.url;
                    link.textContent = detail.description;
                    link.className = 'text-danger small';
                    listItem.appendChild(link);
                    detailsList.appendChild(listItem);
                });
                item.appendChild(detailsList);
            }
        }
        item.appendChild(icon);
    };

    const checkAllConditions = async () => {
        try {
            const response = await fetch(checklistUrl);
            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();

            let allConditionsMet = true;
            for (const [key, result] of Object.entries(data)) {
                const item = checklist.querySelector(`[data-check="${key}"]`);
                if (item) {
                    updateChecklistItem(item, result);
                    if (!result.status) {
                        allConditionsMet = false;
                    }
                }
            }

            if (allConditionsMet) {
                finalizeBtn.disabled = false;
                finalizeBtn.classList.remove('btn-danger');
                finalizeBtn.classList.add('btn-success');
            }

        } catch (error) {
            console.error('Failed to fetch checklist status:', error);
            const errorMsg = document.createElement('div');
            errorMsg.className = 'alert alert-danger mt-3';
            errorMsg.textContent = 'حدث خطأ أثناء التحقق من الشروط. يرجى المحاولة مرة أخرى.';
            checklist.parentElement.insertBefore(errorMsg, checklist);
        }
    };

    checkAllConditions();
}
