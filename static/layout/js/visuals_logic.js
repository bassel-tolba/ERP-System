//gipcco_project\static\layout\js\visuals_logic.js
function showNoDataMessage(canvasId) {
  const canvas = document.getElementById(canvasId);
  if (canvas && canvas.parentElement) {
    const parent = canvas.parentElement;
    // Prevent adding multiple messages
    if (parent.querySelector('.alert-info')) return;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'alert alert-info text-center p-4 d-flex align-items-center justify-content-center h-100';
    messageDiv.innerHTML = '<i class="bi bi-bar-chart-line-fill me-2"></i> لا توجد بيانات كافية لعرض هذا الرسم البياني.';
    canvas.style.display = 'none'; // Hide the canvas if no data
    parent.appendChild(messageDiv);
  }
}

function initVisualsLogic(container) {
  // =========================================================================
  //  NEW & ENHANCED LOGIC FOR VISUALS PAGE
  // =========================================================================
  const analysisForm = container.querySelector("#analysisForm");
  if (analysisForm) {
    console.log("Initializing visuals.html logic...");
    const analysisTypeInput = container.querySelector("#analysisTypeInput");
    const analysisTabs = container.querySelectorAll('#analysisTypeTabs button[data-bs-toggle="tab"]');
    const allFilters = container.querySelectorAll(".analysis-filter");

    // Function to show/hide filters based on selected type
    const updateFiltersVisibility = (type) => {
      allFilters.forEach(filter => {
        const filterType = filter.dataset.type;
        // An element should be visible if its data-type matches the current analysis type
        if (filterType === type) {
          filter.style.display = 'block';
          filter.querySelectorAll('select, input').forEach(el => el.disabled = false);
        } else {
          filter.style.display = 'none';
          filter.querySelectorAll('select, input').forEach(el => el.disabled = true);
        }
      });
    };

    // Add event listeners to tabs
    analysisTabs.forEach(tab => {
      tab.addEventListener('shown.bs.tab', (event) => {
        let type;
        if (event.target.id === 'raw-material-tab') type = 'raw_material';
        else if (event.target.id === 'finished-product-tab') type = 'finished_product';
        else if (event.target.id === 'expense-tab') type = 'expense'; // NEW

        if (type) {
          analysisTypeInput.value = type;
          updateFiltersVisibility(type);
        }
      });
    });

    // Initial setup
    updateFiltersVisibility(analysisTypeInput.value);

    // --- Charting Logic ---
    if (typeof Chart === "undefined") {
      console.error("Chart.js not loaded!");
      return;
    }
    const chartColors = ["#0d6efd", "#6f42c1", "#d63384", "#dc3545", "#fd7e14", "#ffc107", "#198754", "#20c997", "#0dcaf0", "#6c757d"];

    // A. Raw Material Charts
    const inOutData = window.getDataFromIsland("data-for-chart-1", container);
    if (inOutData && inOutData.labels.length > 0) new Chart(document.getElementById("inventoryFlowChart"), { type: "line", data: inOutData, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false } }}); else showNoDataMessage("inventoryFlowChart");
    const consumptionData = window.getDataFromIsland("data-for-chart-2", container);
    if (consumptionData && consumptionData.labels.length > 0) { consumptionData.datasets[0].backgroundColor = chartColors; new Chart(document.getElementById("consumptionChart"), { type: "doughnut", data: consumptionData, options: { responsive: true, maintainAspectRatio: false }}); } else showNoDataMessage("consumptionChart");
    const varianceData = window.getDataFromIsland("data-for-chart-3", container);
    if (varianceData && varianceData.labels.length > 0) { varianceData.datasets[0].backgroundColor = varianceData.datasets[0].data.map(v => v > 0 ? "rgba(220, 53, 69, 0.7)" : "rgba(25, 135, 84, 0.7)"); new Chart(document.getElementById("varianceChart"), { type: "bar", data: varianceData, options: { responsive: true, maintainAspectRatio: false }}); } else showNoDataMessage("varianceChart");
    const supplierData = window.getDataFromIsland("data-for-chart-4", container);
    if (supplierData && supplierData.labels.length > 0) { supplierData.datasets[0].backgroundColor = chartColors.slice().reverse(); new Chart(document.getElementById("supplierChart"), { type: "pie", data: supplierData, options: { responsive: true, maintainAspectRatio: false }}); } else showNoDataMessage("supplierChart");

    // B. Finished Product Charts
    const prodVolData = window.getDataFromIsland("fp-data-for-chart-1", container);
    if (prodVolData && prodVolData.labels.length > 0) new Chart(document.getElementById("productionVolumeChart"), { type: "line", data: prodVolData, options: { responsive: true, maintainAspectRatio: false }}); else showNoDataMessage("productionVolumeChart");
    const costTrendData = window.getDataFromIsland("fp-data-for-chart-2", container);
    if (costTrendData && costTrendData.labels.length > 0) new Chart(document.getElementById("costTrendChart"), { type: "line", data: costTrendData, options: { responsive: true, maintainAspectRatio: false }}); else showNoDataMessage("costTrendChart");
    const marketData = window.getDataFromIsland("fp-data-for-chart-3", container);
    if (marketData && marketData.labels.length > 0) { marketData.datasets[0].backgroundColor = ['#0d6efd', '#fd7e14']; new Chart(document.getElementById("marketShareChart"), { type: "pie", data: marketData, options: { responsive: true, maintainAspectRatio: false }}); } else showNoDataMessage("marketShareChart");
    const mixData = window.getDataFromIsland("fp-data-for-chart-4", container);
    if (mixData && mixData.labels.length > 0) { mixData.datasets[0].backgroundColor = chartColors; new Chart(document.getElementById("productMixChart"), { type: "bar", data: mixData, options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}); } else showNoDataMessage("productMixChart");

    // C. NEW: Expense Analysis Charts
    const deptData = window.getDataFromIsland("exp-data-for-chart-1", container);
    if (deptData && deptData.labels.length > 0) { deptData.datasets[0].backgroundColor = chartColors; new Chart(document.getElementById("departmentExpenseChart"), { type: "pie", data: deptData, options: { responsive: true, maintainAspectRatio: false }}); } else showNoDataMessage("departmentExpenseChart");
    const catTrendData = window.getDataFromIsland("exp-data-for-chart-2", container);
    if (catTrendData && catTrendData.labels.length > 0) new Chart(document.getElementById("categoryTrendChart"), { type: "line", data: catTrendData, options: { responsive: true, maintainAspectRatio: false }}); else showNoDataMessage("categoryTrendChart");
    const topItemsData = window.getDataFromIsland("exp-data-for-chart-3", container);
    if (topItemsData && topItemsData.labels.length > 0) { topItemsData.datasets[0].backgroundColor = chartColors.slice(0,5); new Chart(document.getElementById("topItemsChart"), { type: "bar", data: topItemsData, options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y' }}); } else showNoDataMessage("topItemsChart");
  }
}