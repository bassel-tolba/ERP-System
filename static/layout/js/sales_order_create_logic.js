// static/layout/js/sales_order_create_logic.js

function initSalesOrderCreateLogic(container) {
  // 1. The "Gatekeeper" check: Find the single most important element for this page.
  const addItemBtn = container.querySelector("#add-so-item-btn");

  // 2. The main 'if' block. If the button doesn't exist, this function does nothing.
  if (addItemBtn) {
    
    // 3. The Re-initialization Guard: Check if we've already run this logic.
    if (!addItemBtn.dataset.soLogicInitialized) {
      
      // --- DEBUG: This is the FIRST message you should see now ---
      console.log('%c[SalesOrderCreate] Initializing logic on #add-so-item-btn...', 'color: #007bff; font-weight: bold;');
      
      // Mark as initialized to prevent re-running.
      addItemBtn.dataset.soLogicInitialized = 'true';

      const itemTableBody = container.querySelector("#so-items-tbody");
      
      if (!itemTableBody) {
          console.error('[SalesOrderCreate] CRITICAL: Found the add button but not the table body #so-items-tbody. Halting.');
          return;
      }
      
      let availableStock = [];

      async function fetchSellableStock() {
          const url = window.appUrls.apiGetSellableStock;
          console.log(`[SalesOrderCreate] Starting fetchSellableStock from URL: ${url}`);
          
          try {
              const response = await fetch(url);
              if (!response.ok) {
                  console.error(`[SalesOrderCreate] API request failed with status: ${response.status}`);
                  throw new Error(`HTTP error! status: ${response.status}`);
              }
              const data = await response.json();
              availableStock = data.map(item => ({
                  value: item.id,
                  text: `${item.product_name} | تشغيلة: ${item.batch_number} | متاح: ${item.available_quantity} ${item.unit}`,
                  available_qty: item.available_quantity
              }));
              console.info(`%c[SalesOrderCreate] Successfully fetched ${availableStock.length} stock items.`, 'color: #2ecc71;');
          } catch (error) {
              console.error("[SalesOrderCreate] Failed to load sellable stock:", error);
              alert("فشل تحميل مخزون المنتجات الجاهزة. الرجاء تحديث الصفحة.");
          }
      }

      function createItemRow() {
          console.log('[SalesOrderCreate] createItemRow() called.');
          const newRow = itemTableBody.insertRow();
          newRow.innerHTML = `
              <td class="ps-3">
                  <select name="receipt_id" class="form-select so-item-select" placeholder="ابحث عن منتج/تشغيلة..." required></select>
              </td>
              <td>
                  <input type="number" step="any" name="quantity" class="form-control quantity-input" required>
                  <div class="form-text text-muted small available-qty-text"></div>
              </td>
              <td>
                  <input type="number" step="any" name="base_price_per_unit" class="form-control" placeholder="السعر الأساسي" required>
              </td>
              <td>
                   <div class="input-group">
                      <input type="number" step="any" name="vat_rate" class="form-control" value="14" placeholder="الضريبة" required>
                      <span class="input-group-text">%</span>
                  </div>
              </td>
              <td class="text-center pe-2">
                  <button type="button" class="btn btn-sm btn-outline-danger remove-item-btn" title="حذف البند">
                      <i class="bi bi-trash"></i>
                  </button>
              </td>
          `;
          
          const selectEl = newRow.querySelector('.so-item-select');
          console.log('[SalesOrderCreate] Initializing TomSelect on new row.');

          new TomSelect(selectEl, {
              options: availableStock,
              create: false,
              placeholder: "          ابحث عن منتج/تشغيلة...",
              dropdownParent: 'body',
              rtl: true
          });
          // Note: Event listener for TomSelect change is omitted for brevity, it's inside createItemRow
      }

      console.log('[SalesOrderCreate] Attaching event listeners for add/remove buttons.');
      addItemBtn.addEventListener("click", createItemRow);
      itemTableBody.addEventListener("click", function (e) {
          if (e.target.closest(".remove-item-btn")) {
              console.log('[SalesOrderCreate] Remove item button clicked.');
              const row = e.target.closest("tr");
              const select = row.querySelector('.so-item-select');
              if (select && select.tomselect) {
                  select.tomselect.destroy();
              }
              row.remove();
          }
      });

      console.log('[SalesOrderCreate] Kicking off initial data fetch...');
      fetchSellableStock().then(() => {
          console.log('[SalesOrderCreate] Data fetch complete. Creating initial item row.');
          if (itemTableBody.rows.length === 0) {
              createItemRow();
          }
      });
    }
  }
}