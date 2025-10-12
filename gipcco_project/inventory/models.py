# gipcco_project/inventory/models.py

# This file now serves as the central import point for all models,
# which have been refactored into smaller files inside the 'models' directory.
# This maintains backward compatibility with the rest of the Django project,
# as imports like `from inventory.models import Product` will continue to work.

from .models.accounting_core import *
from .models.accounting_sub_ledger import *
from .models.adjusting_entries import *
from .models.audit_and_closing import *
from .models.bank_reconciliation import *
from .models.expense_workflow import *
from .models.inventory_counts import *
from .models.inventory_management import *
from .models.opening_balance import *
from .models.operational import *
from .models.overhead_allocation import *
from .models.sub_ledger_banking import *
from .models.inventory_counts import *