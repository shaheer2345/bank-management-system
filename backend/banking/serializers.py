from rest_framework import serializers
from .models import Account, Transaction, RecurringTransfer


class AccountSerializer(serializers.ModelSerializer):
    currency = serializers.CharField(source='currency.code', read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "account_number",
            "account_type",
            "currency",
            "balance",
            "status",
            "created_at",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = ['account', 'amount', 'transaction_type']

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value


class RecurringTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringTransfer
        fields = ['id', 'from_account', 'to_account', 'amount', 'interval_days', 'next_transfer_date']
        read_only_fields = ['id', 'next_transfer_date']

    def validate(self, data):
        # ensure accounts differ and belong to user if provided
        if data.get('from_account') == data.get('to_account'):
            raise serializers.ValidationError("Source and destination accounts must be different")
        return data
