"""
Views package for accounts app.
"""

from apps.accounts.views.auth import (
    CSRFBootstrapView,
    CurrentUserView,
    ForgotPasswordSMSView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    RegisterSMSConfirmView,
    RegisterSMSRequestView,
    ResetPasswordConfirmView,
    ResetPasswordSMSConfirmView,
)
from apps.accounts.views.csrf import custom_csrf_failure_view

__all__ = [
    "CSRFBootstrapView",
    "CurrentUserView",
    "ForgotPasswordSMSView",
    "ForgotPasswordView",
    "LoginView",
    "LogoutView",
    "RegisterSMSConfirmView",
    "RegisterSMSRequestView",
    "ResetPasswordConfirmView",
    "ResetPasswordSMSConfirmView",
    "custom_csrf_failure_view",
]
