function initBatchViewLogic(container) {
  // ----- Logic for batch_view.html -----
  const batchViewForm = container.querySelector("#batchEditForm");
  if (batchViewForm) {
    console.log("Initializing FULL batch_view.html dynamic logic...");

    const continuationCheckEdit = container.querySelector('#isContinuationSwitch');
    const parentBatchContainerEdit = container.querySelector('#parent_batch_container_edit');
    const parentBatchSelectEl = container.querySelector('#parent_batch_edit');
    const shopOrderInputEdit = container.querySelector('input[name="shop_order_number"]');

    const batchFromInput = container.querySelector("#batch_number_from");
    const batchToInput = container.querySelector("#batch_number_to");
    const materialsTbody = container.querySelector("#materials_tbody");
    const batchItemsTable = container.querySelector('#batchItemsTable');

    if (continuationCheckEdit && parentBatchContainerEdit && parentBatchSelectEl) {
      const parentBatchSelect = parentBatchSelectEl.tomselect;

      continuationCheckEdit.addEventListener('change', function() {
        if (this.checked) {
          parentBatchContainerEdit.style.display = 'block';
          if(parentBatchSelect) parentBatchSelect.enable();
        } else {
          parentBatchContainerEdit.style.display = 'none';
          if (parentBatchSelect) {
            parentBatchSelect.clear();
            parentBatchSelect.disable();
          }
        }
      });
      
      // --- START: ADDED AUTO-FILL LOGIC ---
      if (parentBatchSelect && shopOrderInputEdit) {
        parentBatchSelect.on('change', async function(parentBatchId) {
          if (!parentBatchId) return; // Do nothing if selection is cleared
          try {
            const apiUrl = window.appUrls.apiBatchDetails.replace('<batchId>', parentBatchId);
            const response = await fetch(apiUrl);
            if (!response.ok) throw new Error('Batch details not found');
            const data = await response.json();
            // Automatically update the Shop Order number to match the selected parent
            shopOrderInputEdit.value = data.shop_order_number;
          } catch (error) {
            console.error('Failed to fetch parent batch details for editing:', error);
            alert('خطأ في تحميل بيانات الأمر الأصلي.');
          }
        });
      }
      // --- END: ADDED AUTO-FILL LOGIC ---

      // Initialize state on load
      if (continuationCheckEdit.checked) {
        if(parentBatchSelect) parentBatchSelect.enable();
      } else {
        if(parentBatchSelect) parentBatchSelect.disable();
      }
    }

    if(batchFromInput && batchToInput && materialsTbody) {
      const getNumBatches = () => {
        const fromVal = parseInt(batchFromInput.value) || 0;
        const toVal = parseInt(batchToInput.value) || fromVal;
        return fromVal > 0 && toVal >= fromVal
          ? toVal - fromVal + 1
          : fromVal > 0
            ? 1
            : 0;
      };

      const recalculateAllQuantities = () => {
        const numBatches = getNumBatches();
        materialsTbody.querySelectorAll("tr").forEach((row) => {
          const theoreticalInput = row.querySelector(".theoretical-qty");
          const actualInput = row.querySelector(".actual-qty");

          const baseTheoretical = parseFloat(theoreticalInput.dataset.baseTheoreticalQuantity);
          if (!isNaN(baseTheoretical)) {
            const totalTheoretical = numBatches > 0 ? baseTheoretical * numBatches : 0;
            theoreticalInput.value = totalTheoretical.toFixed(3);
          }

          const baseActual = parseFloat(actualInput.dataset.baseActualQuantity);
          if (!isNaN(baseActual)) {
            const totalActual = numBatches > 0 ? baseActual * numBatches : 0;
            actualInput.value = totalActual.toFixed(3);
          }
        });
      };

      if (!batchFromInput.dataset.recalcInitialized) {
        batchFromInput.addEventListener("input", recalculateAllQuantities);
        batchToInput.addEventListener("input", recalculateAllQuantities);
        batchFromInput.dataset.recalcInitialized = 'true';
      }
    }

    if (batchItemsTable && !batchItemsTable.dataset.deleteInitialized) {
      batchItemsTable.dataset.deleteInitialized = 'true';
      batchItemsTable.addEventListener('click', function(event) {
        const deleteButton = event.target.closest('.delete-item-btn');
        if (deleteButton) {
          event.preventDefault();
          if (confirm('هل أنت متأكد من حذف هذه المادة؟ لا يمكن التراجع عن هذا الإجراء وسيتم تحديث التكاليف.')) {
            const form = document.getElementById('deleteItemForm');
            if (form) {
              // The form.action needs to be set dynamically from data-form-action
              // Make sure your Django template for batch_view.html provides this attribute correctly.
              form.action = deleteButton.dataset.formAction;
              form.submit();
            }
          }
        }
      });
    }
  }
}