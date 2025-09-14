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
- **Services (`inventory/services/`)**: The application uses a service layer to encapsulate complex business logic, such as the `costing_service.py` for calculating product costs. This separation of concerns helps to keep the views and models clean and focused on their primary responsibilities.

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

## Key Files and Directories

- **`inventory/models.py`**: Contains the core data models for the application.
- **`inventory/views/`**: Contains the view logic, organized by feature.
- **`inventory/services/costing_service.py`**: Contains the logic for calculating product costs.
- **`inventory/urls.py`**: Defines the URL patterns for the `inventory` app.
- **`gipcco_project/settings.py`**: Contains the project's configuration settings.
