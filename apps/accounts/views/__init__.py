"""
Views package for accounts app.
"""

from apps.accounts.views.auth import (
    CSRFBootstrapView,
    CurrentUserView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    ResetPasswordConfirmView,
)
from apps.accounts.views.csrf import custom_csrf_failure_view

__all__ = [
    "CSRFBootstrapView",
    "CurrentUserView",
    "ForgotPasswordView",
    "LoginView",
    "LogoutView",
    "ResetPasswordConfirmView",
    "custom_csrf_failure_view",
]
