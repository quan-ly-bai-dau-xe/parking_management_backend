"""
URL configuration for accounts app.
Wire core authentication endpoints under /api/v1/auth/ per TL-52 and ADR-0004.
"""

from django.urls import path

from apps.accounts.views import (
    CSRFBootstrapView,
    CurrentUserView,
    LoginView,
    LogoutView,
)

urlpatterns = [
    path("csrf/", CSRFBootstrapView.as_view(), name="auth-csrf"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", CurrentUserView.as_view(), name="auth-me"),
]
