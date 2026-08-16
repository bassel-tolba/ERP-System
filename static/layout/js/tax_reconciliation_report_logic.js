function initTaxReconciliationReportLogic(container) {
    const form = container.querySelector('#taxReportForm');
    if (!form) return;

    form.addEventListener('submit', function(event) {
        event.preventDefault();
        const formData = new FormData(form);
        const params = new URLSearchParams(formData);
        const url = `${form.action}?${params.toString()}`;
        
        // This assumes you have a global function `loadContent` from `dynamic_content_loader.js`
        // that handles fetching and injecting the content.
        if (window.loadContent) {
            window.loadContent(url);
        } else {
            // Fallback if the dynamic loader isn't available
            window.location.href = url;
        }
    });
}
