from django.utils import timezone

# Create your models here.
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from .managers import UserManager

class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('TELLER', 'Teller'),
        ('CUSTOMER', 'Customer'),
    )

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)

    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    # multi-factor authentication fields
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(max_length=32, blank=True)
    # security fields
    failed_login_attempts = models.IntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.CharField(max_length=45, blank=True)  # IPv6-safe
    last_password_change = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(max_length=64, blank=True, unique=True, null=True)
    password_reset_token_expires = models.DateTimeField(null=True, blank=True)
    security_alerts_enabled = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def is_account_locked(self):
        """Check if account is currently locked."""
        if self.account_locked_until:
            from django.utils import timezone
            return timezone.now() < self.account_locked_until
        return False

    def __str__(self):
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip() or self.email
        return self.email


class OneTimeCode(models.Model):
    """Simple OTP model for multi-factor authentication.

    Codes expire after a short interval and are single-use.
    """

    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='otps')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    used = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['user', 'code'])]

    @classmethod
    def generate(cls, user):
        import random
        code = f"{random.randint(0, 999999):06d}"
        return cls.objects.create(user=user, code=code)

    @classmethod
    def verify(cls, user, code):
        # only accept unused codes created within last 5 minutes
        from django.utils import timezone
        cutoff = timezone.now() - timezone.timedelta(minutes=5)
        otp = cls.objects.filter(user=user, code=code, used=False, created_at__gte=cutoff).first()
        if otp:
            otp.used = True
            otp.save()
            return True
        return False

class FailedLoginAttempt(models.Model):
    """Track failed login attempts for rate limiting and lockout."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='failed_attempts')
    ip_address = models.CharField(max_length=45)
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'timestamp'])]

    @classmethod
    def create_attempt(cls, user, ip, ua=''):
        """Create failed attempt and lock account if threshold exceeded."""
        cls.objects.create(user=user, ip_address=ip, user_agent=ua)
        user.failed_login_attempts += 1
        # lock after 5 failed attempts for 30 minutes
        if user.failed_login_attempts >= 5:
            from django.utils import timezone
            from datetime import timedelta
            user.account_locked_until = timezone.now() + timedelta(minutes=30)
        user.save()


class SuspiciousActivity(models.Model):
    """Log suspicious activities for review."""
    ACTIVITY_TYPES = (
        ('NEW_LOGIN_IP', 'Login from new IP'),
        ('UNUSUAL_TIME', 'Login at unusual time'),
        ('BULK_TRANSFER', 'Large transfer'),
        ('FAILED_ATTEMPT', 'Failed login'),
        ('PASSWORD_CHANGE', 'Password changed'),
        ('NEW_DEVICE', 'Login from new device'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='suspicious_activities')
    activity_type = models.CharField(max_length=20, choices=ACTIVITY_TYPES)
    description = models.TextField()
    ip_address = models.CharField(max_length=45)
    timestamp = models.DateTimeField(auto_now_add=True)
    severity = models.CharField(max_length=10, choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')], default='MEDIUM')
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp']


class KnownDevice(models.Model):
    """Whitelist devices to reduce MFA prompts on known devices."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='known_devices')
    device_fingerprint = models.CharField(max_length=256)
    device_name = models.CharField(max_length=100)
    ip_address = models.CharField(max_length=45)
    last_used = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'device_fingerprint')

    def mark_used(self):
        """Update last used timestamp."""
        self.last_used = timezone.now()
        self.save()


class SecurityLog(models.Model):
    """Detailed log of all security-relevant actions."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='security_logs')
    action = models.CharField(max_length=100)
    details = models.TextField()
    ip_address = models.CharField(max_length=45)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['user', 'timestamp'])]