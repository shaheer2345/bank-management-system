from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.core.mail import send_mail
from django.conf import settings
from django_ratelimit.decorators import ratelimit
from django.conf import settings

# configure login ratelimit differently for development vs production
if getattr(settings, 'DEBUG', False):
    LOGIN_RATELIMIT = ratelimit(key='ip', rate='20/m', method=['POST'], block=False)
else:
    LOGIN_RATELIMIT = ratelimit(key='ip', rate='5/m', method=['POST'], block=True)

# Create your views here.

from accounts.forms import OTPForm, TOTPForm
from accounts.models import OneTimeCode
from accounts.models import User
from banking.models import LoginHistory
import pyotp
from django.shortcuts import get_object_or_404
from loans.models import Loan, LoanPayment
from banking.models import RecurringTransfer, Account, Transaction
from audit.models import AuditLog
from django.contrib import messages


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@LOGIN_RATELIMIT
def login_view(request):
    # clear any half-completed MFA flow when requested
    if request.GET.get('reset') == '1':
        request.session.pop('mfa_user_id', None)

    # two-phase login: credentials then OTP
    # second phase: either email OTP or TOTP depending on configuration
    if 'mfa_user_id' in request.session:
        # choose appropriate form
        try:
            user = User.objects.get(id=request.session['mfa_user_id'])
        except User.DoesNotExist:
            user = None
        if user and user.mfa_enabled:
            form = TOTPForm(request.POST or None)
        else:
            form = OTPForm(request.POST or None)

        if request.method == 'POST' and form.is_valid():
            code = form.cleaned_data['code']
            if user:
                if user.mfa_enabled:
                    totp = pyotp.TOTP(user.mfa_secret)
                    valid = totp.verify(code)
                else:
                    valid = OneTimeCode.verify(user, code)
                if valid:
                    login(request, user)
                    del request.session['mfa_user_id']
                    
                    # Reset failed attempts on successful login
                    user.failed_login_attempts = 0
                    user.account_locked_until = None
                    user.last_login_ip = get_client_ip(request)
                    user.save()
                    
                    # Log successful login
                    try:
                        LoginHistory.objects.create(
                            user=user,
                            ip_address=get_client_ip(request),
                            user_agent=request.META.get('HTTP_USER_AGENT', ''),
                            success=True
                        )
                        # Log security event
                        from accounts.models import SecurityLog
                        SecurityLog.objects.create(
                            user=user,
                            action='LOGIN_SUCCESS',
                            details=f'Successful login from {get_client_ip(request)}',
                            ip_address=get_client_ip(request)
                        )
                    except:
                        pass
                    
                    # redirect based on user role
                    if getattr(user, 'role', '').upper() in ('ADMIN', 'TELLER', 'STAFF'):
                        return redirect('admin-dashboard')
                    else:
                        return redirect('dashboard')
            # failed MFA
            from accounts.models import SuspiciousActivity
            try:
                SuspiciousActivity.objects.create(
                    user=user,
                    activity_type='FAILED_ATTEMPT',
                    description='Invalid MFA code',
                    ip_address=get_client_ip(request),
                    severity='MEDIUM'
                )
            except:
                pass
            return render(request, 'accounts/otp.html', {'form': form, 'error': 'Invalid or expired code', 'totp': user and user.mfa_enabled})
        return render(request, 'accounts/otp.html', {'form': form, 'totp': user and user.mfa_enabled})

    if request.method == 'POST':
        email = request.POST.get('username')
        password = request.POST.get('password')
        client_ip = get_client_ip(request)
        
        try:
            user = User.objects.get(email=email)
            # Check if account is locked
            if user.is_account_locked():
                messages.error(request, 'Account is locked due to too many failed login attempts. Please try again in 30 minutes or contact support.')
                return render(request, "login.html", {"error": "Account locked"})
        except User.DoesNotExist:
            user = None
        
        authenticated_user = authenticate(request, email=email, password=password)
        if authenticated_user:
            request.session['mfa_user_id'] = authenticated_user.id
            
            # Detect new IP address
            if authenticated_user.last_login_ip and authenticated_user.last_login_ip != client_ip:
                from accounts.models import SuspiciousActivity
                try:
                    SuspiciousActivity.objects.create(
                        user=authenticated_user,
                        activity_type='NEW_LOGIN_IP',
                        description=f'Login from new IP: {client_ip}. Previous: {authenticated_user.last_login_ip}',
                        ip_address=client_ip,
                        severity='LOW'
                    )
                except:
                    pass
            
            if authenticated_user.mfa_enabled:
                # skip OTP email, the second phase will prompt TOTP entry
                return redirect('login')
            # generate and email OTP
            otp = OneTimeCode.generate(authenticated_user)
            try:
                send_mail(
                    'Your FinanceHub Login Code',
                    f'Your authentication code is {otp.code}\n\nIf you did not request this code, please ignore this email.',
                    settings.DEFAULT_FROM_EMAIL,
                    [authenticated_user.email],
                )
            except:
                pass
            return redirect('login')
        else:
            # Failed login attempt
            if user:
                from accounts.models import FailedLoginAttempt
                FailedLoginAttempt.create_attempt(user, client_ip, request.META.get('HTTP_USER_AGENT', ''))
                
                # Log suspicious activity
                from accounts.models import SuspiciousActivity
                try:
                    SuspiciousActivity.objects.create(
                        user=user,
                        activity_type='FAILED_ATTEMPT',
                        description='Failed login attempt',
                        ip_address=client_ip,
                        severity='MEDIUM'
                    )
                except:
                    pass
            
            # Log generic failed attempt (only if we actually resolved a user)
            if user:
                try:
                    LoginHistory.objects.create(
                        user=user,
                        ip_address=client_ip,
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        success=False
                    )
                except:
                    pass
            messages.error(request, 'Invalid email or password.')

    return render(request, "login.html")


