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


def _get_product_inventory_account(product: Product) -> Product:
    """Gets the correct inventory account for a product, checking for overrides."""
    if product.override_inventory_account:
        return product.override_inventory_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.inventory_account:
        raise ValueError(_(f"No default inventory account is set for product type '{product.get_product_type_display()}'."))
    return setting.inventory_account

def _get_product_expense_account(product: Product) -> Product:
    """Gets the correct COGS/Expense account for a product, checking for overrides."""
    if product.override_cogs_expense_account:
        return product.override_cogs_expense_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.cogs_or_expense_account:
        raise ValueError(_(f"No default COGS/Expense account is set for product type '{product.get_product_type_display()}'."))
    return setting.cogs_or_expense_account

def _get_product_revenue_account(product: Product) -> Product:
    """Gets the correct Sales Revenue account for a product, checking for overrides."""
    if product.override_sales_revenue_account:
        return product.override_sales_revenue_account
    
    setting = ProductTypeAccountingSettings.objects.filter(product_type=product.product_type).first()
    if not setting or not setting.sales_revenue_account:
        raise ValueError(_(f"No default sales revenue account is set for product type '{product.get_product_type_display()}'."))
    return setting.sales_revenue_account
