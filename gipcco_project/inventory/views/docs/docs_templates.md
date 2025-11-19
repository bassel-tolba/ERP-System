<!-- gipcco_project/inventory/views/docs/templates.md -->
<!-- gipcco_project/inventory/views/templates.py -->
# File: gipcco_project/inventory/views/templates.py
- **Purpose:** Provides the UI for CRUD (Create, Read, Update, Delete) operations on `ShopOrderTemplate` models, which represent the Bill of Materials (BOM) or "recipe" for finished products.

### Architectural Pattern
- **Thicker Views:** Unlike most other views in the application, these views contain more direct business and data manipulation logic. They interact directly with the Django ORM (`ShopOrderTemplate.objects.create`, `.delete()`, etc.) within `transaction.atomic()` blocks instead of delegating these tasks to a dedicated service layer. This is a notable exception to the "Thin View, Fat Service" pattern seen elsewhere.

### Functions

- `shop_order_templates(request)`:
  - **Description:** A combined view that lists all existing templates and handles the form submission for creating a new one. It also supports a "copy from" feature to pre-populate the form.
  - **Workflow (POST):**
    1.  Extracts template name, final product, and a list of raw materials and quantities from `request.POST`.
    2.  Wraps the creation logic in a `transaction.atomic()` block to ensure atomicity.
    3.  Directly creates the `ShopOrderTemplate` header record.
    4.  Directly creates the associated `TemplateItem` line items in a `bulk_create` operation for efficiency.
  - **Calls:** None (Direct ORM interaction).

- `delete_shop_order_template(request, pk)`:
  - **Description:** A POST-only view that deletes a `ShopOrderTemplate`.
  - **Workflow:**
    1.  Fetches the `ShopOrderTemplate` object.
    2.  Directly calls `.delete()` on the object. The database's `on_delete=models.CASCADE` on the `TemplateItem` model handles the deletion of line items.
  - **Calls:** None (Direct ORM interaction).

- `view_shop_order_template(request, pk)`:
  - **Description:** Displays the details of a single `ShopOrderTemplate` and its constituent items.
  - **Calls:** None (Direct ORM interaction).

- `edit_shop_order_template(request, pk)`:
  - **Description:** Handles both displaying the edit form and processing the update submission for a `ShopOrderTemplate`.
  - **Workflow (POST):**
    1.  Extracts all template and item data from `request.POST`.
    2.  Wraps the update logic in a `transaction.atomic()` block.
    3.  Updates the fields on the main `ShopOrderTemplate` object.
    4.  Performs a "delete-then-create" operation for the line items: it deletes all existing `TemplateItem` records and then bulk-creates the new set of items from the form data.
  - **Calls:** None (Direct ORM interaction).