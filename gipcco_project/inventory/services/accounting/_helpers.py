# gipcco_project/inventory/services/accounting/_helpers.py

import logging
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import PermissionDenied

from ...models import (
    FinancialPeriod, Product, ProductTypeAccountingSettings
)

logger = logging.getLogger(__name__)


def _check_period_is_open(date_to_check):
    """
    Checks if the given date falls within an open financial period.
    This is the authoritative gatekeeper for all financially relevant transactions.
    It raises a PermissionError if the period is closed or locked.
    """
    # Ensure we use the date part if a datetime is passed
    check_date = date_to_check.date() if hasattr(date_to_check, 'date') else date_to_check
    try:
        period = FinancialPeriod.objects.get(
            start_date__lte=check_date,
            end_date__gte=check_date
        )
        if period.status in [FinancialPeriod.Status.CLOSED, FinancialPeriod.Status.PERMANENTLY_LOCKED]:
            raise PermissionDenied(
                _(f"Financial period '{period.name}' for date {check_date} is {period.get_status_display()} and cannot be posted to.")
            )
    except FinancialPeriod.DoesNotExist:
        raise PermissionDenied(_(f"No financial period found for date {check_date}. Please create one."))
    except FinancialPeriod.MultipleObjectsReturned:
        # This indicates a serious data integrity issue that must be resolved.
        logger.error(f"CRITICAL: Overlapping financial periods found for date {check_date}.")
        raise PermissionDenied(_(f"Configuration error: Overlapping financial periods exist for date {check_date}. Contact administrator."))


def _get_product_account(product: Product, account_type: str):
    """
    Generic account resolver for products. This is the single source of truth
    for finding a product-related GL account.

    It follows the logic:
    1. Check for a specific override account on the Product instance.
    2. If not found, fall back to the default account defined on the
       ProductTypeAccountingSettings for the product's type.
    3. Raise a ValueError if no account can be resolved.
    """
    ACCOUNT_TYPE_MAPPING = {
        'inventory': {
            'override_field': 'override_inventory_account',
            'setting_field': 'inventory_account',
            'error_name': 'inventory'
        },
        'cogs': {
            'override_field': 'override_cogs_expense_account',
            'setting_field': 'cogs_or_expense_account',
            'error_name': 'COGS/Expense'
        },
        'revenue': {
            'override_field': 'override_sales_revenue_account',
            'setting_field': 'sales_revenue_account',
            'error_name': 'sales revenue'
        }
    }

    mapping = ACCOUNT_TYPE_MAPPING.get(account_type)
    if not mapping:
        raise ValueError(f"Invalid account_type '{account_type}' requested for product account resolution.")

    override_account = getattr(product, mapping['override_field'], None)
    if override_account:
        return override_account

    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if setting:
        setting_account = getattr(setting, mapping['setting_field'], None)
        if setting_account:
            return setting_account

    raise ValueError(_(f"No default {mapping['error_name']} account is set for product type '{product.get_product_type_display()}'."))


def _get_product_inventory_account(product: Product):
    """Gets the correct inventory account for a product using the generic resolver."""
    return _get_product_account(product, 'inventory')

def _get_product_expense_account(product: Product):
    """Gets the correct COGS/Expense account for a product using the generic resolver."""
    return _get_product_account(product, 'cogs')

def _get_product_revenue_account(product: Product):
    """Gets the correct Sales Revenue account for a product using the generic resolver."""
    return _get_product_account(product, 'revenue')