@login_required
def dashboard_view(request):
    """Customer dashboard with their accounts and transactions."""
    user = request.user
    # redirect admin users to admin dashboard
    if getattr(user, 'role', '').upper() in ('ADMIN', 'TELLER', 'STAFF'):
        return redirect('admin-dashboard')
    return render(request, "dashboard.html")


@login_required
def admin_dashboard_view(request):
    """Admin dashboard with system statistics and pending approvals."""
    user = request.user
    # only allow admin/staff to access
    if not (getattr(user, 'role', '').upper() in ('ADMIN', 'TELLER', 'STAFF') or getattr(user, 'is_staff', False)):
        return render(request, '403.html', status=403)
    
    from accounts.models import User
    from audit.models import AuditLog
    from loans.models import Loan
    from banking.models import Account
    from django.db.models import Sum
    
    # gather admin stats
    total_users = User.objects.count()
    total_accounts = Account.objects.count()
    total_balance = Account.objects.aggregate(sum=Sum('balance'))['sum'] or 0
    pending_loans = Loan.objects.filter(status='PENDING').count()
    pending_loans_list = Loan.objects.filter(status='PENDING').select_related('user')[:10]
    recent_logs = AuditLog.objects.order_by('-timestamp')[:20]

    # transaction type counts for chart
    from banking.models import Transaction
    from django.utils import timezone
    from datetime import timedelta
    week_ago = timezone.now() - timedelta(days=7)
    tx_counts_qs = Transaction.objects.filter(created_at__gte=week_ago)
    deposit_count = tx_counts_qs.filter(transaction_type='DEPOSIT').count()
    withdraw_count = tx_counts_qs.filter(transaction_type='WITHDRAW').count()
    transfer_count = tx_counts_qs.filter(transaction_type='TRANSFER').count()
    tx_counts = {'DEPOSIT': deposit_count, 'WITHDRAW': withdraw_count, 'TRANSFER': transfer_count}
    
    return render(request, 'admin_dashboard.html', {
        'total_users': total_users,
        'total_accounts': total_accounts,
        'total_balance': total_balance,
        'pending_loans': pending_loans,
        'pending_loans_list': pending_loans_list,
        'recent_logs': recent_logs,
        'tx_counts': tx_counts,
    })


@login_required
def loan_list_view(request):
    user = request.user
    # allow customers to apply for loan via POST
    if request.method == 'POST':
        amt = request.POST.get('amount')
        rate = request.POST.get('interest_rate')
        dur = request.POST.get('duration_months')
        if amt and rate and dur:
            try:
                Loan.objects.create(user=user, amount=amt, interest_rate=rate, duration_months=dur)
                from django.contrib import messages
                messages.success(request, 'Loan application submitted.')
            except Exception:
                from django.contrib import messages
                messages.error(request, 'Failed to submit loan application.')
        return redirect('loan-list')

    if getattr(user, 'is_staff', False) or getattr(user, 'role', '') in ('ADMIN', 'TELLER'):
        loans = Loan.objects.all()
    else:
        loans = Loan.objects.filter(user=user)
    return render(request, 'loan_list.html', {'loans': loans})


@login_required
def loan_detail_view(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    # permission: owner or staff
    if not (request.user.id == loan.user_id or getattr(request.user, 'is_staff', False) or getattr(request.user, 'role', '') == 'ADMIN'):
        return render(request, '403.html', status=403)

    if request.method == 'POST':
        # make a repayment
        amount = request.POST.get('amount')
        if not amount:
            messages.error(request, 'Amount is required')
        else:
            LoanPayment.objects.create(loan=loan, amount=amount)
            messages.success(request, 'Payment recorded')
            return redirect('loan-detail', pk=loan.id)

    schedule = loan.generate_schedule()
    payments = loan.payments.order_by('-created_at').all()
    return render(request, 'loan_detail.html', {
        'loan': loan,
        'schedule': schedule,
        'remaining': loan.remaining_balance(),
        'payments': payments,
    })


@login_required
def recurring_list_view(request):
    user = request.user
    if getattr(user, 'is_staff', False) or getattr(user, 'role', '') in ('ADMIN', 'TELLER'):
        transfers = RecurringTransfer.objects.all()
        accounts = Account.objects.all()
    else:
        transfers = RecurringTransfer.objects.filter(user=user)
        accounts = Account.objects.filter(user=user)

    if request.method == 'POST':
        from_id = request.POST.get('from_account')
        to_id = request.POST.get('to_account')
        amount = request.POST.get('amount')
        interval = request.POST.get('interval_days')
        if from_id and to_id and amount and interval:
            RecurringTransfer.objects.create(
                user=user,
                from_account=Account.objects.get(id=from_id),
                to_account=Account.objects.get(id=to_id),
                amount=amount,
                interval_days=interval,
            )
            return redirect('recurring-list')
    return render(request, 'recurring_list.html', {
        'transfers': transfers,
        'accounts': accounts,
    })


@login_required
def statement_view(request):
    user = request.user
    month = request.GET.get('month')
    year = request.GET.get('year')
    qs = Transaction.objects.filter(account__user=user)
    if month and year:
        qs = qs.filter(created_at__year=year, created_at__month=month)
    qs = qs.order_by('-created_at')
    return render(request, 'statement.html', {'transactions': qs, 'month': month, 'year': year})

@login_required
def search_view(request):
    return render(request, 'transaction_search.html')

