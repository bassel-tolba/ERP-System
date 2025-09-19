const reconciliationWorkspace = document.getElementById('reconciliationWorkspace');
const adjustmentModalEl = document.getElementById('adjustmentModal');
const adjustmentForm = document.getElementById('adjustmentForm');

if (reconciliationWorkspace) {
    const reconId = reconciliationWorkspace.dataset.reconciliationId;
    const matchUrl = reconciliationWorkspace.dataset.matchUrl;
    const adjustmentUrl = reconciliationWorkspace.dataset.adjustmentUrl; // <-- Use the URL from the template
    const csrfToken = reconciliationWorkspace.dataset.csrfToken;
    const status = reconciliationWorkspace.dataset.status;

    // --- MODAL FOR MATCHING ---
    const adjustmentModal = new bootstrap.Modal(adjustmentModalEl);

    document.querySelectorAll('.open-adjustment-modal').forEach(button => {
        button.addEventListener('click', () => {
            const id = button.dataset.id;
            const type = button.dataset.type;

            // Clear previous data
            adjustmentForm.reset();
            adjustmentForm.querySelector('input[name="id"]').value = id;
            adjustmentForm.querySelector('input[name="type"]').value = type;

            adjustmentModal.show();
        });
    });

    adjustmentForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(adjustmentForm);

        try {
            const response = await fetch(adjustmentUrl, { // <-- Use the correct URL variable
                method: 'POST',
                body: formData,
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
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
                // --- ADDED DEBUGGING ---
                console.error('Adjustment API Error:', data.message);
                showAlert('خطأ في إنشاء التعديل: ' + data.message, 'danger');
            }
        } catch (error) {
            // --- ADDED DEBUGGING ---
            console.error('Full Adjustment Error:', error);
            showAlert('حدث خطأ غير متوقع أثناء إنشاء التعديل.', 'danger');
        }
    });


    if (confirmationModalEl) {
        const confirmationModal = new bootstrap.Modal(confirmationModalEl);

        document.querySelectorAll('.open-confirmation-modal').forEach(button => {
            button.addEventListener('click', () => {
                const id = button.dataset.id;
                const type = button.dataset.type;

                // Set confirmation details
                confirmationModal.querySelector('.modal-body').innerText = `هل أنت متأكد من ${type === 'match' ? 'مطابقة' : 'إلغاء المطابقة'} هذه السجل؟`;
                confirmationModal.querySelector('form input[name="id"]').value = id;
                confirmationModal.querySelector('form input[name="type"]').value = type;

                confirmationModal.show();
            });
        });

        confirmationModalEl.querySelector('form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);

            try {
                const response = await fetch(matchUrl, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                });
                const data = await response.json();
                if (data.status === 'success') {
                    confirmationModal.hide();
                    showAlert('تمت العملية بنجاح.', 'success');
                    location.reload();
                } else {
                    showAlert('خطأ: ' + data.message, 'danger');
                }
            } catch (error) {
                console.error('Matching Error:', error);
                showAlert('حدث خطأ غير متوقع.', 'danger');
            }
        });
    }
}