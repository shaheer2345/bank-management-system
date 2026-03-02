from django.db import models
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.conf import settings
import uuid

# Create your models here.

User = settings.AUTH_USER_MODEL

class Currency(models.Model):
    """Simple currency definition with rate relative to a base (USD)."""

    code = models.CharField(max_length=3, unique=True)
    name = models.CharField(max_length=50)
    rate_to_usd = models.DecimalField(max_digits=12, decimal_places=6,
                                      help_text="Value of one unit in USD")

    def __str__(self):
        return f"{self.code} ({self.name})"


class Account(models.Model):
    ACCOUNT_TYPE_CHOICES = (
        ('SAVINGS', 'Savings'),
        ('CURRENT', 'Current'),
    )

    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('FROZEN', 'Frozen'),
        ('CLOSED', 'Closed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='accounts')
    account_number = models.CharField(max_length=20, unique=True, editable=False)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    currency = models.ForeignKey('Currency', on_delete=models.PROTECT, default=None, null=True)
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # assign random account number if missing
        if not self.account_number:
            self.account_number = uuid.uuid4().hex[:16]
        # default currency to USD if not provided and USD exists
        if not self.currency:
            try:
                self.currency = Currency.objects.get(code='USD')
            except Currency.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        cur = self.currency.code if self.currency else ''
        return f"{self.account_number} ({cur}) - {self.user}"


class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = (
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAW', 'Withdraw'),
        ('TRANSFER', 'Transfer'),
    )

    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    reference_id = models.CharField(max_length=50, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        new_record = self.pk is None
        if not self.reference_id:
            self.reference_id = uuid.uuid4().hex
        super().save(*args, **kwargs)
        # adjust balance only when first created
        if new_record:
            if self.transaction_type == 'DEPOSIT':
                self.account.balance += self.amount
            elif self.transaction_type == 'WITHDRAW':
                self.account.balance -= self.amount
            # transfers handled by view creating two transactions
            self.account.save()
            # low balance notification
            try:
                threshold = float(getattr(settings, 'LOW_BALANCE_THRESHOLD', 0))
            except Exception:
                threshold = 0
            if self.account.balance < threshold:
                # send email warning
                send_mail(
                    'Low balance alert',
                    f'Your account {self.account.account_number} has low balance: {self.account.balance}',
                    settings.DEFAULT_FROM_EMAIL,
                    [self.account.user.email],
                )

    def __str__(self):
        return f"{self.transaction_type} - {self.amount}"

    class Meta:
        indexes = [
            models.Index(fields=['account', 'created_at']),
        ]


class RecurringTransfer(models.Model):
    """Represent a scheduled transfer that happens every interval_days.

    The `execute` helper performs the actual withdrawal/deposit and
    advances `next_transfer_date` by the configured interval.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recurring_transfers')
    from_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='outgoing_recurring')
    to_account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name='incoming_recurring')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interval_days = models.PositiveIntegerField(default=30)
    next_transfer_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # ensure next_transfer_date defaults to today when first created
        if not self.next_transfer_date:
            from django.utils import timezone

            self.next_transfer_date = timezone.now().date()
        super().save(*args, **kwargs)

    def execute(self):
        """Perform the transfer and bump `next_transfer_date`.

        This method is deliberately simple; callers (e.g. management
        command) should catch any exceptions or log failures.
        """
        import datetime

        # only allow owner to initiate the transfer
        if self.from_account.user_id != self.user_id:
            raise ValueError("Source account does not belong to user")

        # skip if insufficient funds
        if self.from_account.balance < self.amount:
            return False

        # create the underlying transactions
        Transaction.objects.create(account=self.from_account, amount=self.amount, transaction_type='WITHDRAW')
        Transaction.objects.create(account=self.to_account, amount=self.amount, transaction_type='DEPOSIT')

        # advance the next date
        self.next_transfer_date += datetime.timedelta(days=self.interval_days)
        self.save()
        return True

    def __str__(self):
        return f"Recurring {self.amount} from {self.from_account} to {self.to_account}"

    class Meta:
        indexes = [
            models.Index(fields=['next_transfer_date']),
        ]

class TransactionTag(models.Model):
    """Categorize transactions for better organization."""
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#667eea', help_text="Hex color code")
    
    def __str__(self):
        return self.name


class WithdrawalLimit(models.Model):
    """Set daily or monthly withdrawal limits per account."""
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='withdrawal_limit')
    daily_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    monthly_limit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    current_daily_withdrawn = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_monthly_withdrawn = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    daily_reset_date = models.DateField(auto_now_add=True)
    monthly_reset_date = models.DateField(auto_now_add=True)
    
    def __str__(self):
        return f"Limits for {self.account.account_number}"


class LoginHistory(models.Model):
    """Track user login activity for security."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history')
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    login_time = models.DateTimeField(auto_now_add=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    success = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-login_time']
    
    def __str__(self):
        return f"{self.user.email} - {self.login_time}"


class TransactionCategory(models.Model):
    """Link transactions to category tags."""
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name='categories')
    tag = models.ForeignKey(TransactionTag, on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f"{self.transaction.reference_id} - {self.tag.name if self.tag else 'Untagged'}"