# File: gipcco_project/inventory/views/sales.py
- **Purpose:** Handles all user-facing HTTP requests related to the sales workflow, including Customers, Sales Orders, Dispatches, and Sales Returns. It acts as the presentation layer, gathering user input and calling the appropriate service functions to perform business logic.

### Customer Views
- `customers(request)`: Manages the customer list and creation form.
- `edit_customer(request, pk)`: Handles editing a customer's details.
- `delete_customer(request, pk)`: Handles deleting a customer.

### Sales Order Views
- `sales_orders(request)`: Displays a list of all sales orders with search functionality.
- `create_sales_order(request)`: Handles the form for creating a new `SalesOrder` and its `SalesOrderItem`s.
- `view_sales_order(request, pk)`: Displays the details of a single sales order, its items, and their dispatch status.
- `delete_sales_order(request, pk)`: Handles deleting a sales order, preventing deletion if dispatches exist.
- `edit_sales_order_item(request, pk)`: Handles editing a sales order item.
- `delete_sales_order_item(request, pk)`: Handles deleting a sales order item.

### Dispatch Views
- `dispatch_from_sales_order(request, so_pk)`: **Refactored View.** Gathers dispatch quantities and dates from the user form.
  - **Calls:** `sales_service.dispatch_from_sales_order()` to perform all business logic, including stock validation, cost calculation, and database updates.
- `create_dispatch(request, so_item_pk)`: Handles creating a dispatch for a single item (likely from a modal or specific action).
- `edit_dispatch(request, pk)`: Handles editing an existing dispatch record.
- `delete_dispatch(request, pk)`: Handles deleting a dispatch record.

### Sales Return Views
- `sales_returns_list(request)`: **New View.** Displays a list of all `SalesReturn` records.
- `view_sales_return(request, pk)`: **New View.** Shows the details of a specific `SalesReturn`, its items, and displays a form to create a credit memo if one does not already exist.
- `create_credit_memo_from_return_view(request, return_pk)`: **New View.** Handles the form submission for creating a `CustomerCreditMemo`.
  - **Calls:** `sales_return_service.create_credit_memo_from_return()` to execute the business logic for credit memo creation.
