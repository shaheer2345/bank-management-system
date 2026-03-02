from django import forms
from .models import User
import re
from django.core.exceptions import ValidationError

def validate_password_strength(password):
    """Validate password meets security requirements."""
    errors = []
    if len(password) < 12:
        errors.append('Password must be at least 12 characters long.')
    if not re.search(r'[A-Z]', password):
        errors.append('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        errors.append('Password must contain at least one lowercase letter.')
    if not re.search(r'[0-9]', password):
        errors.append('Password must contain at least one number.')
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append('Password must contain at least one special character (!@#$%^&*(),.?":{}|<>).')
    if errors:
        raise ValidationError(' '.join(errors))


class TOTPForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'autocomplete': 'off'}))


class OTPForm(forms.Form):
    code = forms.CharField(max_length=6, widget=forms.TextInput(attrs={'autocomplete': 'off'}))


class UserRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(widget=forms.PasswordInput, help_text='At least 12 chars, uppercase, lowercase, number, special char')
    password2 = forms.CharField(widget=forms.PasswordInput, help_text='Confirm password')

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "address", "date_of_birth")
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1:
            # Validate password strength
            validate_password_strength(password1)
        
        if password1 and password2:
            if password1 != password2:
                raise ValidationError('Passwords do not match.')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.role = 'CUSTOMER'
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "address", "date_of_birth")



class PasswordChangeForm(forms.Form):
    """Secure password change form with strength requirements."""
    old_password = forms.CharField(widget=forms.PasswordInput, label='Current Password')
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New Password', help_text='At least 12 chars, uppercase, lowercase, number, special char')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm New Password')
    
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
    
    def clean(self):
        cleaned_data = super().clean()
        old_password = cleaned_data.get('old_password')
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')
        
        # Verify old password
        if old_password and not self.user.check_password(old_password):
            raise ValidationError('Current password is incorrect.')
        
        if new_password1:
            # Validate new password strength
            validate_password_strength(new_password1)
        
        if new_password1 and new_password2:
            if new_password1 != new_password2:
                raise ValidationError('New passwords do not match.')
            if new_password1 == old_password:
                raise ValidationError('New password must be different from current password.')
        
        return cleaned_data
