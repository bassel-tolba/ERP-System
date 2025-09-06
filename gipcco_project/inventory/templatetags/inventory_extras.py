from django import template

register = template.Library()

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