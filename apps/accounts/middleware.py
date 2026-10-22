"""
Persistent Remember-Me Middleware for Accounts App.
Enforces OWASP series/token persistent login token verification per ADR-0004, TL-36, and OQ-87.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Callable
from datetime import timedelta
from typing import TYPE_CHECKING

import django.db
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account, PersistentLoginToken
from apps.accounts.services.auth import (
    clear_remember_cookie,
    get_client_ip,
    set_remember_cookie,
)

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class PersistentRememberMeMiddleware:
    """
    Middleware that re-authenticates anonymous users presenting a valid remember-me cookie.

    Preserves 0-query invariant for standard requests:
    - Guard 1: In-memory cookie dictionary lookup (0 DB queries, does not touch request.user).
    - Guard 2: In-memory session authentication flag (0 DB queries if already logged in).
    - Guard 3: Validate format (<series>:<raw_token>).
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        cookie_name = settings.REMEMBER_COOKIE_NAME

        # Guard 1: Pure in-memory dict lookup - 0 DB queries, does not evaluate lazy user
        raw_cookie = request.COOKIES.get(cookie_name)
        if not raw_cookie:
            return self.get_response(request)

        # Guard 2: Pure in-memory session flag - 0 DB queries if already authenticated via session
        if request.user.is_authenticated:
            return self.get_response(request)

        # Guard 3: Format validation for <series>:<raw_token>
        if ":" not in raw_cookie:
            response = self.get_response(request)
            clear_remember_cookie(response)
            return response

        series, raw_token = raw_cookie.split(":", 1)
        series = series.strip()
        raw_token = raw_token.strip()

        if not series or not raw_token:
            response = self.get_response(request)
            clear_remember_cookie(response)
            return response

        should_delete_cookie = False
        authenticated_account: Account | None = None
        new_token_data: tuple[str, str] | None = None

        grace_seconds = settings.REMEMBER_ROTATION_GRACE_SECONDS
        grace_delta = timedelta(seconds=grace_seconds)
        max_ip = PersistentLoginToken._meta.get_field("ip_address").max_length or 45
        max_ua = PersistentLoginToken._meta.get_field("user_agent").max_length or 255

        try:
            # Minimal lock scope: select_for_update is confined exclusively to the token row.
            # Avoid holding token row lock while acquiring account row locks to prevent deadlocks (RSK-09).
            with transaction.atomic():
                token_obj = (
                    PersistentLoginToken.objects.select_for_update()
                    .filter(series=series)
                    .first()
                )

                if token_obj is None:
                    should_delete_cookie = True
                elif token_obj.expires_at <= timezone.now():
                    token_obj.delete()
                    should_delete_cookie = True
                else:
                    # Non-locking snapshot read of account status
                    account = Account.objects.filter(id=token_obj.account_id).first()
                    if (
                        account is None
                        or not account.is_active
                        or account.deleted_at is not None
                    ):
                        token_obj.delete()
                        should_delete_cookie = True
                    else:
                        stored_hash = token_obj.token_hash
                        if ":" in stored_hash:
                            current_hash, previous_hash = stored_hash.split(":", 1)
                        else:
                            current_hash, previous_hash = stored_hash, None

                        presented_hash = hashlib.sha256(
                            raw_token.encode("utf-8")
                        ).hexdigest()
                        now = timezone.now()

                        if secrets.compare_digest(presented_hash, current_hash):
                            # Matches current active token
                            if now - token_obj.last_used_at <= grace_delta:
                                # Within grace window: skip rotation per OQ-87 and ADR-0004 to prevent SPA race conditions
                                authenticated_account = account
                            else:
                                # Grace window elapsed: perform atomic token rotation
                                new_raw = secrets.token_hex(32)
                                new_hash = hashlib.sha256(
                                    new_raw.encode("utf-8")
                                ).hexdigest()
                                token_obj.token_hash = f"{new_hash}:{current_hash}"
                                token_obj.last_used_at = now
                                token_obj.ip_address = (get_client_ip(request) or "")[
                                    :max_ip
                                ]
                                token_obj.user_agent = (
                                    request.META.get("HTTP_USER_AGENT") or ""
                                )[:max_ua]
                                token_obj.save(
                                    update_fields=[
                                        "token_hash",
                                        "last_used_at",
                                        "ip_address",
                                        "user_agent",
                                    ]
                                )
                                authenticated_account = account
                                new_token_data = (series, new_raw)

                        elif previous_hash and secrets.compare_digest(
                            presented_hash, previous_hash
                        ):
                            # Matches previous rotated token
                            if now - token_obj.last_used_at <= grace_delta:
                                # Concurrent request arrived during rotation window: accept without rotating
                                authenticated_account = account
                            else:
                                # Stale token replayed outside grace window: Token Theft detected!
                                PersistentLoginToken.objects.filter(
                                    account=account
                                ).delete()
                                logger.warning(
                                    "Security Alert: Expired remember token replay detected for account_id=%s, series=%s",
                                    account.id,
                                    series,
                                )
                                should_delete_cookie = True

                        else:
                            # Series match but hash mismatch: Token Theft detected!
                            PersistentLoginToken.objects.filter(
                                account=account
                            ).delete()
                            logger.warning(
                                "Security Alert: Remember token theft suspected for account_id=%s, series=%s",
                                account.id,
                                series,
                            )
                            should_delete_cookie = True

        except django.db.Error as db_err:
            logger.warning(
                "Transient database error verifying remember-me token: %s",
                db_err.__class__.__name__,
            )
            authenticated_account = None
            new_token_data = None
            should_delete_cookie = False

        # Session authentication and key cycling happen outside the token row lock
        if authenticated_account is not None:
            auth_login(request, authenticated_account)
            request.session.cycle_key()
            # Browser-session cookie per ADR-0004 and TL-53
            request.session.set_expiry(0)

        response = self.get_response(request)

        if should_delete_cookie:
            clear_remember_cookie(response)
        elif new_token_data is not None:
            series_val, token_val = new_token_data
            set_remember_cookie(response, series_val, token_val)

        return response
