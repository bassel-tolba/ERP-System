# AI Agent Instructions for the Gipcco Inventory Management System

This document provides instructions for AI coding agents to effectively contribute to the Gipcco Inventory Management System, a Django-based application.

## Project Overview

The Gipcco Inventory Management System is a comprehensive Django application designed to manage inventory, production, and accounting processes. The core functionality resides in the `inventory` app, which handles everything from raw material procurement to finished product sales.

### Key Components

- **`inventory` app**: The main application containing all models, views, templates, and business logic.
- **`gipcco_project`**: The Django project directory, containing settings, URL configurations, and WSGI application.
- **`static`**: Contains static assets like CSS, JavaScript, and images.
- **`templates`**: Contains Django templates for rendering HTML pages.

## Architecture

The project follows a standard Django architecture, with a clear separation of concerns between models, views, and templates.

- **Models (`inventory/models.py`)**: The data models are well-defined and represent the core entities of the system, including products, companies, batches, purchase orders, and inventory logs. The models make extensive use of foreign keys to establish relationships between different entities.
- **Views (`inventory/views/`)**: The views are organized into separate files based on their functionality (e.g., `batches.py`, `products.py`, `purchase_orders.py`). This modular approach makes it easy to locate and maintain the code for specific features.
- **URLs (`gipcco_project/urls.py`, `inventory/urls.py`)**: The URL configuration is centralized in the `inventory` app, with the project-level `urls.py` simply including the app's URL patterns. This keeps the URL structure clean and maintainable.
- **Services (`inventory/services/`)**: The application uses a service layer to encapsulate complex business logic. This is a key architectural pattern.
    - `costing_service.py`: Handles inventory valuation and cost calculation. The `get_inventory_state_at_datetime` function is crucial for historical reporting.
    - `accounting_service.py`: Manages the creation of journal entries for all inventory-related transactions, ensuring financial accuracy.
- **Signal-based Automation (`inventory/signals.py`)**: The application uses Django signals to automatically trigger the creation of journal entries when key models (like `InventoryLog`, `Batch`, `Payment`) are saved or deleted. This decouples the accounting logic from the core business operations.

## Frontend Architecture

The frontend is designed to feel like a Single-Page Application (SPA) without being a complex JavaScript framework.

- **Dynamic Content Loading (`static/layout/js/dynamic_content_loader.js`)**: This is the core script that handles navigation. It intercepts link clicks, fetches HTML fragments from the server, and injects them into the main content area, avoiding full page reloads.
- **JavaScript Initialization**: Because content is loaded dynamically, the global function `window.initializePluginsInContent` is called after every content load. This function is responsible for initializing JavaScript plugins (like `flatpickr`, `TomSelect`) on the newly added HTML.
- **Page-Specific Logic**: JavaScript for specific pages is organized into separate files in `static/layout/js/` (e.g., `dashboard_logic.js`). The dynamic loader identifies which initializer function to run based on selectors present in the loaded content.
- **Django to JS Communication**: The `layout.html` template defines a global `window.appUrls` object. This is the primary way to safely pass Django URL patterns to the frontend JavaScript.

## API

The application includes a RESTful API for programmatic access to data.

- **Endpoints**: The API endpoints are defined in `inventory/views/api.py` and exposed under the `/api/` URL prefix.
- **Functionality**: The API provides access to data such as product tags, open purchase orders, and batch details.

## Accounting Logic

The application's accounting logic is a critical component of the system.

- **Financial Periods**: The `FinancialPeriod` model is used to define accounting periods. Transactions cannot be posted to closed periods.
- **Journal Entries**: The `accounting_service.py` is responsible for creating balanced, double-entry journal entries for all relevant transactions.
- **Account Configuration**: The `GeneralAccountingSettings` and `ProductTypeAccountingSettings` models are used to configure the accounts used in journal entries.

## Developer Workflows

### Running the Development Server

To run the development server, use the following command:

```bash
python manage.py runserver
```

### Running Tests

The project includes a `tests.py` file in the `inventory` app, but it is currently empty. To run the tests, use the following command:

```bash
python manage.py test
```

### Database Migrations

To create and apply database migrations, use the following commands:

```bash
python manage.py makemigrations
python manage.py migrate
```

## Conventions and Patterns

- **Internationalization**: The application uses `gettext_lazy` for verbose names in the models, indicating that it is designed to support multiple languages.
- **Logging**: The project has a well-configured logging system that writes logs to a rotating file (`gipcco.log`).
- **Atomic Transactions**: The views use `transaction.atomic()` to ensure data integrity when performing database operations.
- **Service Layer**: The use of a service layer for complex business logic is a key architectural pattern in this project.
- **Fat Models**: The `inventory/models.py` file follows the 'Fat Models' principle. Business logic, calculations (via `@property`), and validation (via `clean()` methods) are often placed directly within the model classes.

## Key Files and Directories

- **`inventory/models.py`**: Contains the core data models for the application.
- **`inventory/signals.py`**: Contains the signal handlers that trigger accounting logic.
- **`inventory/views/`**: Contains the view logic, organized by feature.
- **`inventory/services/costing_service.py`**: Contains the logic for calculating product costs.
- **`inventory/services/accounting_service.py`**: Contains the logic for creating journal entries.
- **`inventory/views/api.py`**: Contains the API view logic.
- **`inventory/urls.py`**: Defines the URL patterns for the `inventory` app.
- **`gipcco_project/settings.py`**: Contains the project's configuration settings.
- **`static/layout/js/dynamic_content_loader.js`**: The core script for the SPA-like frontend behavior.
- **`static/layout/js/`**: Directory containing page-specific JavaScript files.
