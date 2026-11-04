"""
URL configuration for accounts app.
Wire core authentication endpoints under /api/v1/auth/ per TL-52 and ADR-0004.
"""

from django.urls import path

from apps.accounts.views import (
    CSRFBootstrapView,
    CurrentUserView,
    ForgotPasswordView,
    LoginView,
    LogoutView,
    ResetPasswordConfirmView,
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
]
