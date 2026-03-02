from django.core.management.base import BaseCommand
from django.utils import timezone
from loans.models import Loan
from django.core.mail import send_mail
from django.conf import settings

class Command(BaseCommand):
    help = 'Send email reminders for loans with due date today or past due'

    def handle(self, *args, **options):
        today = timezone.now().date()
        loans = Loan.objects.filter(next_due_date__lte=today, status='APPROVED')
        for loan in loans:
            try:
                send_mail(
                    'Loan payment due',
                    f'Your loan {loan.id} has a payment due on {loan.next_due_date}.',
                    settings.DEFAULT_FROM_EMAIL,
                    [loan.user.email],
                )
                self.stdout.write(self.style.SUCCESS(f'Sent reminder for loan {loan.id}'))
            except Exception as e:
                self.stderr.write(f'Failed to send for loan {loan.id}: {e}')
