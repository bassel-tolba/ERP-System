from django import template
from decimal import Decimal, InvalidOperation
import json
from django.utils.safestring import mark_safe
from django.utils.functional import Promise
from django.utils.encoding import force_str

register = template.Library()

class LazyEncoder(json.JSONEncoder):
    """
    A custom JSON encoder that can handle Django's lazy translation proxy objects.
    """
    def default(self, obj):
        if isinstance(obj, Promise):
            return force_str(obj)
        return super().default(obj)

@register.filter(name='jsonify')
def jsonify(data):
    """
    Safely converts a Python object (e.g., a list of choices) to a JSON string,
    handling Django's lazy translation proxies.
    """
    return mark_safe(json.dumps(list(data), cls=LazyEncoder))


@register.filter
def get_item(dictionary, key):
    """
    Template filter to get a dictionary item by key.
    Usage: {{ dictionary|get_item:key }}
    """
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None



@register.filter(name='my_abs')
def absolute_value(value):
    """Returns the absolute value of a number."""
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value

@register.filter
def so_status_badge(status):
    """
    Returns a Bootstrap badge color class based on the Sales Order status string.
    """
    status_map = {
        'draft': 'secondary',
        'pending': 'warning',
        'partially_shipped': 'info',
        'completed': 'success',
        'cancelled': 'danger',
    }
    return status_map.get(status, 'secondary') # Return 'secondary' as a default



@register.filter
def multiply(value, arg):
    """Multiplies the value by the arg. Handles Decimals for precision."""
    try:
        # Using str() ensures clean conversion from float/int to Decimal
        return (Decimal(str(value)) * Decimal(str(arg)))
    except (ValueError, TypeError, InvalidOperation):
        # Return a Decimal to prevent further template errors
        return Decimal('0.000')

@register.filter
def subtract(value, arg):
    """Subtracts the arg from the value. Handles Decimals for precision."""
    try:
        return (Decimal(str(value)) - Decimal(str(arg)))
    except (ValueError, TypeError, InvalidOperation):
        return Decimal('0.000')

@register.filter
def status_badge(status_string):
    """Returns a Bootstrap badge class based on an EmployeeAdvance status string."""
    if status_string == 'OPEN':
        return 'bg-danger'
    elif status_string == 'PARTIALLY_SETTLED':
        return 'bg-warning'
    elif status_string == 'SETTLED':
        return 'bg-success'
    return 'bg-secondary'