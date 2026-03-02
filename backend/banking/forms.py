from django import forms
from .models import Account


class AccountCreationForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ['account_type', 'currency']


class DepositForm(forms.Form):
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)


class DepositForm(forms.Form):
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)


class WithdrawForm(forms.Form):
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)


class TransferForm(forms.Form):
    to_account = forms.ModelChoiceField(queryset=Account.objects.none())
    amount = forms.DecimalField(max_digits=15, decimal_places=2, min_value=0.01)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # limit destinations to user's other accounts
        self.fields['to_account'].queryset = Account.objects.filter(user=user)

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # limit destinations to user's other accounts
        self.fields['to_account'].queryset = Account.objects.filter(user=user)
