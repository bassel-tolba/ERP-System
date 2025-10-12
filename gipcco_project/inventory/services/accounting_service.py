# gipcco_project/inventory/services/accounting_service.py

# This file serves as the main entry point for all accounting-related services.
# It imports functions from the refactored, more granular service files
# located in the 'accounting/' subdirectory to maintain backward compatibility
# with the rest of the application.

# No business logic should be added directly to this file. Instead, add it to the
# appropriate file within the 'accounting/' directory and import it here.

from .accounting._helpers import (
    _check_period_is_open,
    _get_product_inventory_account,
    _get_product_expense_account,
    _get_product_revenue_account
)
from .accounting.inventory_transactions import (
    create_je_for_inventory_adjustment,
    create_je_for_inventory_receipt
)
from .accounting.production_transactions import (
    create_je_for_production_consumption,
    create_je_for_finished_goods_receipt,
    create_je_for_production_return
)
from .accounting.sales_transactions import (
    create_je_for_sales_dispatch
)
from .accounting.payment_transactions import (
    create_je_for_supplier_payment,
    create_je_for_customer_payment,
    create_je_for_employee_advance,
    create_je_for_employee_advance_settlement
)
from .accounting.overhead_transactions import (
    create_je_for_overhead_allocation,
    create_je_for_overhead_application
)
from .accounting.asset_transactions import (
    create_je_for_depreciation
)
from .accounting.adjusting_entries import (
    create_je_for_amortization,
    create_je_for_accrual
)
from .accounting.general_transactions import (
    create_je_for_internal_consumption,
    create_je_for_bank_transfer,
    create_je_for_expense_log,
    create_transaction_for_direct_payment_expense,
    create_je_for_opening_balance
)
from .accounting.correction_transactions import (
    correct_approved_expense,
    create_reversing_je_for_correction
)
from .accounting.period_end import (
    run_monthly_depreciation
)

__all__ = [
    # Helpers (Internal)
    '_check_period_is_open',
    '_get_product_inventory_account',
    '_get_product_expense_account',
    '_get_product_revenue_account',

    # Inventory
    'create_je_for_inventory_adjustment',
    'create_je_for_inventory_receipt',

    # Production
    'create_je_for_production_consumption',
    'create_je_for_finished_goods_receipt',
    'create_je_for_production_return',

    # Sales
    'create_je_for_sales_dispatch',

    # Payments
    'create_je_for_supplier_payment',
    'create_je_for_customer_payment',
    'create_je_for_employee_advance',
    'create_je_for_employee_advance_settlement',

    # Overhead
    'create_je_for_overhead_allocation',
    'create_je_for_overhead_application',

    # Assets
    'create_je_for_depreciation',

    # Adjusting Entries
    'create_je_for_amortization',
    'create_je_for_accrual',

    # General / Miscellaneous
    'create_je_for_internal_consumption',
    'create_je_for_bank_transfer',
    'create_je_for_expense_log',
    'create_transaction_for_direct_payment_expense',
    'create_je_for_opening_balance',

    # Corrections
    'correct_approved_expense',
    'create_reversing_je_for_correction',

    # Period End
    'run_monthly_depreciation',
]