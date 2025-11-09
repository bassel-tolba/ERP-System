function initArWorkbenchLogic(container = document) {
	const customerSelect = container.querySelector("#customer_select");
	const workbenchArea = container.querySelector("#workbench_area");
	const noCustomerSelected = container.querySelector("#no_customer_selected");
	const loadingSpinner = container.querySelector("#loading_spinner");
	const creditsTableBody = container.querySelector("#credits_table_body");
	const invoicesTableBody = container.querySelector("#invoices_table_body");
	const applyButton = container.querySelector("#apply_button");
	const form = container.querySelector("#arWorkbenchForm");
	const customerIdHidden = container.querySelector("#customer_id_hidden");
	const applicationsJsonHidden = container.querySelector("#applications_json_hidden");

	let availableCredits = [];
	let openInvoices = [];

	if (!customerSelect) return;

	const formatCurrency = (num) => (num ? parseFloat(num).toFixed(3) : "0.000");

	function updateSummaries() {
		const totalCredits = availableCredits.reduce((sum, credit) => sum + parseFloat(credit.unapplied), 0);
		const totalDue = openInvoices.reduce((sum, inv) => sum + parseFloat(inv.balance), 0);

		let totalApplied = 0;
		container.querySelectorAll(".application-amount-input").forEach((input) => {
			totalApplied += parseFloat(input.value || 0);
		});

		container.querySelector("#total_credits_available").textContent = formatCurrency(totalCredits);
		container.querySelector("#total_invoices_due").textContent = formatCurrency(totalDue);
		container.querySelector("#summary_total_credits").textContent = formatCurrency(totalCredits);
		container.querySelector("#summary_total_applied").textContent = formatCurrency(totalApplied);
		container.querySelector("#summary_remaining_balance").textContent = formatCurrency(totalDue - totalApplied);

		applyButton.disabled = totalApplied <= 0;
	}

	function renderTables() {
		creditsTableBody.innerHTML = "";
		availableCredits.forEach((credit) => {
			const row = `
                <tr>
                    <td class="ps-3">${credit.type === "payment" ? "دفعة" : "إشعار دائن"}</td>
                    <td>${credit.date}</td>
                    <td>${credit.description}</td>
                    <td class="text-end pe-3 fw-bold">${formatCurrency(credit.unapplied)}</td>
                </tr>
            `;
			creditsTableBody.insertAdjacentHTML("beforeend", row);
		});

		invoicesTableBody.innerHTML = "";
		openInvoices.forEach((invoice) => {
			const row = `
                <tr>
                    <td class="ps-3">${invoice.number}</td>
                    <td>${invoice.due_date}</td>
                    <td class="text-end">${formatCurrency(invoice.balance)}</td>
                    <td class="text-end pe-3">
                        <input type="number" class="form-control form-control-sm text-end application-amount-input"
                               data-invoice-id="${invoice.id}"
                               min="0" max="${formatCurrency(invoice.balance)}" step="0.001"
                               placeholder="0.000">
                    </td>
                </tr>
            `;
			invoicesTableBody.insertAdjacentHTML("beforeend", row);
		});
		updateSummaries();
	}

	async function fetchOpenItems(customerId) {
		workbenchArea.classList.add("d-none");
		noCustomerSelected.classList.add("d-none");
		loadingSpinner.classList.remove("d-none");

		try {
			const response = await fetch(`/api/customer/${customerId}/open_items/`);
			if (!response.ok) throw new Error("Network response was not ok.");
			const data = await response.json();
			availableCredits = data.credits.map((c) => ({ ...c, unapplied: parseFloat(c.unapplied) }));
			openInvoices = data.invoices.map((i) => ({ ...i, balance: parseFloat(i.balance) }));
			renderTables();
			workbenchArea.classList.remove("d-none");
		} catch (error) {
			console.error("Failed to fetch customer open items:", error);
			alert("حدث خطأ أثناء تحميل بيانات العميل.");
			noCustomerSelected.classList.remove("d-none");
		} finally {
			loadingSpinner.classList.add("d-none");
		}
	}

	function handleApplicationInput() {
        let totalToApply = 0;
        const applicationInputs = container.querySelectorAll(".application-amount-input");
        applicationInputs.forEach((input) => {
            totalToApply += parseFloat(input.value || 0);
        });

        const totalCredits = availableCredits.reduce((sum, credit) => sum + credit.unapplied, 0);

        // If the total applied exceeds available credits, mark all non-zero inputs as invalid.
        // Otherwise, clear all invalid states.
        const isOverApplied = totalToApply > totalCredits;

        applicationInputs.forEach(input => {
            const amount = parseFloat(input.value || 0);
            if (amount > 0 && isOverApplied) {
                input.classList.add("is-invalid");
            } else {
 				input.classList.remove("is-invalid");
 			}
 		});

		updateSummaries();
	}

	customerSelect.addEventListener("change", (e) => {
		const customerId = e.target.value;
		customerIdHidden.value = customerId;
		if (customerId) {
			fetchOpenItems(customerId);
		} else {
			workbenchArea.classList.add("d-none");
			noCustomerSelected.classList.remove("d-none");
			loadingSpinner.classList.add("d-none");
		}
	});

	invoicesTableBody.addEventListener("input", (e) => {
		if (e.target.classList.contains("application-amount-input")) {
			handleApplicationInput();
		}
	});

	form.addEventListener("submit", (e) => {
		e.preventDefault();
		let totalToApply = 0;
		let totalCredits = availableCredits.reduce((sum, credit) => sum + credit.unapplied, 0);
		const applications = [];
		let hasError = false;

		container.querySelectorAll(".application-amount-input").forEach((input) => {
			const amount = parseFloat(input.value || 0);
			if (amount > 0) {
				totalToApply += amount;
			}
		});

		if (totalToApply > totalCredits) {
			alert("إجمالي المبلغ المطبق يتجاوز الأرصدة المتاحة!");
			hasError = true;
			return;
		}

		// Distribute credits FIFO
		let tempCredits = JSON.parse(JSON.stringify(availableCredits));
		container.querySelectorAll(".application-amount-input").forEach((input) => {
			let amountToApply = parseFloat(input.value || 0);
			if (amountToApply > 0) {
				const invoiceId = input.dataset.invoiceId;
				for (const credit of tempCredits) {
					if (amountToApply === 0) break;
					if (credit.unapplied > 0) {
						const applyFromThisCredit = Math.min(amountToApply, credit.unapplied);
						applications.push({
							source_type: credit.type,
							source_id: credit.id,
							target_invoice_id: parseInt(invoiceId),
							amount: formatCurrency(applyFromThisCredit),
						});
						credit.unapplied -= applyFromThisCredit;
						amountToApply -= applyFromThisCredit;
					}
				}
			}
		});

		if (hasError) {
			return;
		}

		applicationsJsonHidden.value = JSON.stringify(applications);
		form.submit();
	});
}

// Initialize if the content is loaded directly
if (document.readyState !== "loading") {
	initArWorkbenchLogic();
} else {
	document.addEventListener("DOMContentLoaded", () => initArWorkbenchLogic());
}