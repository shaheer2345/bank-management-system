from rest_framework.test import APITestCase
from accounts.models import User
from banking.models import Account, Transaction
from rest_framework_simplejwt.tokens import RefreshToken


class AccountAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='api@test.com', password='pass1234')
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.account = Account.objects.create(user=self.user, account_type='SAVINGS', balance=1000)

    def test_get_accounts(self):
        response = self.client.get('/api/accounts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_recent_transactions(self):
        # create a couple of transactions for the account
        Transaction.objects.create(account=self.account, amount=50, transaction_type='DEPOSIT')
        Transaction.objects.create(account=self.account, amount=20, transaction_type='WITHDRAW')
        response = self.client.get('/api/transactions/recent/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.data) >= 2)

    def test_role_based_account_list(self):
        # create a teller and a customer, each with an account
        teller = User.objects.create_user(email='teller@test.com', password='pass', role='TELLER')
        customer = User.objects.create_user(email='cust@test.com', password='pass', role='CUSTOMER')
        Account.objects.create(user=teller, account_type='CURRENT', balance=50)
        Account.objects.create(user=customer, account_type='SAVINGS', balance=150)
        # authenticate as customer with JWT
        token_cust = str(RefreshToken.for_user(customer).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_cust}')
        resp = self.client.get('/api/accounts/')
        self.assertEqual(resp.status_code, 200)
        # customer should see only their own account
        self.assertEqual(len(resp.data), 1)
        # now authenticate as teller
        token_teller = str(RefreshToken.for_user(teller).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_teller}')
        resp2 = self.client.get('/api/accounts/')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 3)  # original + teller + customer accounts

