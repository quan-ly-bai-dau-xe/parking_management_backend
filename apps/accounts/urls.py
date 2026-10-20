"""
URL configuration for accounts app.
"""

from django.urls import path

from . import login_views

urlpatterns = [
    path("login/", login_views.LoginView.as_view(), name="login"),
    # Additional endpoints will be added here as views are implemented
    # path('register/', login_views.register, name='register'),
]
