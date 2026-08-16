//gipcco_project\static\layout\js\shop_order_templates_logic.js

function initShopOrderTemplatesLogic(container) {
  // ----- Logic for shop_order_templates.html (Add/Copy Modal) -----
  const addTemplateModalEl =
    container.querySelector("#addTemplateModal");
  if (addTemplateModalEl) {
    console.log(
      "Initializing shop_order_templates.html modal logic..."
    );
    // Use a flag on the modal element itself, or the container, to prevent re-initialization
    if (addTemplateModalEl.dataset.initialized) return;
    addTemplateModalEl.dataset.initialized = 'true';


    const itemsContainer = addTemplateModalEl.querySelector(
      "#template-items-container"
    );
    const addItemBtn =
      addTemplateModalEl.querySelector("#add-item-btn");
    const primitiveProducts =
      window.getDataFromIsland("primitive-products-data", container) || [];
    const addTemplateModal = new bootstrap.Modal(addTemplateModalEl); // Ensure bootstrap.Modal is available
    const sourceTemplate =
      window.getDataFromIsland("source-template-data", container) || null;
    const sourceItems = window.getDataFromIsland("source-items-data", container) || [];

    function createItemRow(productId = "", quantity = "") {
      const row = document.createElement("div");
      row.className =
        "row g-3 align-items-center mb-3 template-item-row";
      const productCol = document.createElement("div");
      productCol.className = "col-md-7";
      const select = document.createElement("select");
      select.name = "primitive_product_id";
      select.className = "form-select";
      select.required = true;
      let options =
        '<option value="">اختر مادة خام أو تعبئة...</option>';
      primitiveProducts.forEach((p) => {
        const isSelected = p.id == productId ? "selected" : "";
        options += `<option value="${p.id}" ${isSelected}>${p.name} (${p.code})</option>`;
      });
      select.innerHTML = options;
      productCol.appendChild(select);
      const qtyCol = document.createElement("div");
      qtyCol.className = "col-md-4";
      const qtyInput = document.createElement("input");
      qtyInput.type = "number";
      qtyInput.step = "any";
      qtyInput.name = "theoretical_quantity";
      qtyInput.className = "form-control";
      qtyInput.placeholder = "الكمية النظرية";
      qtyInput.value = quantity;
      qtyInput.required = true;
      qtyCol.appendChild(qtyInput);
      const removeCol = document.createElement("div");
      removeCol.className = "col-md-1";
      const removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn btn-sm btn-outline-danger";
      removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
      removeBtn.onclick = () => row.remove();
      removeCol.appendChild(removeBtn);
      row.appendChild(productCol);
      row.appendChild(qtyCol);
      row.appendChild(removeCol);
      itemsContainer.appendChild(row);
      new TomSelect(select, {
        create: false,
        sortField: { field: "text", direction: "asc" },
      });
    }

    addItemBtn.addEventListener("click", () => createItemRow());

    addTemplateModalEl.addEventListener("show.bs.modal", () => {
      itemsContainer.innerHTML = "";
      let isCopying = window.getDataFromIsland("source-template-data", container) != null; // Check if we should be in copy mode
      if (isCopying) {
        const sourceTpl = window.getDataFromIsland("source-template-data", container);
        const sourceItms = window.getDataFromIsland("source-items-data", container) || [];
        addTemplateModalEl.querySelector(
          "#addTemplateModalLabel"
        ).innerText = "إنشاء قالب جديد من نسخة";
        addTemplateModalEl.querySelector(
          "#template_name_input"
        ).value = `نسخة من - ${sourceTpl.name}`;
        addTemplateModalEl.querySelector(
          "#bottle_size_ml_input"
        ).value = sourceTpl.bottle_size_ml || "";
        if (sourceItms && sourceItms.length > 0) {
          sourceItms.forEach((item) => {
            createItemRow(
              item.primitive_product_id,
              item.theoretical_quantity
            );
          });
        } else {
          createItemRow();
        }
        // Important: Erase the data island content after use to prevent re-copying on next modal open
        const island1 = document.getElementById("source-template-data");
        if (island1) island1.textContent = "";
        const island2 = document.getElementById("source-items-data");
        if (island2) island2.textContent = "";
      } else {
        addTemplateModalEl.querySelector(
          "#addTemplateModalLabel"
        ).innerText = "إنشاء قالب جديد";
        addTemplateModalEl.querySelector("form").reset();
        addTemplateModalEl
          .querySelectorAll(".searchable-select")
          .forEach((sel) => {
            if (sel.tomselect) sel.tomselect.clear();
          });
        createItemRow();
      }
    });

    if (sourceTemplate) {
      addTemplateModal.show();
    }
  } else {
    // If the modal isn't present, ensure the flag is reset for potential future dynamic loads
    // This part should technically not be in the `else` of the modal check if it's dynamic
    // The `dataset.initialized` check inside `if (addTemplateModalEl)` handles re-initialization.
    // document.body.removeAttribute("data-templates-page-initialized"); // Removed as it was on body
  }
}