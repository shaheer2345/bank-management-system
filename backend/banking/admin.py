from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Account, Transaction

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('account_number', 'user', 'account_type', 'balance', 'status', 'created_at')
    list_filter = ('account_type', 'status')
    search_fields = ('account_number',)

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('reference_id', 'account', 'transaction_type', 'amount', 'created_at')
    list_filter = ('transaction_type',)