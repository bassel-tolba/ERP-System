from django.shortcuts import redirect
from django.contrib import messages
from django.http import HttpRequest, JsonResponse

# ... existing code ...

def receive_payment_for_invoice(request: HttpRequest, invoice_pk: int):
    # ... existing code ...
    try:
        # ... existing code ...
    except (ValueError, TypeError) as e:
        messages.error(request, f"خطأ في البيانات: {e}")
    except Exception as e:
        messages.error(request, f"حدث خطأ غير متوقع: {e}")
        
    return redirect('inventory:view_customer_invoice', pk=invoice_pk)


# --- A/R API Views ---

def api_get_uninvoiced_dispatches(request: HttpRequest, so_id: int) -> JsonResponse:
    # ... existing code ...