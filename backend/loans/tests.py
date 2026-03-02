from rest_framework.test import APITestCase
from accounts.models import User
from .models import Loan
from rest_framework_simplejwt.tokens import RefreshToken


class LoanAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='loanuser@test.com', password='pass1234', role='CUSTOMER')
        self.admin = User.objects.create_superuser(email='admin@test.com', password='adminpass')
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_apply_and_list_loans_customer(self):
        data = {'amount': '5000.00', 'interest_rate': '5.0', 'duration_months': 12}
        resp = self.client.post('/api/loans/', data)
        self.assertEqual(resp.status_code, 201)
        # customer should see only their loan
        resp2 = self.client.get('/api/loans/')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(len(resp2.data), 1)

    def test_admin_can_see_all_and_approve(self):
        # create a loan for another user
        other = User.objects.create_user(email='other@test.com', password='p', role='CUSTOMER')
        Loan.objects.create(user=other, amount='1000', interest_rate='3.0', duration_months=6)
        # customer token should see only their own (none)
        resp = self.client.get('/api/loans/')
        self.assertEqual(resp.status_code, 200)
        # now authenticate as admin
        token_admin = str(RefreshToken.for_user(self.admin).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_admin}')
        resp2 = self.client.get('/api/loans/')
        self.assertEqual(resp2.status_code, 200)
        self.assertTrue(len(resp2.data) >= 1)
        # pick a loan and approve it
        loan_id = resp2.data[0]['id']
        approve_resp = self.client.patch(f'/api/loans/{loan_id}/approve/', {'status': 'APPROVED'}, format='json')
        self.assertEqual(approve_resp.status_code, 200)
        loan = Loan.objects.get(id=loan_id)
        self.assertEqual(loan.status, 'APPROVED')
        self.assertIsNotNone(loan.approved_at)

    def test_customer_cannot_approve(self):
        # create a loan for the customer
        loan = Loan.objects.create(user=self.user, amount='200', interest_rate='2.0', duration_months=3)
        # customer tries to approve
        resp = self.client.patch(f'/api/loans/{loan.id}/approve/', {'status': 'APPROVED'}, format='json')
        self.assertIn(resp.status_code, (401, 403))

    def test_repayment_reduces_remaining_balance(self):
        loan = Loan.objects.create(user=self.user, amount='1200', interest_rate='6.0', duration_months=12)
        # ensure schedule/remaining calculation works
        total = float(loan.total_payable_amount())
        # make a payment
        resp = self.client.post(f'/api/loans/{loan.id}/repay/', {'amount': '100.00'}, format='json')
        # should be created
        self.assertEqual(resp.status_code, 201)
        loan.refresh_from_db()
        # remaining should be less than total
        rem = loan.remaining_balance()
        self.assertTrue(rem < total)

    def test_low_balance_notification(self):
        from django.core import mail
        from django.test import override_settings
        # set threshold so the withdrawal will trigger an alert
        with override_settings(LOW_BALANCE_THRESHOLD=100):
            # clear any previous messages
            mail.outbox = []
            from banking.models import Account, Transaction
            acct = Account.objects.create(user=self.user, account_type='SAVINGS', balance=200)
            Transaction.objects.create(account=acct, amount=150, transaction_type='WITHDRAW')
            self.assertEqual(len(mail.outbox), 1)
            self.assertIn('Low balance alert', mail.outbox[0].subject)

    def test_loan_reminder_command(self):
        from django.core import mail
        from django.core.management import call_command
        import datetime
        # create loan and manually set next_due_date to today
        loan2 = Loan.objects.create(user=self.user, amount='500', interest_rate='5', duration_months=6, status='APPROVED')
        loan2.next_due_date = datetime.date.today()
        loan2.save()
        call_command('send_loan_reminders')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Loan payment due', mail.outbox[0].subject)

    def test_schedule_generation(self):
        loan = Loan.objects.create(user=self.user, amount='1200', interest_rate='6.0', duration_months=12)
        schedule = loan.generate_schedule()
        self.assertEqual(len(schedule), 12)
        # amounts should sum approximately to total_payable
        ssum = sum([item['amount_due'] for item in schedule])
        self.assertAlmostEqual(ssum, float(loan.total_payable_amount()), places=1)

# Create your tests here.
