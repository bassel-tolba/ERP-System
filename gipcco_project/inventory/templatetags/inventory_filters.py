from django import template

register = template.Library()

@register.filter
def abs_filter(value):
    """Returns the absolute value of a number."""
    return abs(value)
