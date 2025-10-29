# `manage.py` Manifest

This file is a standard command-line utility script that is automatically created by Django when a new project is started. It serves as the primary entry point for interacting with and managing the Django project from the terminal.

## Key Functionalities:

### 1. **Wrapper for `django-admin`**
   - `manage.py` is essentially a thin wrapper around the `django-admin` command. It performs two main tasks before delegating control to Django's core management functionality:
     1.  **Sets `DJANGO_SETTINGS_MODULE`**: It sets the `DJANGO_SETTINGS_MODULE` environment variable to point to the project's `settings.py` file (in this case, `gipcco_project.settings`). This is crucial because it tells Django where to find all the configuration for the project, such as the database connection, installed apps, middleware, etc.
     2.  **Manages Python Path**: It ensures that the project's root directory is on the Python path (`sys.path`), allowing Django to find and import the project's modules.

### 2. **Execution of Management Commands**
   - The core of the script is the call to `execute_from_command_line(sys.argv)`. This function takes the command-line arguments that were passed to `manage.py` and executes the corresponding management command.
   - **Common Commands**: Developers use `manage.py` to run a wide variety of administrative tasks, including:
     - **`python manage.py runserver`**: Starts the development web server to run the application locally.
     - **`python manage.py makemigrations`**: Scans the project's models for changes and creates new database migration files.
     - **`python manage.py migrate`**: Applies the pending database migrations, altering the database schema to match the models.
     - **`python manage.py createsuperuser`**: Creates an administrator account for accessing the Django admin site.
     - **`python manage.py test`**: Discovers and runs the project's automated test suite.
     - **`python manage.py shell`**: Opens an interactive Python shell with the Django project's environment loaded, which is useful for debugging and data exploration.
     - **`python manage.py collectstatic`**: Gathers all static files (CSS, JavaScript, images) from the various apps into a single directory for deployment.
     - **Custom Commands**: Developers can also create their own custom management commands for application-specific tasks (e.g., `python manage.py import_legacy_data`).

In summary, `manage.py` is the developer's primary tool for managing the Django project. It is not typically modified and serves as the command-line interface for running all of Django's built-in and custom administrative tasks.
