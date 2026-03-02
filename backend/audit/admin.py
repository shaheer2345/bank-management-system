from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'user', 'action', 'target_object', 'ip_address')
    list_filter = ('action',)
    search_fields = ('user__email', 'action', 'target_object')