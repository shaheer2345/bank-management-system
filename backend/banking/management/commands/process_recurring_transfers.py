from django.core.management.base import BaseCommand
from django.utils import timezone

from banking.models import RecurringTransfer


class Command(BaseCommand):
    help = 'Process due recurring transfers'

    def handle(self, *args, **options):
        today = timezone.now().date()
        due = RecurringTransfer.objects.filter(next_transfer_date__lte=today)
        count = 0
        for rt in due:
            try:
                performed = rt.execute()
                if performed:
                    count += 1
                    self.stdout.write(self.style.SUCCESS(f'Processed recurring transfer {rt.id}'))
                else:
                    self.stdout.write(self.style.WARNING(f'Skipped recurring transfer {rt.id} (insufficient funds)'))
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f'Error processing {rt.id}: {exc}'))
        self.stdout.write(f'Total processed: {count}')
