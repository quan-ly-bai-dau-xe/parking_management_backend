"""
CSRF failure view for authentication and API endpoints.
Returns JSON envelope for /api/* requests and delegates to Django HTML view for web/admin.
"""

from __future__ import annotations

import django.views.csrf
from django.http import HttpRequest, HttpResponse, JsonResponse

from apps.core.messages import ALL_MESSAGES


def custom_csrf_failure_view(
    request: HttpRequest,
    reason: str = "",
    template_name: str = django.views.csrf.CSRF_FAILURE_TEMPLATE_NAME,
) -> HttpResponse:
    """
    Handle CSRF check failures:
    - Return JSON envelope with PROP-4.1-P06 when request path starts with /api/
    - Delegate to Django default HTML view for other requests (e.g. /admin/)
    """
    if request.path.startswith("/api/"):
        return JsonResponse(
            {
                "code": "PROP-4.1-P06",
                "message": ALL_MESSAGES.get(
                    "PROP-4.1-P06",
                    "Mã CSRF không hợp lệ hoặc bị thiếu.",
                ),
                "details": {"reason": reason} if reason else {},
            },
            status=403,
        )

    return django.views.csrf.csrf_failure(
        request, reason=reason, template_name=template_name
    )
