from rest_framework import serializers
from .models import Loan


class LoanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = ['id', 'user', 'amount', 'interest_rate', 'duration_months', 'status', 'approved_at', 'created_at']
        read_only_fields = ['id', 'user', 'status', 'approved_at', 'created_at']


class LoanApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Loan
        fields = ['id', 'status']
        read_only_fields = ['id']


class LoanPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = getattr(__import__('loans.models', fromlist=['LoanPayment']), 'LoanPayment')
        fields = ['id', 'loan', 'amount', 'created_at', 'reference']
        read_only_fields = ['id', 'created_at']


class LoanDetailSerializer(LoanSerializer):
    payments = LoanPaymentSerializer(many=True, read_only=True)
    remaining_balance = serializers.SerializerMethodField()

    class Meta(LoanSerializer.Meta):
        fields = LoanSerializer.Meta.fields + ['payments', 'remaining_balance']

    def get_remaining_balance(self, obj):
        return obj.remaining_balance()
