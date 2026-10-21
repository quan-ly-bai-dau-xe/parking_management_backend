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
