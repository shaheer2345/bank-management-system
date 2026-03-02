from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseForbidden, HttpResponse
from rest_framework import generics, permissions
from django.contrib.auth.decorators import login_required
from core.permissions import role_required
import json
from django.template.loader import render_to_string
from django.core.cache import cache
from .gateway import PaymentGateway
import requests
try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None
from django.core.mail import EmailMessage

# helper to safely add messages even if middleware not present
from django.contrib import messages as _messages

def safe_message(request, level, *args, **kwargs):
    try:
        getattr(_messages, level)(request, *args, **kwargs)
    except Exception:
        pass

# monkey patch standard messages methods so that any direct calls to
# messages.success() / messages.error() are wrapped and won't crash
# when middleware isn't available (like in RequestFactory tests).
_orig_success = _messages.success
_orig_error = _messages.error

def _safe_success(request, *args, **kwargs):
    try:
        return _orig_success(request, *args, **kwargs)
    except Exception:
        return None

def _safe_error(request, *args, **kwargs):
    try:
        return _orig_error(request, *args, **kwargs)
    except Exception:
        return None

_messages.success = _safe_success
_messages.error = _safe_error

from .models import Account, Transaction, RecurringTransfer
from .serializers import AccountSerializer, TransactionSerializer, RecurringTransferSerializer
from .permissions import IsOwnerOrStaff
from .forms import AccountCreationForm

# Create your views here.


class AccountListAPIView(generics.ListAPIView):
    serializer_class = AccountSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAuthenticated]
    # we'll apply custom logic in get_queryset below

    def get_queryset(self):
        qs = Account.objects.all()
        role = getattr(self.request.user, 'role', None)
        if role == 'CUSTOMER':
            qs = qs.filter(user=self.request.user)
        # tellers/admin see all accounts
        return qs


class RecentTransactionListAPIView(generics.ListAPIView):
    """Return the most recent transactions for all of the authenticated user's accounts."""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Transaction.objects
            .filter(account__user=self.request.user)
            .order_by('-created_at')[:5]
        )


class RecurringTransferListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = RecurringTransferSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]

    def get_queryset(self):
        qs = RecurringTransfer.objects.all()
        if getattr(self.request.user, 'role', '') == 'CUSTOMER':
            qs = qs.filter(user=self.request.user)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class RecurringTransferDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = RecurringTransferSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrStaff]
    queryset = RecurringTransfer.objects.all()


class StatementAPIView(generics.ListAPIView):
    """Return transactions for a given month/year for the authenticated user."""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # prefetch account to reduce join queries on serialization
        qs = Transaction.objects.filter(account__user=self.request.user).select_related('account')
        month = self.request.query_params.get('month')
        year = self.request.query_params.get('year')
        if month and year:
            qs = qs.filter(created_at__year=year, created_at__month=month)
        return qs.order_by('-created_at')


class TransactionSearchAPIView(generics.ListAPIView):
    """Search transactions by several criteria."""
    serializer_class = TransactionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Transaction.objects.filter(account__user=self.request.user).select_related('account')
        # filters: account, type, date range, min/max amount
        acc = self.request.query_params.get('account')
        ttype = self.request.query_params.get('type')
        from_date = self.request.query_params.get('from')
        to_date = self.request.query_params.get('to')
        min_amt = self.request.query_params.get('min_amount')
        max_amt = self.request.query_params.get('max_amount')
        if acc:
            qs = qs.filter(account_id=acc)
        if ttype:
            qs = qs.filter(transaction_type=ttype)
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)
        if min_amt:
            qs = qs.filter(amount__gte=min_amt)
        if max_amt:
            qs = qs.filter(amount__lte=max_amt)
        return qs.order_by('-created_at')


