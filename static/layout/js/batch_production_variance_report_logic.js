//gipcco_project\static\layout\js\batch_production_variance_report_logic.js
function initBatchProductionVarianceReportLogic(container) {
  // =========================================================================
  //  NEW: LOGIC FOR BATCH PRODUCTION VARIANCE REPORT (ROBUST CHECK)
  // =========================================================================
  const batchVarianceForm = container.querySelector('#batchVarianceForm');
  if (batchVarianceForm) {
    console.log("%c[DEBUG] Batch Variance Report: Found form. Initializing charts.", "color: blue; font-weight: bold;");
    const chartData = window.getDataFromIsland('chart-data', container);
    console.log("[DEBUG] Batch Variance Report: Raw data from island:", chartData);

    if (chartData && chartData.labels && chartData.labels.length > 0) {
      console.log("%c[DEBUG] Batch Variance Report: Chart data is valid. Proceeding to create charts.", "color: green;");

      // --- Quantity Variance Chart ---
      try {
        const qtyCtx = container.querySelector('#quantityVarianceChart').getContext('2d');
        new Chart(qtyCtx, {
          type: 'bar',
          data: {
            labels: chartData.labels,
            datasets: [{
              label: 'Quantity Variance',
              data: chartData.variance_qty_data,
              backgroundColor: chartData.variance_qty_data.map(v => v > 0 ? 'rgba(255, 99, 132, 0.5)' : 'rgba(75, 192, 192, 0.5)'),
              borderColor: chartData.variance_qty_data.map(v => v > 0 ? 'rgba(255, 99, 132, 1)' : 'rgba(75, 192, 192, 1)'),
              borderWidth: 1
            }]
          },
          options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, title: { display: true, text: 'Quantity' } } } }
        });
        console.log("[DEBUG] Batch Variance Report: Quantity Variance Chart created successfully.");
      } catch (e) {
        console.error("[DEBUG] Batch Variance Report: Error creating Quantity Variance Chart:", e);
      }

      // --- Cost Variance Chart ---
      try {
        const costCtx = container.querySelector('#costVarianceChart').getContext('2d');
        new Chart(costCtx, {
          type: 'bar',
          data: {
            labels: chartData.labels,
            datasets: [{
              label: 'Cost Variance',
              data: chartData.variance_cost_data,
              backgroundColor: chartData.variance_cost_data.map(v => v > 0 ? 'rgba(255, 99, 132, 0.5)' : 'rgba(75, 192, 192, 0.5)'),
              borderColor: chartData.variance_cost_data.map(v => v > 0 ? 'rgba(255, 99, 132, 1)' : 'rgba(75, 192, 192, 1)'),
              borderWidth: 1
            }]
          },
          options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, title: { display: true, text: 'Cost' } } } }
        });
        console.log("[DEBUG] Batch Variance Report: Cost Variance Chart created successfully.");
      } catch(e) {
        console.error("[DEBUG] Batch Variance Report: Error creating Cost Variance Chart:", e);
      }

    } else {
      console.warn("%c[DEBUG] Batch Variance Report: Chart data is missing, empty, or invalid.", "color: orange;");
    }
  }
}