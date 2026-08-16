function initLedgerLogic(container) {
  // ----- **MODIFIED** Logic for ledger.html -----
  const detailsModalEl = container.querySelector("#detailsModal");
  if (detailsModalEl) {
    if (detailsModalEl.dataset.ledgerInitialized) return;
    detailsModalEl.dataset.ledgerInitialized = "true";

    const detailsModal = new bootstrap.Modal(detailsModalEl);
    const batchDetailsModalEl = container.querySelector("#batchDetailsModal");
    const batchDetailsModal = batchDetailsModalEl ? new bootstrap.Modal(batchDetailsModalEl) : null;

    detailsModalEl.addEventListener("show.bs.modal", function (event) {
      const button = event.relatedTarget;
      const modal = this;
      const type = button.getAttribute("data-type");

      modal.querySelector("#modal-date").textContent = button.getAttribute("data-date");
      modal.querySelector("#modal-product").textContent = `${button.getAttribute("data-product-name")} (${button.getAttribute("data-product-code")})`;
      modal.querySelector("#modal-actual").textContent = button.getAttribute("data-actual-qty");

      const inDetails = modal.querySelectorAll(".in-details");
      const outDetails = modal.querySelectorAll(".out-details");
      const consumeDetails = modal.querySelectorAll(".consume-details");
      const batchBtnContainer = modal.querySelector("#batch-details-btn-container");

      inDetails.forEach((el) => (el.style.display = "none"));
      outDetails.forEach((el) => (el.style.display = "none"));
      consumeDetails.forEach((el) => (el.style.display = "none"));
      batchBtnContainer.classList.add('d-none');

      if (type === 'IN' || type === 'RETURN_IN') {
        inDetails.forEach((el) => (el.style.display = "table-row"));
        modal.querySelector("#detailsModalLabel").textContent = "تفاصيل حركة وارد";
        modal.querySelector("#modal-company").textContent = button.getAttribute("data-company-name");
        modal.querySelector("#modal-qc").textContent = button.getAttribute("data-qc-no");

      } else if (type === 'OUT') { // Production Consumption
        outDetails.forEach((el) => (el.style.display = "table-row"));
        modal.querySelector("#detailsModalLabel").textContent = "تفاصيل حركة منصرف (إنتاج)";
        const shopOrderCell = modal.querySelector("#modal-shop-order");
        const batchId = button.getAttribute("data-batch-id");
        const shopOrderNumber = button.getAttribute("data-shop-order-no");
        if (batchId) {
          shopOrderCell.innerHTML = `<a href="/batch/${batchId}/" title="عرض تفاصيل أمر التشغيل">${shopOrderNumber} <i class="bi bi-box-arrow-up-right small"></i></a>`;
          batchBtnContainer.classList.remove('d-none');
          const viewFullBatchAnalysisBtn = document.getElementById('viewFullBatchAnalysisBtn');
          if (viewFullBatchAnalysisBtn) {
            viewFullBatchAnalysisBtn.dataset.batchId = batchId;
          }
        } else {
          shopOrderCell.textContent = shopOrderNumber;
        }
        modal.querySelector("#modal-batch").textContent = button.getAttribute("data-batch-no");
        modal.querySelector("#modal-final-product").textContent = button.getAttribute("data-final-product");
        modal.querySelector("#modal-theoretical").textContent = button.getAttribute("data-theoretical-qty");

      } else if (type === 'CONSUME_OUT') { // NEW: Internal Consumption
        consumeDetails.forEach((el) => (el.style.display = "table-row"));
        modal.querySelector("#detailsModalLabel").textContent = "تفاصيل حركة منصرف (إداري)";
        modal.querySelector("#modal-department").textContent = button.getAttribute("data-department");
        modal.querySelector("#modal-notes").textContent = button.getAttribute("data-notes");
      }
    });

    const analysisBtn = container.querySelector("#viewFullBatchAnalysisBtn");
    if (analysisBtn) {
      analysisBtn.addEventListener('click', async function() {
        const batchId = this.dataset.batchId;
        if (!batchId) return;

        const loadingEl = batchDetailsModalEl.querySelector('#batch-analysis-content-loading');
        const mainEl = batchDetailsModalEl.querySelector('#batch-analysis-content-main');
        const tbody = batchDetailsModalEl.querySelector('#ba-raw-materials-tbody');

        loadingEl.classList.remove('d-none'); mainEl.classList.add('d-none'); tbody.innerHTML = '';
        try {
          // Use the URL from the global object
          const response = await fetch(window.appUrls.apiBatchDetails.replace('<batchId>', batchId)); // This URL also works for batch_analysis, assuming backend handles it
          const data = await response.json();
          if (response.ok) {
            mainEl.querySelector('#ba-so-num').textContent = data.shop_order_number;
            mainEl.querySelector('#ba-batch-num').textContent = data.batch_number;
            mainEl.querySelector('#ba-date').textContent = new Date(data.creation_date).toLocaleDateString('en-CA');
            mainEl.querySelector('#ba-final-prod').textContent = data.final_product_name;
            mainEl.querySelector('#ba-total-cost').textContent = parseFloat(data.summary.total_raw_material_cost).toFixed(3);
            mainEl.querySelector('#ba-total-produced').textContent = `${parseFloat(data.summary.total_quantity_produced).toFixed(0)} ${data.final_product_unit}`;
            mainEl.querySelector('#ba-avg-cost').textContent = parseFloat(data.summary.average_cost_per_unit).toFixed(3);

            tbody.innerHTML = '';
            data.raw_materials_used.forEach(item => {
              const row = document.createElement('tr');
              row.innerHTML = `
                <td>${item.product_name}</td>
                <td>${item.qc_no || 'N/A'}</td>
                <td>${parseFloat(item.theoretical_quantity).toFixed(3)}</td>
                <td>${parseFloat(item.actual_quantity).toFixed(3)}</td>
                <td>${parseFloat(item.cost_per_unit).toFixed(3)}</td>
                <td>${parseFloat(item.total_cost).toFixed(3)}</td>
              `;
              tbody.appendChild(row);
            });

            loadingEl.classList.add('d-none');
            mainEl.classList.remove('d-none');
            batchDetailsModal.show();
          } else { throw new Error(data.error); }
        } catch (error) {
          mainEl.innerHTML = `<div class="alert alert-danger">فشل تحميل بيانات التحليل.</div>`;
          loadingEl.classList.add('d-none');
        }
      });
    }
  }
}