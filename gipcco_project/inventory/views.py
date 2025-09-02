import logging

# Get an instance of the logger for this module
logger = logging.getLogger(__name__)

# Import all views from submodules
from .views.batches import *
from .views.companies_products import *
from .views.dashboard import *
from .views.production_returns import *
from .views.opening_balances import *
from .views.analysis_ledger_visuals import *
from .views.api import *
