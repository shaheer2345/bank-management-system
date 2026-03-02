from django.db import models

# Create your models here.
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

class Loan(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('COMPLETED', 'Completed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='loans')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    duration_months = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    approved_at = models.DateTimeField(null=True, blank=True)
    next_due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def total_payable_amount(self):
        from decimal import Decimal
        amt = Decimal(str(self.amount))
        rate = Decimal(str(self.interest_rate))
        months = Decimal(int(self.duration_months))
        interest = (amt * rate * months) / Decimal('100')
        return amt + interest

    def __str__(self):
        return f"Loan {self.id} - {self.user}"

    def remaining_balance(self):
        """Calculate remaining balance after payments."""
        paid = 0
        if hasattr(self, 'payments'):
            paid = sum([p.amount for p in self.payments.all()])
        from decimal import Decimal
        remaining = Decimal(str(self.total_payable_amount())) - Decimal(str(paid))
        return remaining if remaining > 0 else Decimal('0')

    def generate_schedule(self):
        """Return a simple monthly schedule list of dicts (month_number, amount_due)."""
        total = float(self.total_payable_amount())
        months = max(1, int(self.duration_months))
        per_month = round(total / months, 2)
        schedule = []
        for m in range(1, months + 1):
            schedule.append({'month': m, 'amount_due': per_month})
        return schedule


class LoanPayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    reference = models.CharField(max_length=64, blank=True)

    def save(self, *args, **kwargs):
        new = self.pk is None
        super().save(*args, **kwargs)
        if new:
            # advance next_due_date by one month
            from datetime import timedelta
            if self.loan.next_due_date:
                self.loan.next_due_date += timedelta(days=30)
                self.loan.save()

    def __str__(self):
        return f"Payment {self.id} for Loan {self.loan_id}: {self.amount}"