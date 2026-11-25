"""
Custom DRF permissions for Parking Management Backend per TL-01 and Security Baseline.
Enforces role-based access control based on Account.role:
- IsManager: Account.role == 'MANAGER'
- IsEmployeeOrManager: Account.role in ('EMPLOYEE', 'MANAGER')
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class IsManager(BasePermission):
    """
    Cho phép truy cập chỉ khi người dùng đã xác thực và có Account.role == 'MANAGER'.
    """

    message = "Bạn không có quyền thực hiện thao tác này."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_active", True)
            and getattr(user, "role", None) == "MANAGER"
        )


class IsEmployeeOrManager(BasePermission):
    """
    Cho phép truy cập chỉ khi người dùng đã xác thực và có Account.role in ('EMPLOYEE', 'MANAGER').
    """

    message = "Bạn không có quyền thực hiện thao tác này."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_active", True)
            and getattr(user, "role", None) in ("EMPLOYEE", "MANAGER")
        )


def get_request_customer(request: Request) -> Any:
    """
    Resolve and cache the active Customer profile linked to the authenticated Account.
    Avoids duplicate queries between IsCustomer.has_permission() and the view.
    """
    cached = getattr(request, "_cached_customer", None)
    if cached is not None:
        return cached

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    from apps.customers.models import Customer

    customer = Customer.objects.filter(
        account_id=user.id,
        deleted_at__isnull=True,
    ).first()
    request._cached_customer = customer  # type: ignore[attr-defined]
    return customer


class IsCustomer(BasePermission):
    """
    Cho phép truy cập chỉ khi người dùng đã xác thực, còn hoạt động,
    có Account.role == 'CUSTOMER' và gắn với hồ sơ Customer đang hoạt động.
    """

    message = "Bạn không có quyền thực hiện thao tác này."

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        if not (
            user
            and user.is_authenticated
            and getattr(user, "is_active", True)
            and getattr(user, "deleted_at", None) is None
            and getattr(user, "role", None) == "CUSTOMER"
        ):
            return False

        customer = get_request_customer(request)
        return customer is not None
