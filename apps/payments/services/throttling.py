"""
Per-customer rate limiter for VNPAY top-up intent creation.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message


class VnpayTopupLimiter:
    """Atomic cache-backed per-customer rate limiter for VNPAY payment URL creation."""

    DEFAULT_LIMIT = 10
    DEFAULT_WINDOW_SECONDS = 60

    def __init__(
        self,
        cache_backend: Any = None,
        limit: int = DEFAULT_LIMIT,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
    ) -> None:
        self.cache = cache_backend or cache
        self.limit = limit
        self.window_seconds = window_seconds

    def _atomic_incr(self, key: str, timeout: int) -> int:
        self.cache.add(key, 0, timeout)
        try:
            return int(self.cache.incr(key))
        except ValueError:
            if self.cache.add(key, 1, timeout):
                return 1
            return int(self.cache.incr(key))

    def check_and_increment(self, customer_id: int) -> None:
        key = f"throttle:vnpay:topup:customer:{customer_id}"
        count = self._atomic_incr(key, self.window_seconds)
        if count > self.limit:
            raise BusinessAPIException(
                code="PROP-VNPAY-RATE-LIMITED",
                message=get_message("PROP-VNPAY-RATE-LIMITED"),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                details={},
                wait=self.window_seconds,
                headers={"Retry-After": str(self.window_seconds)},
            )
