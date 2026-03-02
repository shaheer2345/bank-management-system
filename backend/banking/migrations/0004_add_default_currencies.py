from django.db import migrations


def create_currencies(apps, schema_editor):
    Currency = apps.get_model('banking', 'Currency')
    Currency.objects.update_or_create(code='USD', defaults={'name': 'US Dollar', 'rate_to_usd': '1'})
    Currency.objects.update_or_create(code='EUR', defaults={'name': 'Euro', 'rate_to_usd': '1.1'})
    Currency.objects.update_or_create(code='GBP', defaults={'name': 'British Pound', 'rate_to_usd': '1.3'})


def reverse_currencies(apps, schema_editor):
    Currency = apps.get_model('banking', 'Currency')
    Currency.objects.filter(code__in=['USD', 'EUR', 'GBP']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('banking', '0003_currency_account_currency'),
    ]

    operations = [
        migrations.RunPython(create_currencies, reverse_currencies),
    ]
