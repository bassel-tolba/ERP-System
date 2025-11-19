<!-- gipcco_project/inventory/views/docs/users.md -->
<!-- gipcco_project/inventory/views/users.py -->
# File: gipcco_project/inventory/views/users.py
- **Purpose:** Provides the UI for managing system users and permission groups. These views interact directly with Django's built-in authentication framework (`django.contrib.auth`).

### Architectural Pattern
- **Direct Framework Interaction:** This module does not use the application's custom service layer. Instead, it directly and correctly uses the models and managers provided by `django.contrib.auth` for all user and group management tasks. This is the standard and recommended practice for handling authentication and authorization in Django.

### Functions

- `manage_users(request)`:
  - **Description:** Lists all users and handles the creation of new users.
  - **Workflow (POST):**
    1.  Validates user permissions (`auth.add_user`).
    2.  Performs basic validation (e.g., passwords match).
    3.  Uses `User.objects.create_user()` to correctly create a new user with a hashed password.
    4.  Sets staff/superuser status and assigns the user to selected groups.
  - **Security:** Requires `auth.view_user` for GET and `auth.add_user` for POST.

- `edit_user(request, pk)`:
  - **Description:** A POST-only view to update an existing user's details, password, and group memberships.
  - **Validation & Security:**
    1.  Requires `auth.change_user` permission.
    2.  Includes a critical check to prevent non-superusers from escalating their own or others' privileges to superuser status.
    3.  Checks for username uniqueness to avoid `IntegrityError`.
    4.  Uses `user.set_password()` to correctly handle password hashing if a new password is provided.

- `delete_user(request, pk)`:
  - **Description:** A POST-only view to delete a user.
  - **Validation & Security:**
    1.  Requires `auth.delete_user` permission.
    2.  Prevents the deletion of superusers.
    3.  Prevents a user from deleting their own account.

- `manage_groups(request)`:
  - **Description:** Lists all permission groups and handles the creation of new groups.
  - **Business Logic:** It fetches all available `Permission` objects and groups them by application/model to provide a user-friendly interface for assigning permissions in the edit modal.
  - **Security:** Requires `auth.view_group` for GET and `auth.add_group` for POST.

- `edit_group(request, pk)`:
  - **Description:** A POST-only view to update a group's name and its set of associated permissions.
  - **Workflow:** Updates the group's name and uses `.permissions.set()` to atomically update the many-to-many relationship with the selected permissions.
  - **Security:** Requires `auth.change_group` permission.

- `delete_group(request, pk)`:
  - **Description:** A POST-only view to delete a group.
  - **Validation & Security:**
    1.  Requires `auth.delete_group` permission.
    2.  Prevents deletion of a group if it is still assigned to any users, protecting data integrity.