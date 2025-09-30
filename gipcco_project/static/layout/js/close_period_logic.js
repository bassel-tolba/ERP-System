// gipcco_project/static/layout/js/close_period_logic.js

function initClosePeriodLogic(container) {
    const cockpitContainer = container.querySelector('#close-period-container');
    if (!cockpitContainer) {
        return;
    }

    const periodId = cockpitContainer.dataset.periodId;
    const checklistUrl = cockpitContainer.dataset.checklistUrl;
    const loadingEl = cockpitContainer.querySelector('#checklist-loading');
    const checklistItemsEl = cockpitContainer.querySelector('#checklist-items');
    const closePeriodBtn = cockpitContainer.querySelector('#closePeriodBtn');
    const closePeriodForm = cockpitContainer.querySelector('#closePeriodForm');

    const checkStatusMap = {
        is_depreciation_run: "تشغيل الإهلاك الشهري",
        is_overhead_posted: "ترحيل التكاليف العامة",
        all_banks_reconciled: "تسوية جميع الحسابات البنكية",
        no_draft_manual_jes: "لا توجد قيود يومية يدوية كمسودة",
        no_unposted_invoices: "لا توجد فواتير موردين/عملاء غير مرحلة",
        is_inventory_valuation_run: "اكتمال عملية تقييم المخزون"
    };

    async function fetchChecklistStatus() {
        try {
            const response = await fetch(checklistUrl);
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText}`);
            }
            const data = await response.json();
            renderChecklist(data);
        } catch (error) {
            console.error('Failed to fetch checklist status:', error);
            checklistItemsEl.innerHTML = `<li class="list-group-item list-group-item-danger">فشل تحميل قائمة التحقق. يرجى المحاولة مرة أخرى.</li>`;
        } finally {
            loadingEl.style.display = 'none';
            checklistItemsEl.style.display = '';
        }
    }

    function renderChecklist(data) {
        checklistItemsEl.innerHTML = '';
        let allComplete = true;

        for (const [key, check] of Object.entries(data)) {
            const isComplete = check.status;
            if (!isComplete) {
                allComplete = false;
            }

            const icon = isComplete 
                ? '<i class="bi bi-check-circle-fill text-success me-2"></i>' 
                : '<i class="bi bi-x-circle-fill text-danger me-2"></i>';
            
            const detailsHtml = check.details && check.details.length > 0 
                ? `<ul class="mt-2 mb-0 small text-muted">${check.details.map(d => `<li><a href="${d.url}" target="_blank">${d.description}</a></li>`).join('')}</ul>`
                : '';

            const listItem = `
                <li class="list-group-item d-flex justify-content-between align-items-center">
                    <div>
                        ${icon}
                        <strong>${checkStatusMap[key] || key}</strong>
                        <p class="mb-0 small text-muted">${check.message}</p>
                        ${detailsHtml}
                    </div>
                    <span class="badge bg-${isComplete ? 'success' : 'danger'} rounded-pill">${isComplete ? 'مكتمل' : 'غير مكتمل'}</span>
                </li>
            `;
            checklistItemsEl.insertAdjacentHTML('beforeend', listItem);
        }

        if (allComplete) {
            closePeriodBtn.disabled = false;
            closePeriodBtn.classList.remove('btn-danger');
            closePeriodBtn.classList.add('btn-success');
            closePeriodBtn.innerHTML = '<i class="bi bi-check-circle-fill me-2"></i> إغلاق الفترة الآن';
        } else {
            closePeriodBtn.disabled = true;
            closePeriodBtn.classList.add('btn-danger');
            closePeriodBtn.classList.remove('btn-success');
            closePeriodBtn.innerHTML = '<i class="bi bi-lock-fill me-2"></i> إغلاق الفترة بشكل نهائي';
        }
    }

    if (closePeriodForm) {
        closePeriodForm.addEventListener('submit', (e) => {
            if (!confirm('هل أنت متأكد من أنك تريد إغلاق هذه الفترة بشكل نهائي؟ لا يمكن التراجع عن هذا الإجراء.')) {
                e.preventDefault();
            }
        });
    }

    fetchChecklistStatus();
}

// Since this file is loaded on all pages, we need to make sure the init function is available globally
// for the dynamic content loader.
window.initClosePeriodLogic = initClosePeriodLogic;