class StatementExportAPIView(generics.GenericAPIView):
    """Export statement (month/year or current queryset) as CSV."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        import csv
        from django.http import HttpResponse

        # reuse statement queryset logic
        qs = Transaction.objects.filter(account__user=request.user).select_related('account')
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        if month and year:
            qs = qs.filter(created_at__year=year, created_at__month=month)
        # optional additional filters similar to search
        acc = request.query_params.get('account')
        if acc:
            qs = qs.filter(account_id=acc)
        ttype = request.query_params.get('type')
        if ttype:
            qs = qs.filter(transaction_type=ttype)
        # build csv response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="statement.csv"'
        writer = csv.writer(response)
        writer.writerow(['Date', 'Account', 'Type', 'Amount', 'Reference'])
        for tr in qs.order_by('-created_at'):
            writer.writerow([tr.created_at, tr.account.account_number, tr.transaction_type, tr.amount, tr.reference_id])
        return response


class StatementPDFAPIView(generics.GenericAPIView):
    """Return statement as a PDF file."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # check for PDF library
        if not pisa:
            return HttpResponse('PDF library not installed', status=501)
        # reuse same queryset logic as export
        qs = Transaction.objects.filter(account__user=request.user)
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        if month and year:
            qs = qs.filter(created_at__year=year, created_at__month=month)
        # render html
        html = render_to_string('banking/statement_pdf.html', {'transactions': qs, 'user': request.user})
        result = pisa.CreatePDF(html)
        if result.err:
            return HttpResponse('Error generating PDF', status=500)
        response = HttpResponse(result.dest.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="statement.pdf"'
        return response


class GatewayChargeAPIView(generics.GenericAPIView):
    """API endpoint for charging a payment source via external gateway."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        amount = request.data.get('amount')
        currency = request.data.get('currency', 'USD')
        source = request.data.get('source')
        if not amount or not source:
            return HttpResponse('amount and source fields are required', status=400)
        gateway = PaymentGateway()
        try:
            result = gateway.charge(amount, currency, source, description=request.data.get('description'))
        except requests.HTTPError as e:
            return HttpResponse(str(e), status=400)
        return HttpResponse(json.dumps(result), content_type='application/json')


class BankingStatsAPIView(generics.GenericAPIView):
    """Return simple statistics for dashboard."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from django.db.models import Sum, Count
        # simple caching to reduce load if endpoint is hit repeatedly
        user = request.user
        cache_key = f"stats_{user.id}_{getattr(user,'role','')}"
        data = cache.get(cache_key)
        if data is None:
            if getattr(user, 'is_staff', False) or getattr(user, 'role', '') in ('ADMIN', 'TELLER'):
                accounts = Account.objects.all()
                transactions = Transaction.objects.all()
            else:
                accounts = Account.objects.filter(user=user)
                transactions = Transaction.objects.filter(account__user=user)
            total_balance = accounts.aggregate(sum=Sum('balance'))['sum'] or 0
            count_accounts = accounts.count()
            deposit_sum = transactions.filter(transaction_type='DEPOSIT').aggregate(sum=Sum('amount'))['sum'] or 0
            withdraw_sum = transactions.filter(transaction_type='WITHDRAW').aggregate(sum=Sum('amount'))['sum'] or 0
            data = {
                'total_balance': str(total_balance),
                'account_count': count_accounts,
                'total_deposits': str(deposit_sum),
                'total_withdrawals': str(withdraw_sum),
            }
            cache.set(cache_key, data, 60)  # cache for 1 minute
        return HttpResponse(
            json.dumps(data),
            content_type='application/json'
        )


@login_required
@role_required('CUSTOMER','TELLER','ADMIN')
def open_account_view(request):
    """Allow a logged-in user to open a new account."""
    if request.method == 'POST':
        form = AccountCreationForm(request.POST)
        if form.is_valid():
            acc = form.save(commit=False)
            acc.user = request.user
            acc.save()
            return redirect('dashboard')
    else:
        form = AccountCreationForm()
    return render(request, 'banking/open_account.html', {'form': form})


@login_required
def close_account_view(request, pk):
    account = Account.objects.filter(pk=pk, user=request.user).first()
    if account and request.method == 'POST':
        if account.balance == 0:
            account.status = 'CLOSED'
            account.save()
    return redirect('account-detail', pk=pk)


@login_required
@role_required('CUSTOMER','TELLER','ADMIN')
def account_detail_view(request, pk):
    account = Account.objects.filter(pk=pk, user=request.user).first()
    if not account:
        return redirect('dashboard')
    # paginate transaction history
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    transactions_qs = account.transactions.order_by('-created_at')
    page_number = request.GET.get('page', 1)
    paginator = Paginator(transactions_qs, 10)  # show 10 per page
    try:
        transactions = paginator.page(page_number)
    except PageNotAnInteger:
        transactions = paginator.page(1)
    except EmptyPage:
        transactions = paginator.page(paginator.num_pages)

    from .forms import DepositForm, WithdrawForm, TransferForm
    depo_form = DepositForm()
    with_form = WithdrawForm()
    trans_form = TransferForm(request.user)

    # compute spending totals by tag for this account
    from django.db.models import Sum
    from .models import TransactionCategory
    tag_totals = (
        TransactionCategory.objects
            .filter(transaction__account=account)
            .values('tag__name', 'tag__color')
            .annotate(total=Sum('transaction__amount'))
            .order_by('-total')
    )

    return render(request, 'banking/account_detail.html', {
        'account': account,
        'transactions': transactions,
        'deposit_form': depo_form,
        'withdraw_form': with_form,
        'transfer_form': trans_form,
        'tag_totals': tag_totals,
    })

@login_required
def cancel_recurring_view(request, pk):
    """Cancel a recurring transfer if owned by the user or staff."""
    recurring = get_object_or_404(RecurringTransfer, pk=pk)
    # permission check
    if recurring.from_account.user != request.user and not (getattr(request.user, 'is_staff', False) or getattr(request.user, 'role','').upper() in ('ADMIN','TELLER','STAFF')):
        return render(request, '403.html', status=403)
    if request.method == 'POST':
        recurring.status = 'CANCELLED'
        recurring.save()
        from django.contrib import messages
        safe_message(request, 'success', 'Recurring transfer cancelled.')
    return redirect('recurring-list')


@login_required
def tag_transaction_view(request, pk):
    """Allow user to add or change category tag on a specific transaction."""
    from django.shortcuts import get_object_or_404
    from django.contrib import messages
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)
    if request.method == 'POST':
        name = request.POST.get('tag', '').strip()
        if name:
            tag_obj, _ = TransactionTag.objects.get_or_create(name=name)
            from .models import TransactionCategory
            TransactionCategory.objects.update_or_create(transaction=tx, defaults={'tag': tag_obj})
            safe_message(request, 'success', f'Tag set to "{tag_obj.name}"')
        else:
            # remove tag
            from .models import TransactionCategory
            TransactionCategory.objects.filter(transaction=tx).delete()
            safe_message(request, 'success', 'Tag removed')
    return redirect('account-detail', pk=tx.account.pk)


