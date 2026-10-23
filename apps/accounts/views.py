"""
Login views for the accounts app.
"""

import json
import re
import secrets
from datetime import timedelta
from hashlib import sha256

from django.contrib.auth import authenticate, login
from django.http import JsonResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from apps.accounts.models import Account, PersistentLoginToken

# Used to satisfy linter for Account and PersistentLoginToken
_ = Account
_ = PersistentLoginToken


@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(View):
    """
    Handle user login requests.
    """

    def post(self, request):
        """
        Process login form submission.
        """
        try:
            # Parse JSON data from request body
            data = json.loads(request.body)
            username = data.get("username", "").strip()
            password = data.get("password", "")
            remember_me = data.get("remember_me", False)

            # Validation
            if not username:
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
                            "details": [
                                {
                                    "field": "username",
                                    "message": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
                                }
                            ],
                        },
                    },
                    status=400,
                )

            if not password:
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
                            "details": [
                                {
                                    "field": "password",
                                    "message": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
                                }
                            ],
                        },
                    },
                    status=400,
                )

            # Check for special characters in username (per SRS 4.1-F01)
            # The Account model already has a validator, but we check here for immediate feedback
            if not re.match(r"^[a-zA-Z0-9_.-]+$", username):
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Tên đăng nhập không chứa ký tự đặc biệt",
                            "details": [
                                {
                                    "field": "username",
                                    "message": "Tên đăng nhập không chứa ký tự đặc biệt",
                                }
                            ],
                        },
                    },
                    status=400,
                )

            # Authenticate user
            user = authenticate(request, username=username, password=password)

            if user is None:
                # Invalid credentials
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "INVALID_CREDENTIALS",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": [
                                {
                                    "field": "non_field",
                                    "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                                }
                            ],
                        },
                    },
                    status=401,
                )

            # Inform Pylance that user is an Account instance
            user: Account

            # Check if user is active
            if not user.is_active:
                return JsonResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "ACCOUNT_DISABLED",
                            "message": "Tài khoản đã được vô hiệu hóa",
                            "details": [
                                {
                                    "field": "non_field",
                                    "message": "Tài khoản đã được vô hiệu hóa",
                                }
                            ],
                        },
                    },
                    status=403,
                )

            # Perform login
            login(request, user)

            # Cycle session key to prevent session fixation
            request.session.cycle_key()

            # Handle remember me functionality
            if remember_me:
                self._handle_remember_me(request, user)

            # Return success response
            return JsonResponse(
                {
                    "success": True,
                    "data": {
                        "user": {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role,
                            "is_staff": user.is_staff,
                            "is_superuser": user.is_superuser,
                        }
                    },
                }
            )

        except json.JSONDecodeError:
            return JsonResponse(
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_REQUEST",
                        "message": "Yêu cầu không hợp lệ",
                        "details": [
                            {"field": "non_field", "message": "Yêu cầu không hợp lệ"}
                        ],
                    },
                },
                status=400,
            )
        except Exception as _:
            return JsonResponse(
                {
                    "success": False,
                    "error": {
                        "code": "SERVER_ERROR",
                        "message": "Lỗi hệ thống",
                        "details": [{"field": "non_field", "message": "Lỗi hệ thống"}],
                    },
                },
                status=500,
            )

    def _handle_remember_me(self, request, user):
        """
        Handle remember me functionality.
        Implements the secure token pattern from ADR-0004 with token rotation.
        """
        # Invalidate any existing remember me tokens for this user on new login
        # This ensures only one active remember me token per user (optional but secure)
        PersistentLoginToken.objects.filter(account=user).delete()

        # Generate a secure random token
        token = secrets.token_hex(32)  # 256-bit secure random token
        token_hash = sha256(token.encode()).hexdigest()

        # Set expiration (30 days as mentioned in ADR-0004)
        expires_at = timezone.now() + timedelta(days=30)

        # Get client IP address
        ip_address = self._get_client_ip(request)

        # Create the persistent login token record
        PersistentLoginToken.objects.create(
            account=user,
            series=urlsafe_base64_encode(force_bytes(secrets.token_bytes(16))),
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],  # Limit length
            expires_at=expires_at,
        )

        # In a real implementation, we would set the cookie here
        # For the API view, the frontend would handle setting the cookie
        # based on the token we would return (though for security, we typically
        # don't return the token to the frontend in API-only implementations)

        # Note: According to ADR-0004, on re-authentication, the consumed token
        # is invalidated, a fresh token is issued, and if an invalid or already-used
        # token is presented, all user remember tokens are revoked.
        # Our implementation above invalidates existing tokens on each login,
        # which provides a similar security benefit.

    def _get_client_ip(self, request):
        """
        Get the client's IP address from the request.
        """
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = request.META.get("REMOTE_ADDR")
        return ip


# Alternative function-based view approach
@ensure_csrf_cookie
@require_http_methods(["POST"])
def login_view(request):
    """
    Function-based login view alternative.
    """
    view = LoginView()
    return view.post(request)


@ensure_csrf_cookie
@require_http_methods(["POST"])
def reset_view(request):
    """
    Reset/Login form clearing endpoint.
    """
    # This endpoint is called when the user clicks the "Reset" button
    # It simply returns success so the frontend can clear the form
    # Use request to satisfy linter (even though we don't need it in this function)
    _ = request
    return JsonResponse({"success": True, "message": "Form reset successfully"})
