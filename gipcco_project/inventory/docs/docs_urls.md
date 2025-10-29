# `urls.py` Manifest

This file is the URL configuration for the `inventory` app. It is responsible for mapping URL paths to their corresponding view functions. This routing is how Django knows which code to execute when a user navigates to a specific web address.

## Key Functionalities:

### 1. **URL to View Mapping**
   - The core of the file is the `urlpatterns` list. This list contains a series of `path()` objects.
   - Each `path()` object defines a mapping between a URL pattern, a view function that should handle requests to that pattern, and a unique `name` for that URL.
   - **Example**: `path('products/', products, name='products')`
     - **URL Pattern**: `'products/'` - This matches the URL `.../inventory/products/`.
     - **View Function**: `products` - This is the function (imported from a `views/*.py` file) that will be executed.
     - **Name**: `'products'` - This is a unique, application-wide name for this URL.

### 2. **Named URLs**
   - The `name` argument in each `path()` is crucial for creating a maintainable application. Instead of hardcoding URLs in templates and other parts of the code, Django's `{% url %}` template tag or `reverse()` function can be used with the name.
   - **Example**: In a template, a link to the products page would be written as `<a href="{% url 'inventory:products' %}">...</a>` instead of `<a href="/inventory/products/">...</a>`.
   - **Benefit**: If the URL pattern for the products page ever needs to change (e.g., to `'all-products/'`), the change only needs to be made in this `urls.py` file. All the templates and code that use the named URL will automatically generate the correct new link without needing to be updated individually.

### 3. **URL Parameters**
   - The URL patterns can capture parts of the URL and pass them as arguments to the view function. This is essential for creating pages that display the details of a specific object.
   - **Example**: `path('product/<int:pk>/', view_product, name='view_product')`
     - The `<int:pk>` part is a path converter. It matches an integer in the URL and captures its value.
     - It then calls the `view_product` function, passing the captured integer as an argument named `pk` (primary key).
     - This allows a single view function to display the details for any product, for example, `/inventory/product/101/` or `/inventory/product/254/`.

### 4. **Inclusion in Project**
   - This `urls.py` file is specific to the `inventory` app. The main project's `urls.py` file (in the `gipcco_project` directory) will include this file, typically with a line like `path('inventory/', include('inventory.urls'))`. This creates a namespace for the app's URLs, so they are all prefixed with `/inventory/`.

### 5. **API Endpoints**
   - This file also defines the routes for the application's API endpoints (e.g., `/api/sellable_stock/`). These URLs are typically called by JavaScript on the frontend to fetch data dynamically without a full page reload.

In summary, `urls.py` acts as the table of contents for the web application, directing incoming browser requests to the correct view function that knows how to handle them.
