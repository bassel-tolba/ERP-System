# gipcco_project/inventory/management/commands/post_depreciation.py

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inventory.services.accounting_service import create_je_for_monthly_depreciation

class Command(BaseCommand):
    help = 'Calculates and posts the monthly depreciation for all eligible fixed assets.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Specify the year to run depreciation for (e.g., 2023). Defaults to the previous month\'s year.'
        )
        parser.add_argument(
            '--month',
            type=int,
            help='Specify the month to run depreciation for (e.g., 11 for November). Defaults to the previous month.'
        )

    def handle(self, *args, **options):
        year = options['year']
        month = options['month']

        if not year or not month:
            # Default to the previous month if not specified
            today = timezone.now().date()
            first_of_this_month = today.replace(day=1)
            last_day_of_previous_month = first_of_this_month - timezone.timedelta(days=1)
            year = last_day_of_previous_month.year
            month = last_day_of_previous_month.month
        
        self.stdout.write(f"Running depreciation calculation for {year}-{month:02d}...")

        try:
            journal_entry = create_je_for_monthly_depreciation(year=year, month=month)
            if journal_entry:
                self.stdout.write(self.style.SUCCESS(
                    f"Successfully posted depreciation. Journal Entry JE-{journal_entry.id} created."
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    "Depreciation process completed, but no new journal entry was created (assets may be up-to-date)."
                ))
        except Exception as e:
            raise CommandError(f"An error occurred during depreciation posting: {e}")