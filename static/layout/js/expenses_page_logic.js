function initExpensesPageLogic(container) {
  // --- LOGIC FOR EXPENSES PAGE ---
  const consumptionForm = container.querySelector('#consumptionForm');
  if (consumptionForm) {
    if (consumptionForm.dataset.initialized) return;
    consumptionForm.dataset.initialized = 'true';

    const productSelectEl = consumptionForm.querySelector('#product_id');
    const productSelect = productSelectEl.tomselect || new TomSelect(productSelectEl, {
      placeholder: 'اختر قطعة غيار أو مستهلك...'
    });
    const sourceSelectEl = consumptionForm.querySelector('#source_log_id');
    const sourceSelect = sourceSelectEl.tomselect || new TomSelect(sourceSelectEl, { placeholder: 'اختر مصدر...' });
    const quantityInput = consumptionForm.querySelector('#quantity_consumed');
    const maxHelpText = consumptionForm.querySelector('#maxConsumableHelp');

    productSelect.on('change', async function(productId) {
      sourceSelect.clear();
      sourceSelect.clearOptions();
      sourceSelect.disable();
      quantityInput.removeAttribute('max');
      maxHelpText.textContent = '';

      if (!productId) return;

      try {
        // Use the URL from the global object
        const response = await fetch(window.appUrls.apiAvailableStock.replace('<productId>', productId));
        const stocks = await response.json();

        if(stocks.length > 0) {
          stocks.forEach(stock => {
            sourceSelect.addOption({
              value: stock.id,
              text: stock.display_text,
              'data-max': stock.remaining_quantity
            });
          });
          sourceSelect.enable();
        } else {
          sourceSelect.addOption({value: '', text: 'لا يوجد مخزون متاح لهذا المنتج'});
        }
      } catch (error) {
        console.error('Failed to load available stock:', error);
        sourceSelect.addOption({value: '', text: 'خطأ في تحميل البيانات'});
      }
    });

    sourceSelect.on('change', function(sourceId) {
      if (sourceId && this.options[sourceId]) {
        const maxVal = this.options[sourceId]['data-max'];
        quantityInput.setAttribute('max', maxVal);
        maxHelpText.textContent = `الكمية القصوى المتاحة: ${parseFloat(maxVal).toFixed(3)}`;
      } else {
        quantityInput.removeAttribute('max');
        maxHelpText.textContent = '';
      }
    });
  }
}