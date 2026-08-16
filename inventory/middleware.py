# gipcco_project/inventory/middleware.py
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _

class FinancialPeriodExceptionHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        # This method is called when a view raises an exception.
        if isinstance(exception, PermissionError):
            # To avoid catching unrelated PermissionErrors, we check if the message
            # matches the one we raise for closed financial periods.
            if "Financial period" in str(exception) and "cannot be posted to" in str(exception):
                # Add a user-friendly error message.
                messages.error(request, str(exception))
                
                # Redirect the user back to the page they came from, with a fallback to the home page.
                referer = request.META.get('HTTP_REFERER', '/')
                return redirect(referer)
        
        # If the exception is not the one we're looking for, do nothing and
        # let Django's default exception handling take over.
        return None
