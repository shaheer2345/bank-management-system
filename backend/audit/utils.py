from .models import AuditLog

def log_action(user, action, target_object=None, ip_address=None):
    AuditLog.objects.create(
        user=user,
        action=action,
        target_object=str(target_object) if target_object else None,
        ip_address=ip_address
    )