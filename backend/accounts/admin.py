from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import User, OneTimeCode

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'role', 'is_active', 'is_staff', 'created_at')
    list_filter = ('role', 'is_active')
    search_fields = ('email',)
    ordering = ('-created_at',)