import logging
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission

logger = logging.getLogger(__name__)

# Define roles and their permissions for clarity and maintainability
ROLES = {
    "Production Planner": {
        "permissions": [
            # Default Django permissions
            ("inventory", "add_batch"),
            ("inventory", "change_batch"),
            ("inventory", "view_batch"),
            ("inventory", "add_productionreturn"),
            ("inventory", "view_productionreturn"),
            # Custom permissions
            ("inventory", "can_submit_batch"),
        ]
    },
    "Production Manager": {
        "permissions": [
            # Default Django permissions
            ("inventory", "add_batch"),
            ("inventory", "change_batch"),
            ("inventory", "view_batch"),
            ("inventory", "delete_batch"), # Managers can delete drafts
            ("inventory", "add_productionreturn"),
            ("inventory", "view_productionreturn"),
            # Custom permissions
            ("inventory", "can_approve_batch"),
            ("inventory", "can_start_production"),
            ("inventory", "can_cancel_batch"),
        ]
    },
}

class Command(BaseCommand):
    help = "Creates and configures the necessary user groups and permissions for the batch production workflow."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting setup of batch workflow permissions..."))

        for group_name, group_data in ROLES.items():
            self.stdout.write(f"  Configuring group: '{group_name}'")
            
            group, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"    - Group '{group_name}' created."))
            
            group.permissions.clear()
            
            permissions_to_add = []
            for app_label, codename in group_data["permissions"]:
                try:
                    permission = Permission.objects.get(content_type__app_label=app_label, codename=codename)
                    permissions_to_add.append(permission)
                except Permission.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"    - WARNING: Permission '{app_label}.{codename}' not found. Skipping."))
            
            group.permissions.add(*permissions_to_add)
            self.stdout.write(self.style.SUCCESS(f"    - Assigned {len(permissions_to_add)} permissions to '{group_name}'."))

        self.stdout.write(self.style.SUCCESS("\nSuccessfully set up all batch workflow permissions and groups."))
