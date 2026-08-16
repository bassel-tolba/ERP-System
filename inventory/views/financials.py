# gipcco_project/inventory/views/financials.py

"""
This module serves as the main entry point for all financial views.
It imports views from the refactored sub-modules to keep the codebase organized
and to ensure URL routing continues to function as expected.
"""

# flake8: noqa

from .financials.ap_views import *
from .financials.ar_views import *
from .financials.banking_views import *
from .financials.config_views import *
from .financials.gl_views import *
from .financials.overhead_views import *
from .financials.period_views import *