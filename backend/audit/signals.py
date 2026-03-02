from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.conf import settings

from .models import AuditLog
from banking.models import Account, Transaction


from .middleware import get_current_ip

def create_audit(user, action, target):
    # user may be None
    AuditLog.objects.create(
        user=user,
        action=action,
        target_object=str(target),
        ip_address=get_current_ip()
    )


@receiver(post_save, sender=Account)
def account_saved(sender, instance, created, **kwargs):
    user = instance.user
    action = 'Created account' if created else 'Updated account'
    create_audit(user, action, f"Account {instance.account_number}")


@receiver(post_delete, sender=Account)
def account_deleted(sender, instance, **kwargs):
    create_audit(instance.user, 'Deleted account', f"Account {instance.account_number}")


@receiver(post_save, sender=Transaction)
def transaction_saved(sender, instance, created, **kwargs):
    user = instance.account.user
    action = f"Created transaction {instance.transaction_type} {instance.amount}" if created else 'Updated transaction'
    create_audit(user, action, f"Transaction {instance.reference_id}")


@receiver(post_delete, sender=Transaction)
def transaction_deleted(sender, instance, **kwargs):
    create_audit(instance.account.user, 'Deleted transaction', f"Transaction {instance.reference_id}")
