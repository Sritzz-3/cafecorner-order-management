from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    """Base for role checks; group membership is the access-control source."""

    group_name = None

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or user.groups.filter(name=self.group_name).exists()


class IsCustomer(HasRole):
    group_name = "Customer"


class IsStaffRole(HasRole):
    group_name = "Staff"


class IsAdminRole(HasRole):
    group_name = "Admin"
