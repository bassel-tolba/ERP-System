from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def abs_filter(value):
    """Returns the absolute value of a number."""
    return abs(value)

@register.filter(name='mul')
def multiply(value, arg):
    """Multiply two numeric values, supports Decimal, int, and float.
    Returns empty string if inputs are invalid.
    """
    try:
        # Try Decimal multiplication for precision if possible
        return (Decimal(str(value)) * Decimal(str(arg)))
    except (InvalidOperation, ValueError, TypeError):
        try:
            return float(value) * float(arg)
        except (ValueError, TypeError):
            return ''
