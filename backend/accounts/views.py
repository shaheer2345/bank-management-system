from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

# Create your views here.
from .forms import UserRegistrationForm, OTPForm, TOTPForm
from .models import OneTimeCode
import pyotp

@login_required
def profile_view(request):
    """Render a simple profile page for the currently logged-in user."""
    # you can extend this context with additional fields as needed
    return render(request, "accounts/profile.html", {"user": request.user})


@login_required
def edit_profile_view(request):
    """Allow the logged-in user to update their profile details."""
    from .forms import UserProfileForm

    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    return render(request, 'accounts/profile_edit.html', {'form': form})


def register_view(request):
    """Display and process a user sign-up form. New users default to CUSTOMER role."""
    if request.method == "POST":
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('login')
    else:
        form = UserRegistrationForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def enable_totp_view(request):
    user = request.user
    # ensure secret exists
    if not user.mfa_secret:
        user.mfa_secret = pyotp.random_base32()
        user.save()

    if request.method == 'POST':
        form = TOTPForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            totp = pyotp.TOTP(user.mfa_secret)
            if totp.verify(code):
                user.mfa_enabled = True
                user.save()
                return redirect('profile')
            else:
                return render(request, 'accounts/enable_totp.html', {'form': form, 'secret': user.mfa_secret, 'error': 'Invalid code'})
    else:
        form = TOTPForm()
    return render(request, 'accounts/enable_totp.html', {'form': form, 'secret': user.mfa_secret})


@login_required
def login_history_view(request):
    """Display user's login history and security activities."""
    from banking.models import LoginHistory
    
    logins = LoginHistory.objects.filter(user=request.user).order_by('-login_time')[:50]
    return render(request, 'accounts/login_history.html', {'logins': logins})

@login_required
def security_center_view(request):
    """Show user's overall security dashboard."""
    from .models import SuspiciousActivity, SecurityLog, KnownDevice
    from django.utils import timezone
    from datetime import timedelta
    
    # Get recent suspicious activity
    suspicious = SuspiciousActivity.objects.filter(user=request.user).order_by('-timestamp')[:10]
    
    # Get known devices
    known_devices = KnownDevice.objects.filter(user=request.user, is_active=True).order_by('-last_used')
    
    # Get recent security events
    week_ago = timezone.now() - timedelta(days=7)
    recent_events = SecurityLog.objects.filter(user=request.user, timestamp__gte=week_ago).order_by('-timestamp')[:20]
    
    # Security status
    mfa_enabled = request.user.mfa_enabled
    account_locked = request.user.is_account_locked()
    failed_attempts = request.user.failed_login_attempts
    
    return render(request, 'accounts/security_center.html', {
        'suspicious_activities': suspicious,
        'known_devices': known_devices,
        'recent_events': recent_events,
        'mfa_enabled': mfa_enabled,
        'account_locked': account_locked,
        'failed_attempts': failed_attempts,
    })

@login_required
def change_password_view(request):
    """Allow user to change their password with strong password requirements."""
    from .forms import PasswordChangeForm
    from .models import SecurityLog
    
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            request.user.set_password(form.cleaned_data['new_password1'])
            request.user.last_password_change = timezone.now()
            request.user.save()
            
            # Log security event
            from django.utils import timezone as tz
            SecurityLog.objects.create(
                user=request.user,
                action='PASSWORD_CHANGE',
                details='Password successfully changed',
                ip_address=get_client_ip(request) if 'get_client_ip' in dir() else request.META.get('REMOTE_ADDR', '')
            )
            
            from django.contrib import messages
            messages.success(request, 'Password changed successfully. Please login again.')
            from django.contrib.auth import logout
            logout(request)
            return redirect('login')
    else:
        form = PasswordChangeForm(request.user)
    
    return render(request, 'accounts/change_password.html', {'form': form})

@login_required
def suspicious_activity_view(request):
    """Display all suspicious activities detected on user's account."""
    from .models import SuspiciousActivity
    
    # Paginate suspicious activities
    from django.core.paginator import Paginator
    activities_qs = SuspiciousActivity.objects.filter(user=request.user).order_by('-timestamp')
    page_number = request.GET.get('page', 1)
    paginator = Paginator(activities_qs, 20)
    activities = paginator.get_page(page_number)
    
    return render(request, 'accounts/suspicious_activity.html', {'activities': activities})

def get_client_ip(request):
    """Get client IP from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
