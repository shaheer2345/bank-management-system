from rest_framework import permissions


class IsOwnerOrStaff(permissions.BasePermission):
    """Allow access if user owns the object (has `user` attribute) or is staff/admin."""

    def has_permission(self, request, view):
        # authenticated users may list/create; object-level checks enforced below
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # superusers/staff always allowed
        if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False) or getattr(request.user, 'role', '') == 'ADMIN':
            return True
        # otherwise require a user foreign key matching
        return getattr(obj, 'user_id', None) == getattr(request.user, 'id', None)
