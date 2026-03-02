from django.test import TestCase
from accounts.models import User
from banking.models import Account, Transaction
from .models import AuditLog


class AuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='audittest@test.com', password='secret')

    def test_account_creation_generates_log(self):
        acc = Account.objects.create(user=self.user, account_type='SAVINGS', balance=0)
        # signal should have created an audit entry
        entry = AuditLog.objects.filter(user=self.user, action__icontains='Created account').first()
        self.assertIsNotNone(entry)
        self.assertIn(str(acc.account_number), entry.target_object)
        # IP address may be set to loopback or other value depending on environment
        self.assertIsNotNone(entry.ip_address)

    def test_transaction_creation_generates_log(self):
        acc = Account.objects.create(user=self.user, account_type='SAVINGS', balance=0)
        txn = Transaction.objects.create(account=acc, amount=100, transaction_type='DEPOSIT')
        entry = AuditLog.objects.filter(user=self.user, action__icontains='Created transaction').first()
        self.assertIsNotNone(entry)
        self.assertIn(str(txn.reference_id), entry.target_object)

