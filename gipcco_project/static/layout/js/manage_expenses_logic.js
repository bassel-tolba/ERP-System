function initManageExpensesLogic(container) {
  // =========================================================================
  //  NEW LOGIC FOR MANAGE EXPENSES PAGE
  // =========================================================================
  const editConsumptionModalEl = container.querySelector("#editConsumptionModal");
  if(editConsumptionModalEl) {
    if(editConsumptionModalEl.dataset.initialized) return;
    editConsumptionModalEl.dataset.initialized = 'true';

    editConsumptionModalEl.addEventListener("show.bs.modal", function (event) {
      const button = event.relatedTarget;
      const form = document.getElementById("editConsumptionForm");

      const pk = button.dataset.pk;
      // Use the URL from the global object
      form.action = window.appUrls.expensesConsumptionEdit.replace('<pk>', pk);

      document.getElementById("edit_c_product_name").textContent = button.dataset.productName;
      document.getElementById("edit_c_source_log").textContent = button.dataset.sourceLog;
      document.getElementById("edit_c_quantity").value = button.dataset.quantity;
      document.getElementById("edit_c_date").value = button.dataset.date;
      document.getElementById("edit_c_department").value = button.dataset.department;
      document.getElementById("edit_c_notes").value = button.dataset.notes;
    });
  }

  const editGeneralExpenseModalEl = container.querySelector("#editGeneralExpenseModal");
  if(editGeneralExpenseModalEl) {
    if(editGeneralExpenseModalEl.dataset.initialized) return;
    editGeneralExpenseModalEl.dataset.initialized = 'true';

    editGeneralExpenseModalEl.addEventListener("show.bs.modal", function (event) {
      const button = event.relatedTarget;
      const form = document.getElementById("editGeneralExpenseForm");

      const pk = button.dataset.pk;
      // Use the URL from the global object
      form.action = window.appUrls.expensesGeneralEdit.replace('<pk>', pk);

      document.getElementById("edit_g_description").value = button.dataset.description;
      document.getElementById("edit_g_amount").value = button.dataset.amount;
      document.getElementById("edit_g_date").value = button.dataset.date;
      document.getElementById("edit_g_category").value = button.dataset.category;
      document.getElementById("edit_g_classification").value = button.dataset.classification;
      document.getElementById("edit_g_notes").value = button.dataset.notes;

      // --- NEW: Set Cost Pool ---
      const costPoolSelect = document.getElementById("edit_g_cost_pool");
      if (costPoolSelect) {
          // Check if TomSelect is attached and use its API
          if (costPoolSelect.tomselect) {
              costPoolSelect.tomselect.setValue(button.dataset.costPoolId);
          } else {
              costPoolSelect.value = button.dataset.costPoolId;
          }
      }
    });
  }
}