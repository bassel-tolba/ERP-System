# gipcco_project/inventory/apps.py

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class InventoryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'inventory'
    verbose_name = _("Inventory & Accounting Management")

    def ready(self):
        # This line is crucial for discovering and connecting the signals.
        import inventory.signals