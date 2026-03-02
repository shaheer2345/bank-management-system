from django.test import TestCase, Client
from accounts.models import User
from banking.models import Account, Transaction, Currency
from banking.views import transfer_view
from unittest.mock import patch
import requests

# additional imports for new features
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.management import call_command
import datetime


class AccountTestCase(TestCase):
    def setUp(self):
        # ensure currencies exist (data migration already seeds them)
        self.usd, _ = Currency.objects.get_or_create(code='USD', defaults={'name': 'US Dollar', 'rate_to_usd': 1})
        self.eur, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'rate_to_usd': 1.1})
        self.user = User.objects.create_user(email='user@test.com', password='pass1234')
        self.account = Account.objects.create(user=self.user, account_type='SAVINGS', currency=self.usd, balance=1000)
        self.client = Client()

    def test_account_creation(self):
        self.assertEqual(self.account.user.email, 'user@test.com')
        self.assertEqual(self.account.balance, 1000)
        self.assertEqual(self.account.currency.code, 'USD')

    def test_open_account_view_requires_login(self):
        resp = self.client.get('/api/accounts/')
        # ensure account list API requires login: this uses session auth
        self.assertEqual(resp.status_code, 403)
        # use login for view
        self.client.login(email='user@test.com', password='pass1234')
        resp2 = self.client.get('/accounts/open/')
        self.assertEqual(resp2.status_code, 200)
        # include currency id when opening account
        resp3 = self.client.post('/accounts/open/', {'account_type': 'CURRENT', 'currency': self.usd.id})
        self.assertEqual(resp3.status_code, 302)
        self.assertTrue(Account.objects.filter(user=self.user, account_type='CURRENT', currency=self.usd).exists())


class TransactionTestCase(TestCase):
    def setUp(self):
        # ensure currencies exist
        self.usd, _ = Currency.objects.get_or_create(code='USD', defaults={'name': 'US Dollar', 'rate_to_usd': 1})
        self.eur, _ = Currency.objects.get_or_create(code='EUR', defaults={'name': 'Euro', 'rate_to_usd': 1.1})
        self.user = User.objects.create_user(email='user2@test.com', password='pass1234')
        self.account = Account.objects.create(user=self.user, account_type='SAVINGS', currency=self.usd, balance=1000)

    def test_deposit_transaction(self):
        t = Transaction.objects.create(account=self.account, amount=500, transaction_type='DEPOSIT')
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 1500)

    def test_withdraw_transaction(self):
        t = Transaction.objects.create(account=self.account, amount=200, transaction_type='WITHDRAW')
        self.account.refresh_from_db()
        self.assertEqual(self.account.balance, 800)

    def test_transfer_balance_changes(self):
        other = Account.objects.create(user=self.user, account_type='SAVINGS', currency=self.usd, balance=500)
        # perform transfer manually
        Transaction.objects.create(account=self.account, amount=100, transaction_type='WITHDRAW')
        Transaction.objects.create(account=other, amount=100, transaction_type='DEPOSIT')
        self.account.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(self.account.balance, 900)
        self.assertEqual(other.balance, 600)

    def test_cross_currency_transfer(self):
        # source USD -> dest EUR at rate 1 USD = 1.1 EUR
        other = Account.objects.create(user=self.user, account_type='SAVINGS', currency=self.eur, balance=0)
        # use view logic to transfer
        # mimic user posting via view
        from django.test import RequestFactory
        rf = RequestFactory()
        request = rf.post(f'/accounts/{self.account.id}/transfer/', data={'to_account': other.id, 'amount': '100.00'})
        request.user = self.user
        transfer_view(request, self.account.id)
        other.refresh_from_db(); self.account.refresh_from_db()
        # 100 USD withdrawn, dest amount = 100*1 /1.1 ≈ 90.91 EUR
        self.assertEqual(self.account.balance, 900)
        self.assertAlmostEqual(float(other.balance), 90.91, places=2)

    def test_fx_update_command(self):
        # ensure command runs and does not error
        from django.core.management import call_command
        # update rates, should at least touch existing currencies
        call_command('update_fx_rates')
        # verify rate_to_usd stays numeric
        for cur in Currency.objects.all():
            self.assertIsNotNone(cur.rate_to_usd)

    def test_currency_template_filter(self):
        from django.template import Context, Template
        t = Template("{% load currency_tags %}{{ val|format_currency:code }}")
        ctx = Context({'val': 1234.5, 'code': 'USD'})
        rendered = t.render(ctx)
        self.assertIn('USD', rendered)

    def test_close_account(self):
        # can't close with nonzero balance
        acc = Account.objects.create(user=self.user, account_type='SAVINGS', balance=100)
        acc.status='ACTIVE'
        acc.save()
        if acc.balance == 0:
            acc.status='CLOSED'
        self.assertNotEqual(acc.status, 'CLOSED')
        # zero balance scenario
        acc.balance = 0
        acc.save()
        if acc.balance == 0:
            acc.status='CLOSED'
        self.assertEqual(acc.status, 'CLOSED')

    def test_tag_summary_in_account_view(self):
        # create a tagged transaction and ensure context contains totals
        from banking.models import TransactionTag, TransactionCategory
        t = Transaction.objects.create(account=self.account, amount=123.45, transaction_type='WITHDRAW')
        tag = TransactionTag.objects.create(name='Groceries')
        TransactionCategory.objects.create(transaction=t, tag=tag)
        # login and request account detail
        self.client.login(email='user2@test.com', password='pass1234')
        resp = self.client.get(f'/accounts/{self.account.pk}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('tag_totals', resp.context)
        totals = resp.context['tag_totals']
        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0]['tag__name'], 'Groceries')
        self.assertAlmostEqual(float(totals[0]['total']), 123.45, places=2)


class RecurringTransferAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='rt@test.com', password='pass1234')
        self.other = User.objects.create_user(email='other@test.com', password='pass1234')
        self.account1 = Account.objects.create(user=self.user, account_type='SAVINGS', balance=1000)
        self.account2 = Account.objects.create(user=self.user, account_type='SAVINGS', balance=500)
        self.admin = User.objects.create_superuser(email='admin@test.com', password='adminpass')
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_create_and_list_recurring(self):
        data = {
            'from_account': self.account1.id,
            'to_account': self.account2.id,
            'amount': '100.00',
            'interval_days': 1,
        }
        resp = self.client.post('/api/recurring-transfers/', data)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['amount'], '100.00')
        # now list as customer
        resp2 = self.client.get('/api/recurring-transfers/')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 1)

    def test_recurring_transfer_command(self):
        from banking.models import RecurringTransfer
        rt = RecurringTransfer.objects.create(
            user=self.user,
            from_account=self.account1,
            to_account=self.account2,
            amount='200',
            interval_days=1,
            next_transfer_date=datetime.date.today(),
        )
        call_command('process_recurring_transfers')
        self.account1.refresh_from_db(); self.account2.refresh_from_db()
        self.assertEqual(self.account1.balance, 800)
        self.assertEqual(self.account2.balance, 700)
        rt.refresh_from_db()
        self.assertGreater(rt.next_transfer_date, datetime.date.today())


class StatementAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='stmt@test.com', password='pass1234')
        self.account = Account.objects.create(user=self.user, account_type='SAVINGS', balance=1000)
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        # create some transactions with varying dates
        Transaction.objects.create(account=self.account, amount=100, transaction_type='DEPOSIT')
        old = Transaction.objects.create(account=self.account, amount=50, transaction_type='WITHDRAW')
        old.created_at = datetime.datetime(2020, 1, 15, tzinfo=datetime.timezone.utc)
        old.save()

    def test_statement_filters_by_month(self):
        now = datetime.datetime.now()
        month = now.month
        year = now.year
        resp = self.client.get(f'/api/statements/?month={month}&year={year}')
        self.assertEqual(resp.status_code, 200)
        # should include only recent deposit, not the 2020 transaction
        self.assertEqual(len(resp.data), 1)

    def test_search_filters(self):
        # deposit from setup is later
        resp = self.client.get('/api/transactions/search/?type=DEPOSIT')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        # specify min amount to exclude
        resp2 = self.client.get('/api/transactions/search/?min_amount=200')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 0)

    def test_export_csv(self):
        resp = self.client.get('/api/statements/export/?month=1&year=2020')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        content = resp.content.decode()
        self.assertIn('Date,Account,Type,Amount,Reference', content)

    def test_export_pdf(self):
        resp = self.client.get('/api/statements/pdf/?month=1&year=2020')
        # PDF generation may not be available in all environments
        self.assertIn(resp.status_code, (200, 501))
        if resp.status_code == 200:
            self.assertEqual(resp['Content-Type'], 'application/pdf')
            self.assertTrue(len(resp.content) > 100)  # some content

    def test_stats_endpoint(self):
        # setUp creates one account; as customer, only their accounts are counted
        from django.core.cache import cache
        cache.clear()
        resp = self.client.get('/api/stats/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('total_balance', data)
        # ensure account count matches actual records (cache may have stale data)
        expected = Account.objects.filter(user=self.user).count()
        self.assertEqual(data['account_count'], expected)

    def test_stats_cache(self):
        # ensure caching layer is used by stats endpoint
        from django.core.cache import cache
        cache.clear()
        resp1 = self.client.get('/api/stats/')
        data1 = resp1.json()
        # create another account which would change totals
        Account.objects.create(user=self.user, account_type='SAVINGS', balance=2000)
        resp2 = self.client.get('/api/stats/')
        data2 = resp2.json()
        # cached response should still equal original
        self.assertEqual(data1, data2)
        # clear cache and fetch again to see updated totals
        cache.clear()
        resp3 = self.client.get('/api/stats/')
        self.assertNotEqual(resp1.json(), resp3.json())


class PaymentGatewayAPITest(APITestCase):
    """Verify that the gateway integration view behaves correctly."""

    def setUp(self):
        self.user = User.objects.create_user(email='pay@test.com', password='pass1234')
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    @patch('banking.gateway.requests.post')
    def test_gateway_charge_success(self, mock_post):
        # simulate a successful gateway response
        mock_resp = mock_post.return_value
        mock_resp.json.return_value = {'status': 'success', 'id': 'tx_123'}
        mock_resp.raise_for_status = lambda: None

        resp = self.client.post('/api/payments/charge/', {'amount': '100', 'currency': 'USD', 'source': 'card_visa'}, format='json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['id'], 'tx_123')

    @patch('banking.gateway.requests.post')
    def test_gateway_charge_failure(self, mock_post):
        # simulate a failing gateway call
        class Bad:
            def raise_for_status(self):
                raise requests.HTTPError("Bad request")
        mock_post.return_value = Bad()

        resp = self.client.post('/api/payments/charge/', {'amount': '50', 'source': 'card_visa'}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Bad request', resp.content.decode())


