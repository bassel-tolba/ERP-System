//gipcco_project\static\layout\js\receive_finished_product_logic.js
function initReceiveFinishedProductLogic(container) {
  // =========================================================================
  //  NEW JAVASCRIPT FOR RECEIVE FINISHED PRODUCT PAGE
  // =========================================================================
  const addSubBatchBtn = container.querySelector('#add-sub-batch-btn');
  if (addSubBatchBtn && !addSubBatchBtn.dataset.logicInitialized) {
    console.log("Initializing receive_finished_product.html dynamic logic...");
    addSubBatchBtn.dataset.logicInitialized = 'true';

    const subBatchesTbody = container.querySelector('#sub-batches-tbody');

    // Function to create a new row
    const createSubBatchRow = () => {
      const row = document.createElement('tr');
      row.innerHTML = `
        <td class="ps-3">
            <input type="text" name="sub_batch_id" class="form-control" placeholder="مثال: A2, P-002" required>
        </td>
        <td>
            <input type="number" step="any" name="sub_batch_qty" class="form-control text-center" required>
        </td>
        <td class="text-center pe-2">
            <button type="button" class="btn btn-sm btn-outline-danger remove-sub-batch-btn" title="حذف الصف">
                <i class="bi bi-trash"></i>
            </button>
        </td>
      `;
      subBatchesTbody.appendChild(row);
    };

    // Add row button event
    addSubBatchBtn.addEventListener('click', createSubBatchRow);

    // Use event delegation for remove buttons
    subBatchesTbody.addEventListener('click', function(e) {
      const removeBtn = e.target.closest('.remove-sub-batch-btn');
      if (removeBtn) {
        removeBtn.closest('tr').remove();
      }
    });
  }
}