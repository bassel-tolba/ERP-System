// This function needs to be globally accessible to initialize plugins on newly loaded content
window.initializePluginsInContent = function (container = document) {
	console.log("%c[DEBUG] initializePluginsInContent: Running on container:", "color: green;", container);

	// 1. Generic Initializers (run on all dynamic content)
	flatpickr(container.querySelectorAll(".datepicker"), { dateFormat: "Y-m-d", locale: "ar" });

	container.querySelectorAll(".searchable-select").forEach((el) => {
		if (!el.tomselect) {
			// Prevent re-initialization
			new TomSelect(el, {
				rtl: true,
				placeholder: el.getAttribute("placeholder") || "ابحث أو اختر...",
				create: false,
				dropdownParent: "body",
			});
		}
	});

	container.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
		if (!bootstrap.Tooltip.getInstance(el)) {
			new bootstrap.Tooltip(el);
		}
	});

	// 2. Page-Specific Initializers
	const pageInitializers = {
		"#batchVarianceForm": initBatchProductionVarianceReportLogic,
		"#batchEditForm": initBatchViewLogic,
		[`form[action="${window.appUrls.createBatch}"]`]: initCreateBatchLogic,
		'form[action="/"]': initDashboardLogic,
		// '#consumptionForm': initExpensesPageLogic,
		"#detailsModal": initLedgerLogic,
		// '#editConsumptionModal': initManageExpensesLogic,
		"#returnForm": initProductionReturnsLogic,
		"#add-sub-batch-btn": initReceiveFinishedProductLogic,
		"#editRecordModal": initRecordsLogic,
		"#addTemplateModal": initShopOrderTemplatesLogic,
		"#analysisForm": initVisualsLogic,
		// --- NEW FINANCIALS INITIALIZERS ---
		"#supplierInvoiceFilters": initSupplierInvoiceListLogic,
		"#createSupplierInvoiceForm": initCreateSupplierInvoiceLogic,
		"#customerInvoiceFilters": initCustomerInvoiceListLogic,
		"#createCustomerInvoiceForm": initCreateCustomerInvoiceLogic,
		"#journalEntryForm": initJournalEntryCreateLogic,
		"#reconciliationWorkspace": initReconciliationManageLogic,
		"#createSalesOrderForm": initSalesOrderCreateLogic,
		"#createPurchaseOrderForm": initPurchaseOrderFormLogic, // MODIFIED
		"#editPurchaseOrderForm": initPurchaseOrderFormLogic,   // NEW
		"#createPurchaseReturnForm": initPurchaseReturnCreateLogic, // NEW
		"#taxReportForm": initTaxReconciliationReportLogic,
		"#close-period-container": initClosePeriodLogic,
		"#fiscalYearContainer": initFiscalYearListLogic,
		"#overhead-allocation-workspace-container": initOverheadAllocationWorkspaceLogic,
		"#variance-allocation-content": initInventoryCountsLogic,
		"#createCostPoolModal": initCostPoolsListLogic, // <-- ADDED THIS LINE
		// --- NEW: Employee Financials ---
		"#employee-advances-container": initEmployeeAdvanceDetailLogic,
		"#manage-employees-container": initManageEmployeesLogic,
	};

	for (const selector in pageInitializers) {
		if (container.querySelector(selector)) {
			console.log(`%c[DEBUG] Found selector "${selector}", running its initializer.`, "color: #007bff;");
			try {
				pageInitializers[selector](container);
			} catch (e) {
				console.error(`Error executing initializer for selector "${selector}":`, e);
			}
		}
	}
};

document.addEventListener("DOMContentLoaded", function () {
	const contentContainer = document.getElementById("page-content");

	window.getDataFromIsland = function (islandId, container = document) {
		const island = container.querySelector(`#${islandId}`);
		if (!island || !island.textContent) return null;
		try {
			return JSON.parse(island.textContent);
		} catch (e) {
			console.error(`Failed to parse JSON from data island #${islandId}. Error:`, e);
			return null;
		}
	};

	async function loadContent(url, pushState = true) {
		try {
			contentContainer.style.transition = "opacity 0.2s ease-in-out";
			contentContainer.style.opacity = "0.5";
			const response = await fetch(url, {
				headers: { "X-Partial-Request": "true" },
			});

			if (!response.ok) {
				window.location.href = url;
				return;
			}
			const html = await response.text();
			contentContainer.innerHTML = html;
			contentContainer.style.opacity = "1";
			if (pushState) {
				history.pushState({ path: url }, "", url);
			}
			const newTitle = contentContainer.querySelector("h1")?.innerText;
			document.title = newTitle ? `${newTitle} - GIPCCO` : "GIPCCO Warehouse System";
			window.initializePluginsInContent(contentContainer);
			updateActiveNav(url);
		} catch (error) {
			console.error("Failed to load dynamic content:", error);
			window.location.href = url;
		}
	}

	function updateActiveNav(url) {
		const path = new URL(url, window.location.origin).pathname;
		document.querySelectorAll(".nav-link, .dropdown-item").forEach((link) => {
			link.classList.remove("active");
		});

		let bestMatch = null;
		document.querySelectorAll(".nav-link, .dropdown-item").forEach((link) => {
			const linkPath = new URL(link.href).pathname;
			if (path.startsWith(linkPath)) {
				if (!bestMatch || linkPath.length > new URL(bestMatch.href).pathname.length) {
					bestMatch = link;
				}
			}
		});

		if (bestMatch) {
			bestMatch.classList.add("active");
			const dropdown = bestMatch.closest(".dropdown");
			if (dropdown) {
				const toggle = dropdown.querySelector(".dropdown-toggle");
				if (toggle) {
					toggle.classList.add("active");
				}
			}
		}
	}

	document.body.addEventListener("click", (event) => {
		const link = event.target.closest("a");
		if (
			link &&
			link.href &&
			link.target !== "_blank" &&
			!link.hasAttribute("data-bs-toggle") &&
			new URL(link.href).origin === window.location.origin &&
			!link.hasAttribute("data-no-dynamic") &&
			!link.closest(".modal")
		) {
			event.preventDefault();
			loadContent(link.href);
		}
	});

	window.addEventListener("popstate", (event) => {
		if (event.state && event.state.path) {
			loadContent(event.state.path, false);
		} else {
			// Fallback for initial page load popstate
			loadContent(window.location.href, false);
		}
	});

	history.replaceState({ path: window.location.href }, "", window.location.href);

	window.initializePluginsInContent(document.body);
});
