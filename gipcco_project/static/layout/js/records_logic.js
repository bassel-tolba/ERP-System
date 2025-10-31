function initRecordsLogic(container) {
  // =========================================================
  //  **NEW**: Logic for records.html (View Record Modal)
  // =========================================================
  const viewModal = container.querySelector("#viewRecordModal");
  if (viewModal) {
      viewModal.addEventListener("show.bs.modal", function (event) {
          const button = event.relatedTarget;
          if (!button) return;

          const setData = (id, value) => {
              const el = viewModal.querySelector(`#view-${id}`);
              if (el) el.textContent = value || 'N/A';
          };

          setData('product-name', button.dataset.productName);
          setData('product-code', button.dataset.productCode);
          setData('company-name', button.dataset.companyName);
          setData('po-number', button.dataset.poNumber);
          setData('quantity', `${button.dataset.quantity} ${button.dataset.unit}`);
          setData('status-display', button.dataset.statusDisplay);
          setData('qc-no', button.dataset.qcNo);
          setData('entry-date', button.dataset.entryDate);
          setData('release-date', button.dataset.releaseDate);
          setData('base-unit-price', button.dataset.baseUnitPrice);
          setData('vat-amount', button.dataset.vatAmount);
          setData('wht-amount', button.dataset.whtAmount);
          setData('vat-treatment-display', button.dataset.vatTreatmentDisplay);
          
          const tags = button.dataset.tags.split(',').filter(Boolean).join(', ') || 'N/A';
          setData('tags', tags);
      });
  }

  // --- Logic for Void Record Modal ---
  const voidModal = container.querySelector('#voidRecordModal');
  if (voidModal) {
    voidModal.addEventListener('show.bs.modal', function (event) {
      const button = event.relatedTarget;
      const logId = button.getAttribute('data-log-id');
      const logInfo = button.getAttribute('data-log-info');
      
      const form = voidModal.querySelector('#voidRecordForm');
      const infoElement = voidModal.querySelector('#voidRecordInfo');
      
      form.action = window.appUrls.voidRecord.replace('0', logId);
      infoElement.textContent = logInfo;
    });
  }

  // --- Logic for Inventory Log History Modal ---
  const historyModal = container.querySelector('#logHistoryModal');
  if (historyModal) {
      const loader = historyModal.querySelector('#history-loader');
      const content = historyModal.querySelector('#history-content');
      const logInfoEl = historyModal.querySelector('#history-log-info');
      const tableBody = historyModal.querySelector('#history-table-body');

      container.querySelectorAll('.history-btn').forEach(button => {
          button.addEventListener('click', async function() {
              const logId = this.getAttribute('data-log-id');
              const modal = new bootstrap.Modal(historyModal);
              
              // Show loader, hide content
              loader.style.display = 'block';
              content.style.display = 'none';
              tableBody.innerHTML = '';
              
              modal.show();

              try {
                  const response = await fetch(window.appUrls.apiGetInventoryLogHistory.replace('0', logId));
                  const data = await response.json();
                  
                  logInfoEl.textContent = `History for ${data.product_name} (QC: ${data.qc_no}) - Initial Quantity: ${data.initial_quantity}`;

                  data.history.forEach(item => {
                      const row = tableBody.insertRow();
                      row.innerHTML = `
                          <td>${new Date(item.date).toLocaleDateString()}</td>
                          <td>${item.type}</td>
                          <td class="font-monospace ${item.quantity > 0 ? 'text-success' : 'text-danger'}">${item.quantity.toFixed(3)}</td>
                          <td>${item.description}</td>
                          <td>${item.reference || ''}</td>
                      `;
                  });

              } catch (error) {
                  console.error('Failed to load inventory log history:', error);
                  tableBody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Failed to load history.</td></tr>';
              } finally {
                  // Hide loader, show content
                  loader.style.display = 'none';
                  content.style.display = 'block';
              }
          });
      });
  }
}