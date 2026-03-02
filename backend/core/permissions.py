import functools
from django.http import HttpResponseForbidden
from rest_framework import permissions


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'ADMIN'


class IsTeller(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'TELLER'


class IsCustomer(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role == 'CUSTOMER'


class IsTellerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.role in ('TELLER', 'ADMIN')


def role_required(*allowed_roles):
    """Django view decorator that restricts access based on user.role."""
    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden()
        return _wrapped
    return decorator