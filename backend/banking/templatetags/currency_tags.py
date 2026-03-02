from django import template
from django.utils.formats import localize

register = template.Library()

@register.filter
def format_currency(value, code=None):
    """Format a decimal value with optional currency code symbol/abbrev.

    Uses Django's localization to add thousands separators/decimal point.
    """
    try:
        val = localize(value)
    except Exception:
        val = value
    if code:
        return f"{val} {code}"
    return val
