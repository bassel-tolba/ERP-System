function initProductionReturnsLogic(container) {
  // ----- Logic for production_returns.html -----
  const productSelectForReturns = container.querySelector('#product_id');
  if (productSelectForReturns && productSelectForReturns.closest('#returnForm')) {
    if (!productSelectForReturns.dataset.returnsInitialized) {
      console.log("Initializing production_returns.html logic...");
      productSelectForReturns.dataset.returnsInitialized = 'true';

      const sourceSelect = container.querySelector('#source_log_id');
      const quantityInput = container.querySelector('#quantity');
      const maxHelpText = container.querySelector('#maxReturnableHelp');

      productSelectForReturns.addEventListener('change', async function() {
        const productId = this.value;
        sourceSelect.innerHTML = '<option>جاري التحميل...</option>';
        sourceSelect.disabled = true;
        maxHelpText.textContent = '';
        quantityInput.removeAttribute('max');

        if (!productId) {
          sourceSelect.innerHTML = '<option value="" selected disabled>-- اختر المادة أولاً --</option>';
          return;
        }

        try {
          // Use the URL from the global object
          const response = await fetch(window.appUrls.apiGetUsedQcSources.replace('<productId>', productId));
          if (!response.ok) throw new Error('Network response was not ok');

          const sources = await response.json();

          sourceSelect.innerHTML = '<option value="" selected disabled>-- اختر المصدر --</option>';
          if (sources.length > 0) {
            sources.forEach(source => {
              const option = document.createElement('option');
              option.value = source.id;
              const date = new Date(source.timestamp).toLocaleDateString('en-CA');
              option.textContent = `${source.qc_no || 'N/A'} (تاريخ: ${date})`;
              option.dataset.maxReturnable = source.max_returnable;
              sourceSelect.appendChild(option);
            });
            sourceSelect.disabled = false;
          } else {
            sourceSelect.innerHTML = '<option value="" selected disabled>-- لا توجد مصادر مستخدمة لهذه المادة --</option>';
          }
        } catch (error) {
          console.error('Failed to fetch sources:', error);
          sourceSelect.innerHTML = '<option value="" selected disabled>-- خطأ في التحميل --</option>';
        }
      });

      sourceSelect.addEventListener('change', function() {
        const selectedOption = this.options[this.selectedIndex];
        const maxReturnable = selectedOption.dataset.maxReturnable;
        if (maxReturnable) {
          const maxVal = parseFloat(maxReturnable).toFixed(3);
          quantityInput.setAttribute('max', maxVal);
          maxHelpText.textContent = `الكمية القصوى الممكن إرجاعها من هذا المصدر: ${maxVal}`;
        } else {
          quantityInput.removeAttribute('max');
          maxHelpText.textContent = '';
        }
      });
    }
  }
}