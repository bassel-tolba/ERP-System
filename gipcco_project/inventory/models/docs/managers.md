<!-- gipcco_project/inventory/models/managers.py -->
# File: gipcco_project/inventory/models/managers.py
**Purpose:** This file defines custom `QuerySet` classes that encapsulate complex, reusable database query logic. By attaching these querysets to models via custom managers, we establish a single, authoritative source of truth for critical calculations like "quantity on hand". This architectural pattern is vital for maintaining data integrity, improving performance, and keeping business logic DRY (Don't Repeat Yourself).

### Class: `InventoryLogQuerySet`
- **Description:** A custom queryset attached to the `InventoryLog` model. Its primary responsibility is to provide the definitive, system-wide method for calculating the real-time available stock for any given raw material or MRO inventory receipt. It correctly accounts for all possible inflows and outflows.

- **Method: `with_remaining_quantity()`**
    - **Description:** This is the cornerstone method of the queryset. It annotates each `InventoryLog` object with a calculated field, `remaining_quantity`, which represents the current sellable or consumable stock from that specific receipt.
    - **Business Logic:** The available quantity is calculated using the following formula:
      `remaining_quantity = initial_quantity - consumed_in_production - consumed_internally + returned_from_production +/- adjustments`
    - **Workflow:**
        1.  Starts with the `quantity` field from the `InventoryLog` record (the initial receipt amount).
        2.  **Subtracts** the sum of all `actual_quantity` from related `BatchItem` records (stock consumed for manufacturing).
        3.  **Subtracts** the sum of `quantity_consumed` from related `InventoryConsumption` records (stock used for internal purposes like maintenance).
        4.  **Adds** back the sum of `quantity` from related `ProductionReturn` records (unused stock returned from the factory floor).
        5.  **Adds or Subtracts** the sum of `adjustment_quantity` from related `InventoryAdjustment` records (corrections from cycle counts, damages, etc.).
    - **Performance Considerations / Design Pattern:**
        - **Critical Pattern:** This method expertly avoids the "JOIN multiplication bug" by using Django's `Subquery` object for each aggregation.
        - **Why it Matters:** A naive approach using multiple `annotate(Sum(...))` calls on the same queryset would create a Cartesian product if a log has multiple consumptions AND multiple adjustments, leading to massively inflated (and incorrect) sums.
        - **Implementation:** Each outflow/inflow (production, internal consumption, returns, adjustments) is calculated in a separate, isolated subquery. The results are then combined at the top level using `Coalesce` to handle cases where there are no related records (returning `Decimal('0.0')` instead of `None`). This ensures both correctness and performance at scale.
    - **Integration Points:**
        - This queryset is the **single source of truth** for raw material availability.
        - **Upstream:** It is used by services like `batch_service` and `approval_service` to validate stock before allowing production or internal consumption to proceed.
        - **Downstream:** It is used by the `adjustment_service` to snapshot the system quantity for physical inventory counts.
        - **Lateral:** It's used by any API or report that needs to display current stock levels.

### Class: `FinishedProductReceiptQuerySet`
- **Description:** A custom queryset attached to the `FinishedProductReceipt` model. It serves as the single, authoritative source for calculating the available stock of any given batch of finished goods.

- **Method: `with_remaining_quantity()`**
    - **Description:** Annotates each `FinishedProductReceipt` object with a `remaining_quantity` field, representing the current stock available for sale from that production receipt.
    - **Business Logic:** The available quantity is calculated using the following formula:
      `remaining_quantity = total_quantity_produced - total_dispatched +/- total_adjusted`
    - **Workflow:**
        1.  Starts with the `total_quantity_produced` from the `FinishedProductReceipt`.
        2.  **Subtracts** the sum of `quantity` from all related `FinishedProductDispatch` records (stock sold and shipped to customers).
        3.  **Adds or Subtracts** the sum of `adjustment_quantity` from related `InventoryAdjustment` records (e.g., stock added back from a sales return, or removed due to damage).
    - **Performance Considerations / Design Pattern:**
        - Employs the same critical `Subquery` and `Coalesce` pattern as `InventoryLogQuerySet` to guarantee accurate calculations and prevent performance degradation from incorrect database joins. This is essential for a system with a high volume of sales and adjustments.
    - **Integration Points:**
        - This queryset is the **single source of truth** for finished good availability.
        - **Upstream:** Critically used by the `sales_service` during the dispatch process to validate that sufficient stock is on hand before confirming a shipment.
        - **Downstream:** Used by the `adjustment_service` to snapshot system quantities for physical counts of finished goods.
        - **Lateral:** Powers any API, report, or dashboard that displays sellable inventory levels.