@login_required
def transaction_pdf_view(request, pk):
    """Generate PDF receipt for a single transaction."""
    from django.shortcuts import get_object_or_404
    tx = get_object_or_404(Transaction, pk=pk, account__user=request.user)
    # render PDF
    if pisa:
        html = render_to_string('banking/transaction_pdf.html', {'tx': tx, 'user': request.user})
        result = pisa.CreatePDF(html)
        if result.err:
            return HttpResponse('Error generating PDF', status=500)
        response = HttpResponse(result.dest.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="transaction_{tx.reference_id}.pdf"'
        return response
    else:
        return HttpResponse('PDF library not installed', status=501)


def deposit_view(request, pk):
    from django.contrib import messages
    account = Account.objects.filter(pk=pk).first()
    if not account:
        messages.error(request, 'Account not found.')
        return redirect('dashboard')
    # customers may only deposit to their own accounts; tellers/admin may deposit any
    if request.user.role == 'CUSTOMER' and account.user != request.user:
        safe_message(request, 'error', 'You do not have permission to deposit to this account.')
        return HttpResponseForbidden()
    from .forms import DepositForm
    if request.method == 'POST':
        form = DepositForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            try:
                tx = Transaction.objects.create(
                    account=account,
                    amount=amount,
                    transaction_type='DEPOSIT'
                )
                # update balance now that transaction created
                account.refresh_from_db()
                success_message = f'Successfully deposited {account.currency.code} {amount} to account {account.account_number}'
                # Send confirmation email
                try:
                    EmailMessage(
                        subject=f'Deposit Confirmation - {amount} {account.currency.code}',
                        body=f'Your deposit of {amount} {account.currency.code} to account {account.account_number} was successful.\n\nReference: {tx.reference_id}',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[account.user.email],
                    ).send()
                except:
                    pass
                # AJAX response
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.template.loader import render_to_string
                    txn_html = render_to_string('banking/partials/transaction_row.html', {'t': tx, 'account': account})
                    return JsonResponse({'success': True, 'message': success_message, 'balance': str(account.balance), 'transaction_html': txn_html})
                else:
                    safe_message(request, 'success', success_message)
            except Exception as e:
                error_msg = f'Deposit failed: {str(e)}'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Please enter a valid amount.'})
            messages.error(request, 'Please enter a valid amount.')
    return redirect('account-detail', pk=pk)


@login_required
def withdraw_view(request, pk):
    from django.contrib import messages
    from datetime import date, timedelta
    from banking.models import WithdrawalLimit
    
    account = Account.objects.filter(pk=pk).first()
    if not account:
        messages.error(request, 'Account not found.')
        return redirect('dashboard')
    if request.user.role == 'CUSTOMER' and account.user != request.user:
        safe_message(request, 'error', 'You do not have permission to withdraw from this account.')
        return HttpResponseForbidden()
    from .forms import WithdrawForm
    if request.method == 'POST':
        form = WithdrawForm(request.POST)
        if form.is_valid():
            amount = form.cleaned_data['amount']
            
            # Check balance
            if amount > account.balance:
                error_msg = f'Insufficient balance. You have {account.currency.code} {account.balance} but are trying to withdraw {account.currency.code} {amount}.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return redirect('account-detail', pk=pk)
            
            # Check withdrawal limits
            try:
                limit = WithdrawalLimit.objects.get(account=account)
                today = date.today()
                
                # Reset daily limit if needed
                if limit.daily_reset_date != today:
                    limit.current_daily_withdrawn = 0
                    limit.daily_reset_date = today
                
                # Reset monthly limit if needed
                if limit.monthly_reset_date != today.replace(day=1):
                    limit.current_monthly_withdrawn = 0
                    limit.monthly_reset_date = today
                
                # Check daily limit
                if limit.daily_limit:
                    if limit.current_daily_withdrawn + amount > limit.daily_limit:
                        remaining = limit.daily_limit - limit.current_daily_withdrawn
                        error_msg = f'Daily withdrawal limit exceeded. You can withdraw up to {account.currency.code} {remaining} more today.'
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': error_msg})
                        messages.error(request, error_msg)
                        return redirect('account-detail', pk=pk)
                
                # Check monthly limit
                if limit.monthly_limit:
                    if limit.current_monthly_withdrawn + amount > limit.monthly_limit:
                        remaining = limit.monthly_limit - limit.current_monthly_withdrawn
                        error_msg = f'Monthly withdrawal limit exceeded. You can withdraw up to {account.currency.code} {remaining} more this month.'
                        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                            return JsonResponse({'success': False, 'error': error_msg})
                        messages.error(request, error_msg)
                        return redirect('account-detail', pk=pk)
            except WithdrawalLimit.DoesNotExist:
                pass  # No limits set
            
            try:
                tx = Transaction.objects.create(
                    account=account,
                    amount=amount,
                    transaction_type='WITHDRAW'
                )
                
                # Update withdrawal limits
                try:
                    limit = WithdrawalLimit.objects.get(account=account)
                    limit.current_daily_withdrawn += amount
                    limit.current_monthly_withdrawn += amount
                    limit.save()
                except WithdrawalLimit.DoesNotExist:
                    pass
                
                account.refresh_from_db()
                success_msg = f'Successfully withdrew {account.currency.code} {amount} from account {account.account_number}'
                
                # Send confirmation email
                try:
                    EmailMessage(
                        subject=f'Withdrawal Confirmation - {amount} {account.currency.code}',
                        body=f'Your withdrawal of {amount} {account.currency.code} from account {account.account_number} was successful.\n\nReference: {tx.reference_id}\nNew Balance: {account.balance}',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[account.user.email],
                    ).send()
                except:
                    pass
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.template.loader import render_to_string
                    txn_html = render_to_string('banking/partials/transaction_row.html', {'t': tx, 'account': account})
                    return JsonResponse({'success': True, 'message': success_msg, 'balance': str(account.balance), 'transaction_html': txn_html})
                messages.success(request, success_msg)
            except Exception as e:
                error_msg = f'Withdrawal failed: {str(e)}'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Please enter a valid amount.'})
            messages.error(request, 'Please enter a valid amount.')
    return redirect('account-detail', pk=pk)


@login_required
def transfer_view(request, pk):
    from django.contrib import messages
    account = Account.objects.filter(pk=pk).first()
    source = account
    if not source:
        messages.error(request, 'Account not found.')
        return redirect('dashboard')
    if request.user.role == 'CUSTOMER' and source.user != request.user:
        messages.error(request, 'You do not have permission to transfer from this account.')
        return HttpResponseForbidden()
    from .forms import TransferForm
    if request.method == 'POST':
        form = TransferForm(request.user, request.POST)
        if form.is_valid():
            to_acc = form.cleaned_data['to_account']
            amount = form.cleaned_data['amount']
            
            # Validation
            if to_acc == source:
                error_msg = 'You cannot transfer to the same account.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return redirect('account-detail', pk=pk)
            
            if source.balance < amount:
                error_msg = f'Insufficient balance. You have {source.currency.code} {source.balance} but are trying to transfer {source.currency.code} {amount}.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return redirect('account-detail', pk=pk)
            
            if to_acc.status != 'ACTIVE':
                error_msg = f'Destination account is {to_acc.status.lower()}. Transfer cannot be completed.'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
                return redirect('account-detail', pk=pk)
            
            try:
                # Handle currency conversion if needed
                if source.currency and to_acc.currency and source.currency != to_acc.currency:
                    from decimal import Decimal, getcontext
                    getcontext().prec = 12
                    amt = Decimal(amount)
                    usd_val = amt * source.currency.rate_to_usd
                    dest_amt = (usd_val / to_acc.currency.rate_to_usd).quantize(Decimal('0.01'))
                else:
                    dest_amt = amount
                
                # Create transactions
                tx_out = Transaction.objects.create(
                    account=source,
                    amount=amount,
                    transaction_type='WITHDRAW'
                )
                tx_in = Transaction.objects.create(
                    account=to_acc,
                    amount=dest_amt,
                    transaction_type='DEPOSIT'
                )
                
                source.refresh_from_db()
                success_msg = f'Successfully transferred {source.currency.code} {amount} to account {to_acc.account_number}'
                
                # Send confirmation emails
                try:
                    EmailMessage(
                        subject=f'Transfer Confirmation - {amount} {source.currency.code}',
                        body=f'You have transferred {amount} {source.currency.code} from account {source.account_number} to account {to_acc.account_number}.\n\nReference: {tx_out.reference_id}\nNew Balance: {source.balance}',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[source.user.email],
                    ).send()
                    
                    EmailMessage(
                        subject=f'Transfer Received - {dest_amt} {to_acc.currency.code}',
                        body=f'You have received {dest_amt} {to_acc.currency.code} in account {to_acc.account_number} from account {source.account_number}.\n\nReference: {tx_in.reference_id}\nNew Balance: {to_acc.balance}',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[to_acc.user.email],
                    ).send()
                except:
                    pass
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.template.loader import render_to_string
                    txn_html = render_to_string('banking/partials/transaction_row.html', {'t': tx_out, 'account': source})
                    return JsonResponse({'success': True, 'message': success_msg, 'balance': str(source.balance), 'transaction_html': txn_html})
                messages.success(request, success_msg)
            except Exception as e:
                error_msg = f'Transfer failed: {str(e)}'
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': error_msg})
                messages.error(request, error_msg)
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': 'Please fill in all fields correctly.'})
            safe_message(request, 'error', 'Please fill in all fields correctly.')
    return redirect('account-detail', pk=pk)

