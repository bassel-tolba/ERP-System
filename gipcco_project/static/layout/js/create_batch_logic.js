//gipcco_project\static\layout\js\create_batch_logic.js
function initCreateBatchLogic(container) {
	// ----- Logic for create_batch.html -----
	const createBatchForm = container.querySelector(`form[action="${window.appUrls.createBatch}"]`);
	if (createBatchForm) {
		console.log("Initializing FULL create_batch.html dynamic logic...");

		const templateData = window.getDataFromIsland("template-data", container) || {};
		const availableStockData = window.getDataFromIsland("available-stock-data", container) || {};
		const allPrimitiveProducts = window.getDataFromIsland("primitive-products-data", container) || [];

		const continuationCheck = container.querySelector("#is_continuation");
		const parentBatchContainer = container.querySelector("#parent_batch_container");
		const parentBatchSelectEl = container.querySelector("#parent_batch");
		const templateSelectEl = container.querySelector("#template_id");
		const shopOrderInput = container.querySelector("#shop_order_number");
		const batchFromInput = container.querySelector("#batch_number_from");
		const batchToInput = container.querySelector("#batch_number_to");
		const creationDateInput = container.querySelector("#creation_date");

		const materialsCard = container.querySelector("#materials_card");
		const materialsTbody = container.querySelector("#materials_tbody");
		const batchCountDisplay = container.querySelector("#batch_count_display");
		const addManualBtn = container.querySelector("#add-material-manually-btn");

		const templateSelect = templateSelectEl.tomselect;
		const parentBatchSelect = parentBatchSelectEl.tomselect;

		const toggleContinuationMode = (isContinuation) => {
			if (isContinuation) {
				parentBatchContainer.style.display = "block";
				parentBatchSelect.enable();
				templateSelect.lock();
				shopOrderInput.readOnly = true;
				batchFromInput.readOnly = false; // <-- CORRECTED: Must be able to enter a NEW batch number
				batchToInput.readOnly = false; // <-- CORRECTED: Must be able to enter a NEW batch number
			} else {
				parentBatchContainer.style.display = "none";
				parentBatchSelect.clear();
				parentBatchSelect.disable();
				templateSelect.unlock();
				templateSelect.clear();
				shopOrderInput.readOnly = false;
				shopOrderInput.value = "";
				batchFromInput.readOnly = false;
				batchFromInput.value = "";
				batchToInput.readOnly = false;
				batchToInput.value = "";
				materialsCard.style.display = "none";
				materialsTbody.innerHTML = "";
			}
		};

		const validateRowQuantity = (row) => {
			const actualQtyInput = row.querySelector(".actual-qty");
			const qcSelect = row.querySelector(".qc-select");
			const feedbackDiv = actualQtyInput.nextElementSibling;
			const selectedOption = qcSelect.options[qcSelect.selectedIndex];

			actualQtyInput.classList.remove("is-invalid");
			feedbackDiv.textContent = "";

			if (!selectedOption || !selectedOption.value) return;

			const availableQty = parseFloat(selectedOption.dataset.available);
			const actualQty = parseFloat(actualQtyInput.value);

			if (!isNaN(availableQty) && !isNaN(actualQty) && actualQty > availableQty + 0.001) {
				actualQtyInput.classList.add("is-invalid");
				feedbackDiv.textContent = `الكمية أكبر من المتاح (${availableQty.toFixed(3)})`;
			}
		};

		const validateRowDate = (row) => {
			const qcSelect = row.querySelector(".qc-select");
			const feedbackDiv = qcSelect.nextElementSibling;
			const selectedOption = qcSelect.options[qcSelect.selectedIndex];

			qcSelect.classList.remove("is-invalid");
			feedbackDiv.textContent = "";

			if (!selectedOption || !selectedOption.value || !selectedOption.dataset.timestamp) return;

			const creationDateStr = creationDateInput.value;
			const qcTimestamp = selectedOption.dataset.timestamp;

			if (creationDateStr && qcTimestamp > creationDateStr) {
				qcSelect.classList.add("is-invalid");
				feedbackDiv.textContent = "تاريخ المصدر أحدث من تاريخ الأمر.";
			}
		};

		const recalculateQuantities = () => {
			const fromVal = parseInt(batchFromInput.value) || 0;
			const toVal = parseInt(batchToInput.value) || fromVal;
			const numBatches = fromVal > 0 && toVal >= fromVal ? toVal - fromVal + 1 : fromVal > 0 ? 1 : 0;

			batchCountDisplay.textContent = numBatches > 0 ? `لـ ${numBatches} تشغيلة` : "";

			materialsTbody.querySelectorAll("tr").forEach((row) => {
				const theoreticalInput = row.querySelector(".theoretical-qty");
				const actualInput = row.querySelector(".actual-qty");
				const baseQuantity = parseFloat(theoreticalInput.dataset.baseQuantity);

				if (isNaN(baseQuantity)) return;

				const total = numBatches > 0 ? baseQuantity * numBatches : 0;
				if (theoreticalInput.dataset.baseQuantity) {
					theoreticalInput.value = total.toFixed(3);
					actualInput.value = total.toFixed(3);
				}
				validateRowQuantity(row);
			});
			updateQuantitySummaries();
		};

		const updateQuantitySummaries = () => {
			const productTotals = {};
			materialsTbody.querySelectorAll("tr").forEach((row) => {
				const productIdInput = row.querySelector('[name="primitive_product_id"]');
				if (!productIdInput || !productIdInput.value) return;

				const productId = productIdInput.value;
				if (!productTotals[productId]) {
					productTotals[productId] = { theoretical: 0, actual: 0 };
				}
				productTotals[productId].theoretical += parseFloat(row.querySelector(".theoretical-qty").value) || 0;
				productTotals[productId].actual += parseFloat(row.querySelector(".actual-qty").value) || 0;
			});

			materialsTbody.querySelectorAll(".quantity-summary").forEach((span) => (span.textContent = ""));

			Object.keys(productTotals).forEach((productId) => {
				const totals = productTotals[productId];
				const difference = totals.theoretical - totals.actual;
				const isMatch = Math.abs(difference) < 0.001;
				let summaryText = `(${totals.actual.toFixed(3)} / ${totals.theoretical.toFixed(3)})`;
				if (!isMatch) {
					summaryText += ` | متبقي: ${difference.toFixed(3)}`;
				}
				const badgeClass = isMatch ? "bg-success" : "bg-danger";

				materialsTbody.querySelectorAll(`input[name="primitive_product_id"][value="${productId}"]`).forEach((input) => {
					const summarySpan = input.closest("td").querySelector(".quantity-summary");
					if (summarySpan) {
						summarySpan.textContent = summaryText;
						summarySpan.className = `quantity-summary badge ${badgeClass}`;
					}
				});
			});
		};

		const populateQcSelect = (row, productId) => {
			const qcSelect = row.querySelector(".qc-select");
			if (!productId) {
				qcSelect.innerHTML = "<option>اختر مادة أولاً</option>";
				qcSelect.disabled = true;
				return;
			}
			const stockForProduct = availableStockData[productId] || [];
			let optionsHTML = '<option value="">اختر مصدر...</option>';
			stockForProduct.forEach((stock) => {
				optionsHTML += `<option value="${stock.id}" data-available="${stock.remaining_quantity}" data-timestamp="${stock.timestamp}">QC: ${stock.qc_no} | متاح: ${stock.remaining_quantity} | ${stock.timestamp}</option>`;
			});
			if (stockForProduct.length === 0) {
				optionsHTML += '<option value="" disabled>لا يوجد مخزون متاح</option>';
			}
			qcSelect.innerHTML = optionsHTML;
			qcSelect.disabled = false;
			validateRowDate(row);
		};

		const attachRowListeners = (row) => {
			const materialSelect = row.querySelector(".material-select");
			if (materialSelect) {
				new TomSelect(materialSelect, { create: false, dropdownParent: "body" });
				materialSelect.addEventListener("change", (e) => {
					populateQcSelect(row, e.target.value);
					updateQuantitySummaries();
				});
			}
		};

		const createMaterialRow = (item, isManualAdd = false) => {
			const row = document.createElement("tr");
			// When loading from a template, item.theoretical_quantity is a string from JSON.
			// We must parse it to a number before calling .toFixed().
			// The '|| 0' handles cases where the value might be undefined or null.
			const theoreticalQty = isManualAdd ? 0 : parseFloat(item.theoretical_quantity) || 0;

			let materialCellHTML;
			if (isManualAdd) {
				let productOptions = '<option value="">اختر مادة...</option>';
				allPrimitiveProducts.forEach((p) => {
					productOptions += `<option value="${p.id}" data-unit="${p.unit}">${p.name} (${p.unit})</option>`;
				});
				materialCellHTML = `<select class="form-select material-select" name="primitive_product_id" required>${productOptions}</select>`;
			} else {
				materialCellHTML = `<strong>${item.name}</strong> (${item.unit}) <span class="quantity-summary badge"></span><input type="hidden" name="primitive_product_id" value="${item.primitive_product_id}">`;
			}

			row.innerHTML = `
          <td class="ps-3">${materialCellHTML}</td>
          <td><input type="number" step="any" class="form-control text-center fw-bold theoretical-qty" name="theoretical_quantity" value="${theoreticalQty.toFixed(
				3
			)}" data-base-quantity="${theoreticalQty}" required></td>
          <td><input type="number" step="any" class="form-control text-center fw-bold actual-qty" name="actual_quantity" value="${theoreticalQty.toFixed(
				3
			)}" data-base-quantity="${theoreticalQty}" required><div class="invalid-feedback small text-center"></div></td>
          <td class="qc-cell"><select class="form-select qc-select" name="source_log_id" disabled><option>اختر مادة أولاً</option></select><div class="invalid-feedback small"></div></td>
          <td class="text-center pe-2"><button type="button" class="btn btn-sm btn-outline-info split-quantity-btn" title="تقسيم الكمية من المصدر التالي" data-bs-toggle="tooltip"><i class="bi bi-distribute-vertical"></i></button><button type="button" class="btn btn-sm btn-outline-danger remove-row-btn" title="حذف الصف"><i class="bi bi-trash"></i></button></td>
      `;

			materialsTbody.appendChild(row);
			attachRowListeners(row);
			if (!isManualAdd) {
				populateQcSelect(row, item.primitive_product_id);
			}
			return row;
		};

		const loadTemplate = () => {
			const selectedTemplateId = templateSelect.getValue();
			const items = templateData[selectedTemplateId];

			materialsTbody.innerHTML = "";
			if (!selectedTemplateId || !items) {
				materialsCard.style.display = "none";
				return;
			}

			materialsCard.style.display = "block";
			items.forEach((item) => {
				createMaterialRow(item);
			});
			recalculateQuantities();
		};

		continuationCheck.addEventListener("change", function () {
			toggleContinuationMode(this.checked);
		});

		parentBatchSelect.on("change", async function (parentBatchId) {
			if (!parentBatchId) {
				shopOrderInput.value = "";
				batchFromInput.value = "";
				templateSelect.clear();
				return;
			}
			try {
				// --- CORRECTED URL CONSTRUCTION ---
				const apiUrl = window.appUrls.apiBatchDetails.replace("0", parentBatchId);
				const response = await fetch(apiUrl);
				// --- END CORRECTION ---
				if (!response.ok) throw new Error("Batch not found");
				const data = await response.json();

				// --- CORRECTED LOGIC ---
				shopOrderInput.value = data.shop_order_number; // Auto-fill SO Number
				batchFromInput.value = data.batch_number_from; // Auto-fill Batch Number From
				batchToInput.value = data.batch_number_to; // Auto-fill Batch Number To
				templateSelect.setValue(data.template_id); // Auto-select template
				loadTemplate(); // Manually load items for the selected template
				recalculateQuantities(); // Recalculate quantities based on the auto-filled batch numbers
				// --- END CORRECTION ---
			} catch (error) {
				console.error("Failed to fetch parent batch details:", error);
				alert("خطأ في تحميل بيانات الأمر الأصلي.");
			}
		});

		templateSelect.on("change", loadTemplate);
		batchFromInput.addEventListener("input", recalculateQuantities);
		batchToInput.addEventListener("input", recalculateQuantities);
		creationDateInput.addEventListener("change", () => {
			materialsTbody.querySelectorAll("tr").forEach(validateRowDate);
		});
		addManualBtn.addEventListener("click", () => createMaterialRow({}, true));

		materialsTbody.addEventListener("click", function (e) {
			const removeBtn = e.target.closest(".remove-row-btn");
			if (removeBtn) {
				removeBtn.closest("tr").remove();
				updateQuantitySummaries();
			}

            const splitBtn = e.target.closest(".split-quantity-btn");
            if (splitBtn) {
                const currentRow = splitBtn.closest("tr");
                const actualQtyInput = currentRow.querySelector(".actual-qty");
                const qcSelect = currentRow.querySelector(".qc-select");
                const selectedOption = qcSelect.options[qcSelect.selectedIndex];

                if (!selectedOption || !selectedOption.value) return;

                const availableQty = parseFloat(selectedOption.dataset.available);
                const actualQty = parseFloat(actualQtyInput.value);
                const productId = currentRow.querySelector('[name="primitive_product_id"]').value;
                const productInfo = allPrimitiveProducts.find(p => p.id == productId);

                if (isNaN(availableQty) || isNaN(actualQty) || actualQty <= availableQty) return;

                const remainingNeeded = actualQty - availableQty;
                actualQtyInput.value = availableQty.toFixed(3);

                const newRow = createMaterialRow({
                    name: productInfo.name,
                    unit: productInfo.unit,
                    primitive_product_id: productId,
                    theoretical_quantity: 0 // Theoretical is not relevant for the split part
                });

                newRow.querySelector('.theoretical-qty').value = remainingNeeded.toFixed(3);
                newRow.querySelector('.actual-qty').value = remainingNeeded.toFixed(3);

                // Find and select the next available source
                const stockForProduct = availableStockData[productId] || [];
                const currentIndex = stockForProduct.findIndex(s => s.id == selectedOption.value);
                const nextSource = stockForProduct[currentIndex + 1];

                if (nextSource) {
                    newRow.querySelector('.qc-select').value = nextSource.id;
                }
                
                validateRowQuantity(currentRow);
                validateRowQuantity(newRow);
                updateQuantitySummaries();
            }
		});

		materialsTbody.addEventListener("change", function (e) {
			const target = e.target;
			if (target.classList.contains("qc-select") || target.classList.contains("material-select")) {
				const row = target.closest("tr");
				validateRowQuantity(row);
				validateRowDate(row);
				if (target.classList.contains("material-select")) updateQuantitySummaries();
			}
		});

		materialsTbody.addEventListener("input", function (e) {
			const target = e.target;
			if (target.classList.contains("actual-qty") || target.classList.contains("theoretical-qty")) {
				if (target.classList.contains("actual-qty")) validateRowQuantity(target.closest("tr"));
				updateQuantitySummaries();
			}
		});
	}
}
