from rest_framework import permissions


class IsLoanOwnerOrStaff(permissions.BasePermission):
    """Allow access if user is staff/admin or the owner of the loan."""

    def has_permission(self, request, view):
        # list and create allowed for authenticated users
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # staff/admin can do anything
        if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', '') == 'ADMIN':
            return True
        # otherwise only owner
        return obj.user_id == getattr(request.user, 'id', None)
