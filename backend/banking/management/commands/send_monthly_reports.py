import calendar
import datetime
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None
from django.conf import settings
from accounts.models import User
from banking.models import Transaction


class Command(BaseCommand):
    help = 'Generate and email monthly PDF statements to customers'

    def handle(self, *args, **options):
        if pisa is None:
            self.stdout.write(self.style.ERROR('xhtml2pdf is not installed. Run: pip install xhtml2pdf'))
            return
        
        today = datetime.date.today()
        # previous month
        first = today.replace(day=1)
        last_month = first - datetime.timedelta(days=1)
        month = last_month.month
        year = last_month.year
        self.stdout.write(f'Generating reports for {month}/{year}')
        for user in User.objects.filter(role='CUSTOMER'):
            txs = Transaction.objects.filter(account__user=user,
                                             created_at__year=year,
                                             created_at__month=month)
            if not txs.exists():
                continue
            html = render_to_string('banking/statement_pdf.html', {'transactions': txs, 'user': user})
            result = pisa.CreatePDF(html)
            if result.err:
                self.stdout.write(self.style.ERROR(f'Failed PDF for {user.email}'))
                continue
            pdf_content = result.dest.getvalue()
            email = EmailMessage(
                subject=f'Monthly statement {month}/{year}',
                body='Please find your statement attached.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            email.attach(f'statement_{year}_{month}.pdf', pdf_content, 'application/pdf')
            try:
                email.send()
                self.stdout.write(self.style.SUCCESS(f'Sent statement to {user.email}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error sending to {user.email}: {e}'))
