function initRecordsLogic(container) {
  // =========================================================
  //  **MODIFIED**: Logic for records.html (Edit Record Modal)
  // =========================================================
  const editModal = container.querySelector("#editRecordModal");
  if (editModal && !editModal.dataset.poLogicInitialized) {
    console.log("Initializing Edit Record Modal PO logic...");
    editModal.dataset.poLogicInitialized = 'true';

    const mainProductSelect = new TomSelect('#editProductId');
    const mainCompanySelect = new TomSelect('#editCompanyId');
    const manualPriceContainer = document.getElementById('edit-manual-price-container');
    const basePriceInput = document.getElementById('editBaseUnitPrice');
    const vatAmountInput = document.getElementById('editVatAmount');
    const vatTreatmentSelect = document.getElementById('editVatTreatment');

    const linkPoCheck = document.getElementById('editLinkToPoCheck');
    const poFieldsContainer = document.getElementById('edit-po-fields-container');
    const poSupplierSelect = new TomSelect('#edit_po_supplier_id', { placeholder: 'اختر مورد...' });
    const poSelect = new TomSelect('#edit_purchase_order_id', { placeholder: 'اختر أمر شراء...' });
    const poItemSelect = new TomSelect('#edit_po_item_id', { placeholder: 'اختر المادة...' });

    // Use the URL from the global object
    const tagsUrlTemplate = window.appUrls.apiProductTags;
    const recordsEditUrlTemplate = window.appUrls.recordsEdit;

    const tagsSelect = new TomSelect('#editTags', { plugins: ['remove_button'] });

    const fetchAndSetTags = async (productId, selectedTagIds = []) => {
      tagsSelect.disable(); tagsSelect.clear(); tagsSelect.clearOptions();
      if (!productId) return;
      try {
        const response = await fetch(tagsUrlTemplate.replace('0', productId));
        const data = await response.json();
        data.tags.forEach(tag => tagsSelect.addOption({ value: tag.id, text: tag.name }));
        tagsSelect.enable();
        if (selectedTagIds.length > 0) tagsSelect.setValue(selectedTagIds);
      } catch (error) { console.error('Error fetching modal tags:', error); }
    };

    const togglePoFields = (isLinked) => {
      if (isLinked) {
        poFieldsContainer.style.display = 'block';
        manualPriceContainer.style.display = 'none';
        basePriceInput.required = false;
        vatAmountInput.required = false;
        mainProductSelect.lock();
        mainCompanySelect.lock();
      } else {
        poFieldsContainer.style.display = 'none';
        manualPriceContainer.style.display = 'block';
        basePriceInput.required = true;
        vatAmountInput.required = true;
        mainProductSelect.unlock();
        mainCompanySelect.unlock();
        poSupplierSelect.clear();
      }
    };

    const loadPOs = async (supplierId) => {
      poSelect.clear(); poSelect.clearOptions(); poSelect.disable();
      if (!supplierId) return;
      try {
        // Use the URL from the global object
        const response = await fetch(window.appUrls.apiSupplierOpenPos.replace('<supplierId>', supplierId));
        const data = await response.json();
        data.forEach(po => poSelect.addOption({value: po.id, text: `${po.po_number} (${po.order_date})`}));
        poSelect.enable();
      } catch (error) { console.error("Failed to load POs:", error); }
    };

    const loadPOItems = async (poId) => {
      poItemSelect.clear(); poItemSelect.clearOptions(); poItemSelect.disable();
      if (!poId) return;
      try {
        // Use the URL from the global object
        const response = await fetch(window.appUrls.apiPoItems.replace('<poId>', poId));
        const data = await response.json();
        data.forEach(item => poItemSelect.addOption({
          value: item.id,
          text: `${item.product_name} | متبقي: ${item.quantity_remaining}`,
          'data-product-id': item.product_id
        }));
        poItemSelect.enable();
      } catch (error) { console.error("Failed to load PO Items:", error); }
    };

    linkPoCheck.addEventListener('change', (e) => togglePoFields(e.target.checked));
    mainProductSelect.on('change', (productId) => fetchAndSetTags(productId));
    poSupplierSelect.on('change', (supplierId) => loadPOs(supplierId));
    poSelect.on('change', (poId) => loadPOItems(poId));
    poItemSelect.on('change', (itemId) => {
      const selectedOption = poItemSelect.options[itemId];
      if (itemId && selectedOption) {
        const productId = selectedOption['data-product-id'];
        mainProductSelect.setValue(productId, true);
        mainCompanySelect.setValue(poSupplierSelect.getValue(), true);
        fetchAndSetTags(productId);
      }
    });

    editModal.addEventListener("show.bs.modal", async function (event) {
      const button = event.relatedTarget;
      if (!button) return;

      linkPoCheck.checked = false;
      togglePoFields(false);
      poSupplierSelect.clear();
      poSelect.clear();
      poItemSelect.clear();

      const logId = button.getAttribute("data-log-id");
      const productId = button.getAttribute("data-product-id");
      const companyId = button.getAttribute("data-company-id");
      const tagIds = button.getAttribute('data-tag-ids').split(',').filter(Boolean);

      // Use the URL from the global object
      document.getElementById("editRecordForm").action = recordsEditUrlTemplate.replace('<logId>', logId);
      document.getElementById("editQuantity").value = button.getAttribute("data-quantity");
      document.getElementById("editEntryDate").value = button.getAttribute("data-entry-date");
      basePriceInput.value = button.getAttribute("data-base-unit-price");
      vatAmountInput.value = button.getAttribute("data-vat-amount");
      vatTreatmentSelect.value = button.getAttribute("data-vat-treatment");

      mainProductSelect.setValue(productId, true);
      mainCompanySelect.setValue(companyId, true);
      await fetchAndSetTags(productId, tagIds);

      const poItemId = button.getAttribute("data-po-item-id");
      if (poItemId) {
        const supplierId = button.getAttribute("data-supplier-id");
        const poId = button.getAttribute("data-po-id");

        linkPoCheck.checked = true;
        togglePoFields(true);

        poSupplierSelect.setValue(supplierId);
        await loadPOs(supplierId);

        if (!poSelect.options[poId]) {
          poSelect.addOption({value: poId, text: `أمر شراء #${poId} (مغلق)`});
        }
        poSelect.setValue(poId);

        await loadPOItems(poId);

        if (!poItemSelect.options[poItemId]) {
          poItemSelect.addOption({value: poItemId, text: 'البند الحالي (مستلم بالكامل)'});
        }
        poItemSelect.setValue(poItemId);
      }
    });
  }

  // --- NEW: Logic for Void Record Modal ---
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

  // --- NEW: Logic for Inventory Log History Modal ---
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