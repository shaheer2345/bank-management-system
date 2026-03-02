import requests
from django.core.management.base import BaseCommand

from banking.models import Currency
from django.conf import settings


class Command(BaseCommand):
    help = 'Fetch latest foreign exchange rates and update Currency table'

    def handle(self, *args, **options):
        # using exchangerate.host which is free and requires no key
        url = 'https://api.exchangerate.host/latest?base=USD'
        self.stdout.write(f'Fetching rates from {url}')
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            rates = data.get('rates', {})
            updated = 0
            for code, rate in rates.items():
                # only update currencies we already track
                try:
                    cur = Currency.objects.get(code=code)
                    if cur.rate_to_usd != rate:
                        cur.rate_to_usd = rate
                        cur.save()
                        updated += 1
                except Currency.DoesNotExist:
                    continue
            self.stdout.write(self.style.SUCCESS(f'Updated {updated} currencies'))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'Failed to fetch rates: {exc}'))
