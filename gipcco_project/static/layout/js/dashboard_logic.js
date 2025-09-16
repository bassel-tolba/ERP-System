function initDashboardLogic(container) {
  // --- A. Logic for dashboard.html (Add New Record Form) ---
  const dashboardProductSelectEl = container.querySelector('#product_id');
  const dashboardTagsSelectEl = container.querySelector('#tags');
  // Check if the form is for the index page using its action or a specific ID
  const dashboardForm = container.querySelector('form[action="/"]'); // Or a more specific selector
  if (dashboardProductSelectEl && dashboardTagsSelectEl && dashboardForm) {
    if (!dashboardProductSelectEl.dataset.tagsInitialized) {
      console.log("Initializing dashboard dynamic tags logic...");
      dashboardProductSelectEl.dataset.tagsInitialized = 'true';

      // Use the URL from the global object
      const tagsUrlTemplate = window.appUrls.apiProductTags;

      const productSelect = dashboardProductSelectEl.tomselect || new TomSelect(dashboardProductSelectEl, { placeholder: 'ابحث عن منتج...' });
      const companySelectEl = container.querySelector('#company_id');
      const companySelect = companySelectEl.tomselect || new TomSelect(companySelectEl, { placeholder: 'ابحث عن شركة...' });
      const tagsSelect = dashboardTagsSelectEl.tomselect || new TomSelect(dashboardTagsSelectEl, {
        plugins: ['remove_button'],
        placeholder: 'اختر الوسوم المناسبة'
      });
      tagsSelect.disable();

      window.updateTagsForProduct = function(productId) {
        console.log(`[TAGS] Updating tags for product ID: ${productId}`);
        tagsSelect.disable();
        tagsSelect.clear();
        tagsSelect.clearOptions();

        if (productId) {
          const finalUrl = tagsUrlTemplate.replace('0', productId);
          fetch(finalUrl)
            .then(response => response.json())
            .then(data => {
              data.tags.forEach(tag => tagsSelect.addOption({value: tag.id, text: tag.name}));
              tagsSelect.enable();
            })
            .catch(error => console.error('Error fetching dashboard tags:', error));
        }
      }

      productSelect.on('change', function(productId) {
        window.updateTagsForProduct(productId);
      });
    }
  }

  // =========================================================================
  //  **MODIFIED** Logic for dashboard.html (PO Workflow)
  // =========================================================================
  const poCheck = container.querySelector('#receiveAgainstPoCheck');
  if (poCheck && !poCheck.dataset.poLogicInitialized) {
    console.log('[DEBUG] 1. Initializing PO workflow logic...');
    poCheck.dataset.poLogicInitialized = 'true';

    try {
      const poContainer = container.querySelector('#po-fields-container');
      const manualPriceContainer = container.querySelector('#manual-price-container');
      const poSupplierSelectEl = container.querySelector('#po_supplier_id');
      const poSelectEl = container.querySelector('#purchase_order_id');
      const poItemSelectEl = container.querySelector('#po_item_id');
      const mainProductSelect = container.querySelector('#product_id').tomselect;
      const mainCompanySelect = container.querySelector('#company_id').tomselect;
      const quantityInput = container.querySelector('#quantity');
      const basePriceInput = container.querySelector('#base_unit_price');
      const vatAmountInput = container.querySelector('#vat_amount');

      console.log('[DEBUG] 2. All required elements found.');

      const poSupplierSelect = poSupplierSelectEl.tomselect;
      const poSelect = poSelectEl.tomselect;
      const poItemSelect = poItemSelectEl.tomselect;

      poCheck.addEventListener('change', function() {
        if (this.checked) {
          poContainer.style.display = 'block';
          manualPriceContainer.style.display = 'none';
          basePriceInput.required = false;
          vatAmountInput.required = false;
          mainProductSelect.lock();
          mainCompanySelect.lock();
        } else {
          poContainer.style.display = 'none';
          manualPriceContainer.style.display = 'block';
          basePriceInput.required = true;
          vatAmountInput.required = true;
          mainProductSelect.unlock();
          mainCompanySelect.unlock();
          poSupplierSelectEl.tomselect.clear();
        }
      });

      console.log('[DEBUG] 3. Attaching event listeners...');

      // --- SUPPLIER CHANGE EVENT ---
      poSupplierSelect.on('change', function(supplierId) {
        console.log(`[DEBUG] EVENT: Supplier changed! New ID: ${supplierId}`);
        poSelect.clear(); poSelect.clearOptions(); poSelect.disable();
        poItemSelect.clear(); poItemSelect.clearOptions(); poItemSelect.disable();

        if (supplierId) {
          // Use the URL from the global object
          const apiUrl = window.appUrls.apiSupplierOpenPos.replace('<supplierId>', supplierId);
          fetch(apiUrl)
            .then(res => res.json())
            .then(data => {
              poSelect.clear(); poSelect.enable();
              if (data.length > 0) {
                data.forEach(po => poSelect.addOption({value: po.id, text: `${po.po_number} (${po.order_date})`}));
              } else {
                poSelect.addOption({value: '', text: 'لا توجد أوامر شراء مفتوحة'});
              }
            });
        }
      });

      // --- PURCHASE ORDER CHANGE EVENT ---
      poSelect.on('change', function(poId) {
        console.log(`[DEBUG] EVENT: PO changed! New ID: ${poId}`);
        poItemSelect.clear(); poItemSelect.clearOptions(); poItemSelect.disable();

        if (poId) {
          // Use the URL from the global object
          const apiUrl = window.appUrls.apiPoItems.replace('<poId>', poId);
          fetch(apiUrl)
            .then(res => res.json())
            .then(data => {
              poItemSelect.clear(); poItemSelect.enable();
              if (data.length > 0) {
                data.forEach(item => {
                  poItemSelect.addOption({
                    value: item.id,
                    text: `${item.product_name} | متبقي: ${item.quantity_remaining}`,
                    'data-product-id': item.product_id,
                    'data-quantity': item.quantity_remaining,
                    'data-base-price': item.base_price_per_unit,
                    'data-vat-rate': item.vat_rate,
                    'data-wht-rate': item.withholding_tax_rate,
                  });
                });
              } else {
                poItemSelect.addOption({value: '', text: 'لا توجد مواد متبقية'});
              }
            });
        }
      });

      // --- PO ITEM CHANGE EVENT ---
      poItemSelect.on('change', function(itemId) {
        console.log(`[DEBUG] EVENT: PO Item changed! New ID: ${itemId}`);
        const selectedOption = this.options[itemId];
        if (itemId && selectedOption) {
          const productId = selectedOption['data-product-id'];
          mainProductSelect.setValue(productId, true);
          mainCompanySelect.setValue(poSupplierSelect.getValue(), true);
          quantityInput.value = selectedOption['data-quantity'];
          // Set VAT and WHT display fields (rates are fractions, display as %)
          const vatRateEl = container.querySelector('#po_vat_rate');
          const whtRateEl = container.querySelector('#po_wht_rate');
          if (vatRateEl) {
            const vr = parseFloat(selectedOption['data-vat-rate']);
            vatRateEl.value = isFinite(vr) ? (vr * 100).toFixed(2) : '';
          }
          if (whtRateEl) {
            const wr = parseFloat(selectedOption['data-wht-rate']);
            whtRateEl.value = isFinite(wr) ? (wr * 100).toFixed(2) : '';
          }
          if (window.updateTagsForProduct) {
            window.updateTagsForProduct(productId);
          }
        } else {
          mainProductSelect.clear();
          mainCompanySelect.clear();
          quantityInput.value = '';
          const vatRateEl = container.querySelector('#po_vat_rate');
          const whtRateEl = container.querySelector('#po_wht_rate');
          if (vatRateEl) vatRateEl.value = '';
          if (whtRateEl) whtRateEl.value = '';
        }
      });

      console.log('[DEBUG] 4. Event listeners attached successfully.');

    } catch (error) {
      console.error('[DEBUG] A critical error occurred inside the PO workflow block:', error);
    }
  }
}