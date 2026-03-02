from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Loan

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'amount', 'interest_rate', 'duration_months', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__email',)