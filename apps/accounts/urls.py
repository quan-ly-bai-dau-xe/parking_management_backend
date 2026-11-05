"""
URL configuration for accounts app.
Wire core authentication endpoints under /api/v1/auth/ per TL-52 and ADR-0004.
"""

from django.urls import path

from apps.accounts.views import (
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

urlpatterns = [
    path("csrf/", CSRFBootstrapView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
    path(
        "forgot-password/",
        ForgotPasswordView.as_view(),
        name="auth-forgot-password",
    ),
    path(
        "reset-password/",
        ResetPasswordConfirmView.as_view(),
        name="auth-reset-password",
    ),
    path(
        "password-reset/request/",
        ForgotPasswordView.as_view(),
        name="auth-password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        ResetPasswordConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),
    path(
        "forgot-password/sms/",
        ForgotPasswordSMSView.as_view(),
        name="auth-forgot-password-sms",
    ),
    path(
        "reset-password/sms/",
        ResetPasswordSMSConfirmView.as_view(),
        name="auth-reset-password-sms",
    ),
    path(
        "password-reset/sms/request/",
        ForgotPasswordSMSView.as_view(),
        name="auth-password-reset-sms-request",
    ),
    path(
        "password-reset/sms/confirm/",
        ResetPasswordSMSConfirmView.as_view(),
        name="auth-password-reset-sms-confirm",
    ),
    path(
        "register/sms/request/",
        RegisterSMSRequestView.as_view(),
        name="auth-register-sms-request",
    ),
    path(
        "register/sms/confirm/",
        RegisterSMSConfirmView.as_view(),
        name="auth-register-sms-confirm",
    ),
    path(
        "register/",
        RegisterSMSConfirmView.as_view(),
        name="auth-register",
    ),
]
