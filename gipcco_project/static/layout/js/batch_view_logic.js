function initBatchViewLogic(container) {
	// ----- Logic for batch_view.html -----
	const batchViewForm = container.querySelector("#batchEditForm");
	if (batchViewForm) {
		console.log("Initializing FULL batch_view.html dynamic logic...");

		const batchStatus = container.querySelector("#batch-status-badge")?.dataset.status;
		if (batchStatus && batchStatus !== 'draft') {
			const fieldset = batchViewForm.querySelector("fieldset");
			if (fieldset) {
				fieldset.disabled = true;
			}
		}

		const continuationCheckEdit = container.querySelector("#isContinuationSwitch");
		const parentBatchContainerEdit = container.querySelector("#parent_batch_container_edit");
		const parentBatchSelectEl = container.querySelector("#parent_batch_edit");
		const shopOrderInputEdit = container.querySelector('input[name="shop_order_number"]');

		const batchFromInput = container.querySelector("#batch_number_from");
		const batchToInput = container.querySelector("#batch_number_to");
		const materialsTbody = container.querySelector("#materials_tbody");
		const batchItemsTable = container.querySelector("#batchItemsTable");

		if (continuationCheckEdit && parentBatchContainerEdit && parentBatchSelectEl) {
			const parentBatchSelect = parentBatchSelectEl.tomselect;

			continuationCheckEdit.addEventListener("change", function () {
				if (this.checked) {
					parentBatchContainerEdit.style.display = "block";
					if (parentBatchSelect) parentBatchSelect.enable();
				} else {
					parentBatchContainerEdit.style.display = "none";
					if (parentBatchSelect) {
						parentBatchSelect.clear();
						parentBatchSelect.disable();
					}
				}
			});

			// --- START: ADDED AUTO-FILL LOGIC ---
			if (parentBatchSelect && shopOrderInputEdit) {
				parentBatchSelect.on("change", async function (parentBatchId) {
					if (!parentBatchId) return; // Do nothing if selection is cleared
					try {
						const apiUrl = window.appUrls.apiBatchDetails.replace("<batchId>", parentBatchId);
						const response = await fetch(apiUrl);
						if (!response.ok) throw new Error("Batch details not found");
						const data = await response.json();
						// Automatically update the Shop Order number to match the selected parent
						shopOrderInputEdit.value = data.shop_order_number;
					} catch (error) {
						console.error("Failed to fetch parent batch details for editing:", error);
						alert("خطأ في تحميل بيانات الأمر الأصلي.");
					}
				});
			}
			// --- END: ADDED AUTO-FILL LOGIC ---

			// Initialize state on load
			if (continuationCheckEdit.checked) {
				if (parentBatchSelect) parentBatchSelect.enable();
			} else {
				if (parentBatchSelect) parentBatchSelect.disable();
			}
		}

		if (batchFromInput && batchToInput && materialsTbody) {
			const getNumBatches = () => {
				const fromVal = parseInt(batchFromInput.value) || 0;
				const toVal = parseInt(batchToInput.value) || fromVal;
				return fromVal > 0 && toVal >= fromVal ? toVal - fromVal + 1 : fromVal > 0 ? 1 : 0;
			};

			const recalculateAllQuantities = () => {
				const numBatches = getNumBatches();
				materialsTbody.querySelectorAll("tr").forEach((row) => {
					const theoreticalInput = row.querySelector(".theoretical-qty");
					const actualInput = row.querySelector(".actual-qty");

					const baseTheoretical = parseFloat(theoreticalInput.dataset.baseTheoreticalQuantity);
					if (!isNaN(baseTheoretical)) {
						const totalTheoretical = numBatches > 0 ? baseTheoretical * numBatches : 0;
						theoreticalInput.value = totalTheoretical.toFixed(3);
					}

					const baseActual = parseFloat(actualInput.dataset.baseActualQuantity);
					if (!isNaN(baseActual)) {
						const totalActual = numBatches > 0 ? baseActual * numBatches : 0;
						actualInput.value = totalActual.toFixed(3);
					}
				});
			};

			if (!batchFromInput.dataset.recalcInitialized) {
				batchFromInput.addEventListener("input", recalculateAllQuantities);
				batchToInput.addEventListener("input", recalculateAllQuantities);
				batchFromInput.dataset.recalcInitialized = "true";
			}
		}

		if (batchItemsTable && !batchItemsTable.dataset.deleteInitialized) {
			batchItemsTable.dataset.deleteInitialized = "true";
		}

		// --- START: REFACTORED DYNAMIC QC SOURCE LOADING FOR MODAL ---
		const addBatchItemModal = container.querySelector("#addBatchItemModal");
		if (addBatchItemModal) {
			console.log("%c[DEBUG] Modal #addBatchItemModal found.", "color: orange;");
			const productSelectModal = addBatchItemModal.querySelector('select[name="primitive_product_id"]');
			const qcSelectModal = addBatchItemModal.querySelector('select[name="source_log_id"]');

			if (productSelectModal && qcSelectModal) {
				console.log("%c[DEBUG] Modal product and QC select elements found.", "color: orange;");

				// Initialize TomSelect if it doesn't exist on the product dropdown
				if (!productSelectModal.tomselect) {
					console.log("%c[DEBUG] Initializing TomSelect on modal product dropdown.", "color: orange;");
					new TomSelect(productSelectModal, { create: false, dropdownParent: "body" });
				}
				// The QC select is also a searchable-select, so TomSelect is initialized on it automatically.

				// Attach event listener if it hasn't been attached yet
				if (productSelectModal.tomselect && !productSelectModal.dataset.qcListenerAttached) {
					console.log("%c[DEBUG] Attaching QC source loader listener to modal product dropdown.", "color: orange;");
					productSelectModal.tomselect.on("change", async function (productId) {
						console.log(`%c[DEBUG] Product changed in modal. Selected product ID: ${productId}`, "color: #9c27b0;");
						const qcSelectTomSelect = qcSelectModal.tomselect;
						if (!qcSelectTomSelect) {
							console.error("[DEBUG] TomSelect instance not found on QC select modal. Cannot update options.");
							return;
						}

						// Use TomSelect API to manage options
						qcSelectTomSelect.clear();
						qcSelectTomSelect.clearOptions();
						qcSelectTomSelect.disable();
						qcSelectTomSelect.addOption({ value: "", text: "جار التحميل..." });

						if (!productId) {
							console.log("%c[DEBUG] Product cleared, resetting QC select.", "color: #9c27b0;");
							qcSelectTomSelect.clearOptions();
							qcSelectTomSelect.addOption({ value: "", text: "اختر مادة أولاً" });
							return;
						}

						try {
							const apiUrl = window.appUrls.apiGetAvailableStock.replace("0", productId);
							console.log(`%c[DEBUG] Fetching available stock from: ${apiUrl}`, "color: #9c27b0;");
							const response = await fetch(apiUrl);

							if (!response.ok) {
								console.error(`[DEBUG] API Error: Status ${response.status} - ${response.statusText}`);
								throw new Error(`Network response was not ok (status: ${response.status})`);
							}

							const data = await response.json();
							console.log("%c[DEBUG] Received stock data:", "color: #9c27b0;", data);

							qcSelectTomSelect.clearOptions(); // Clear "Loading..."
							qcSelectTomSelect.addOption({ value: "", text: "اختر مصدر..." });

							if (data && data.length > 0) {
								data.forEach((stock) => {
									qcSelectTomSelect.addOption({ value: stock.id, text: stock.display_text });
								});
								console.log(`%c[DEBUG] Populated QC TomSelect with ${data.length} options.`, "color: #9c27b0;");
							} else {
								qcSelectTomSelect.addOption({ value: "", text: "لا يوجد مخزون متاح", disabled: true });
								console.log("%c[DEBUG] No available stock found for this product.", "color: #9c27b0;");
							}
							qcSelectTomSelect.enable();
						} catch (error) {
							console.error("[DEBUG] Failed to fetch available stock for modal:", error);
							qcSelectTomSelect.clearOptions();
							qcSelectTomSelect.addOption({ value: "", text: "خطأ في تحميل البيانات" });
						}
					});
					productSelectModal.dataset.qcListenerAttached = "true";
					console.log("%c[DEBUG] QC listener attached and marked.", "color: orange;");
				}
			} else {
				console.warn("[DEBUG] Could not find product or QC select elements inside the modal.");
			}
		}
		// --- END: REFACTORED DYNAMIC QC SOURCE LOADING FOR MODAL ---
	}
}
