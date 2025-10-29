# `middleware.py` Manifest

This file contains custom Django middleware. Middleware in Django is a framework of hooks into Django's request/response processing. It's a light, low-level "plugin" system for globally altering Django's input or output.

## Middleware Defined:

### 1. **`FinancialPeriodExceptionHandlerMiddleware`**
   - **Purpose**: To provide a user-friendly experience when a user attempts to perform an action that violates the closed financial period rule.
   - **How it Works**:
     - The `_check_period_is_open` helper function (in `services/accounting/_helpers.py`) is the gatekeeper for all financial transactions. When a user tries to post a transaction to a closed or locked period, this function raises a `PermissionError` with a specific message (e.g., "Financial period 'September 2023' is Closed and cannot be posted to.").
     - Without this middleware, a `PermissionError` would typically result in a generic "Server Error (500)" page, which is unhelpful for the user.
     - This middleware intercepts exceptions that occur during the request-response cycle. The `process_exception` method is specifically designed to catch exceptions raised by views.
   - **Specific Logic**:
     - It checks if the caught exception is an instance of `PermissionError`.
     - To ensure it only handles the specific error it's designed for, it inspects the exception's message to see if it contains the key phrases related to a closed financial period.
     - If it matches, the middleware does two things:
       1.  It uses Django's `messages` framework to add a user-friendly error message to the request. This message will be displayed as a prominent notification on the next page the user sees.
       2.  It redirects the user back to the page they came from (`HTTP_REFERER`). This prevents them from seeing the ugly error page and instead returns them to the form they were on, where they can see the error message and correct their mistake (e.g., by changing the transaction date).
     - If the exception is not the specific `PermissionError` it's looking for, the middleware does nothing (`return None`), allowing Django's standard error handling to proceed.

This middleware is a key piece of the user experience, transforming a potentially confusing system-level error into a clear, actionable notification for the end-user, guiding them to correct their input without interrupting their workflow.
