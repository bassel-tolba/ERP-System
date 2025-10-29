# `urls.py` (Project Level) Manifest

This file is the **root URL configuration** for the entire Django project. It is the first place Django looks to determine how to route an incoming URL request.

## Key Functionalities:

### 1. **`urlpatterns` List**
   - This list contains the top-level URL patterns for the project. Each `path()` in this list defines a segment of the URL and delegates the handling of the rest of the URL to another module.

### 2. **Admin URL**
   - `path('admin/', admin.site.urls)`: This is a standard Django entry. It routes any URL that starts with `/admin/` to the built-in Django administration site.

### 3. **Authentication URLs**
   - `path('accounts/', include('django.contrib.auth.urls'))`: This line includes all of Django's built-in authentication URLs. This is a convenient shortcut that automatically sets up the URLs for common authentication views, such as:
     - `/accounts/login/`
     - `/accounts/logout/`
     - `/accounts/password_change/`
     - `/accounts/password_reset/`
     - And others.

### 4. **Application URL Inclusion**
   - `path('', include('inventory.urls'))`: This is the most important line for our application.
     - **`include('inventory.urls')`**: This function tells Django to hand off any URL that matches the pattern to the `urls.py` file located inside the `inventory` app for further processing.
     - **`path('', ...)`**: Because the URL pattern is an empty string, it means that the root URL of the site (e.g., `http://127.0.0.1:8000/`) and any path that doesn't match the other patterns (`/admin/`, `/accounts/`) will be passed to the `inventory` app's URL configuration.
     - **Effect**: This makes the `inventory` app the primary, user-facing application for the entire project. A URL like `http://127.0.0.1:8000/products/` will be processed by this file, which will match the empty string `''`, strip it away, and pass the remaining part (`products/`) to `inventory/urls.py` to find the final view.

In summary, this project-level `urls.py` file acts as a primary router or switchboard. It doesn't handle most URLs directly but instead delegates them to the appropriate application (the admin site, the auth system, or our main `inventory` app) based on the URL's prefix.
