"""
Atomic reserve-then-verify login attempt limiter.
Protects authentication endpoints against parallel brute-force attacks across 3 buckets:
1. (normalized identifier, client IP): 5 attempts / 15 min.
2. per-identifier ceiling: 20 attempts / 15 min.
3. per-IP ceiling for failures: 30 attempts / 15 min.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest
from rest_framework import status

from apps.accounts.selectors.auth import normalize_login_identifier
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message


def get_client_ip(request: HttpRequest) -> str:
    """
    Extracts client IP honoring DRF NUM_PROXIES semantics.
    If NUM_PROXIES <= 0 (default) or header missing, uses REMOTE_ADDR.
    Never trusts X-Forwarded-For by default.
    """
    num_proxies = settings.NUM_PROXIES
    remote_addr = request.META.get("REMOTE_ADDR") or ""
    if num_proxies is None or num_proxies <= 0:
        return remote_addr

    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if not xff and hasattr(request, "headers"):
        xff = request.headers.get("x-forwarded-for")
    if not xff:
        return remote_addr

    addresses = [ip.strip() for ip in xff.split(",") if ip.strip()]
    if not addresses:
        return remote_addr
    return addresses[-min(num_proxies, len(addresses))]


@dataclass(frozen=True)
class LimiterReservation:
    """Holds reservation keys to allow atomic rollback on successful authentication."""

    pair_key: str
    id_key: str
    ip_key: str
    window: int


class LoginAttemptLimiter:
    """
    Atomic rate limiter enforcing reserve-then-verify semantics.
    """

    def __init__(self, cache_backend: Any = None) -> None:
        self.cache = cache_backend or cache

    def _atomic_incr(self, key: str, timeout: int) -> int:
        """Atomically increments integer counter at key with TTL timeout."""
        self.cache.add(key, 0, timeout)
        try:
            return int(self.cache.incr(key))
        except ValueError:
            if self.cache.add(key, 1, timeout):
                return 1
            return int(self.cache.incr(key))

    def _atomic_decr(self, key: str) -> None:
        """Atomically decrements counter on successful login, pruning key at 0."""
        try:
            val = self.cache.decr(key)
            if val <= 0:
                self.cache.delete(key)
        except ValueError:
            pass

    def get_pair_key(self, norm_id: str, client_ip: str) -> str:
        ident_hash = hashlib.sha256(f"{norm_id}:{client_ip}".encode()).hexdigest()
        return f"throttle:login:pair:{ident_hash}"

    def get_identifier_key(self, norm_id: str) -> str:
        ident_hash = hashlib.sha256(norm_id.encode()).hexdigest()
        return f"throttle:login:id:{ident_hash}"

    def get_ip_key(self, client_ip: str) -> str:
        return f"throttle:login:ip:{client_ip}"

    def reserve_or_throttle(
        self, request: HttpRequest, identifier: str
    ) -> LimiterReservation:
        """
        Atomically reserves quota across all 3 buckets BEFORE password verification.
        Raises BusinessAPIException(PROP-4.1-P01, 429) if any limit is exceeded.
        """
        norm_id = normalize_login_identifier(identifier)
        client_ip = get_client_ip(request) or "unknown"
        window = settings.AUTH_THROTTLE_WINDOW_SECONDS

        pair_limit = settings.AUTH_THROTTLE_PAIR_LIMIT
        id_limit = settings.AUTH_THROTTLE_IDENTIFIER_LIMIT
        ip_limit = settings.AUTH_THROTTLE_IP_LIMIT

        pair_key = self.get_pair_key(norm_id, client_ip)
        id_key = self.get_identifier_key(norm_id)
        ip_key = self.get_ip_key(client_ip)

        # Atomic increment on all three buckets
        pair_count = self._atomic_incr(pair_key, window)
        id_count = self._atomic_incr(id_key, window)
        ip_count = self._atomic_incr(ip_key, window)

        # Check thresholds
        if pair_count > pair_limit or id_count > id_limit or ip_count > ip_limit:
            raise BusinessAPIException(
                code="PROP-4.1-P01",
                message=get_prop_message(
                    "PROP-4.1-P01",
                    "Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.",
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                details={},
                wait=window,
                headers={"Retry-After": str(window)},
            )

        return LimiterReservation(
            pair_key=pair_key,
            id_key=id_key,
            ip_key=ip_key,
            window=window,
        )

    def release_on_success(self, reservation: LimiterReservation) -> None:
        """
        Rolls back the reserved failure attempt on successful authentication.
        Resets the failed counter for this pair and identifier, and decrements IP failure counter.
        Ensures successful logins NEVER consume failed attempt quota.
        """
        self.cache.delete(reservation.pair_key)
        self.cache.delete(reservation.id_key)
        self._atomic_decr(reservation.ip_key)

    def reset(self, identifier: str, client_ip: str | None = None) -> None:
        """Explicitly reset counters for an identifier."""
        norm_id = normalize_login_identifier(identifier)
        if norm_id:
            self.cache.delete(self.get_identifier_key(norm_id))
            if client_ip:
                self.cache.delete(self.get_pair_key(norm_id, client_ip))
