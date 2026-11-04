"""
Authentication services for accounts app per ADR-0004, Schema v2, and TL-01.
"""

import hashlib
import secrets
from datetime import timedelta
from typing import NoReturn

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.hashers import check_password, get_hasher
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Account, PasswordResetToken, PersistentLoginToken
from apps.accounts.selectors.auth import get_active_account_by_identifier
from apps.accounts.services.throttling import PasswordResetLimiter, get_client_ip
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message, get_srs_message

# cspell:disable
# High-entropy pre-computed dummy hashes for anti-timing protection (OWASP CWE-208 / TL-52)
DUMMY_ARGON2_HASH = (
    "argon2$argon2id$v=19$m=102400,t=2,p=8$"
    "TGlqWHJkR1Q5N0d3MUZyek50b21lQQ$"
    "JD8z2Dr4OBCceKFq44MCJfXtYshloZSwL6tQzID3opI"
)

DUMMY_PBKDF2_HASH = (
    "pbkdf2_sha256$1500000$X6Ww7hyHfCtJ8d2Gti51VG$"
    "7WahN7QjfBP80klAivKpmJKntm4BQrdFPIRBQS0ELps="
)
# cspell:enable


def get_dummy_password_hash() -> str:
    """
    Returns pre-computed dummy hash matching active primary hasher.
    In base/production, Argon2 is primary to prevent timing attacks.
    In test settings, fast PBKDF2 is primary to maintain test velocity.
    """
    try:
        primary_hasher = get_hasher()
        if primary_hasher.algorithm and primary_hasher.algorithm.startswith("pbkdf2"):
            return DUMMY_PBKDF2_HASH
    except ValueError, LookupError:
        pass
    return DUMMY_ARGON2_HASH


def check_password_anti_timing(raw_password: str) -> bool:
    """
    Anti-timing dummy verification executing constant CPU cycles
    when an account does not exist or is inactive (OWASP CWE-208 / TL-52).
    """
    dummy_hash = get_dummy_password_hash()
    return check_password(raw_password, dummy_hash)


def _raise_invalid_credentials_error() -> NoReturn:
    """Raises byte-identical 401 BusinessAPIException for invalid authentication attempts."""
    raise BusinessAPIException(
        code="MSG-4.1-M02",
        message=get_srs_message(
            "MSG-4.1-M02",
            "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
        ),
        status_code=status.HTTP_401_UNAUTHORIZED,
        details={},
    )


def authenticate_account(identifier: str, password: str) -> Account:
    """
    Xác thực tài khoản theo identifier (email hoặc phone) và password.

    Quy tắc an ninh theo TL-52 và OWASP:
    - Nếu tài khoản không tồn tại, inactive hoặc soft-deleted -> chạy check_password_anti_timing
      rồi raise BusinessAPIException(code="MSG-4.1-M02", status_code=401).
    - Nếu tài khoản tồn tại nhưng sai mật khẩu -> raise BusinessAPIException(code="MSG-4.1-M02", status_code=401).
    - Thân lỗi của mọi trường hợp thất bại là giống hệt nhau (byte-identical), không gợi ý trường.
    """
    account = get_active_account_by_identifier(identifier)
    if account is None:
        check_password_anti_timing(password)
        _raise_invalid_credentials_error()

    if not account.check_password(password):
        _raise_invalid_credentials_error()

    return account


def set_remember_cookie(response: HttpResponse, series: str, raw_token: str) -> None:
    """Sets secure remember-me cookie with settings-configured lifetime and name."""
    cookie_name = settings.REMEMBER_COOKIE_NAME
    lifetime_days = settings.REMEMBER_TOKEN_LIFETIME_DAYS
    cookie_val = f"{series}:{raw_token}"
    response.set_cookie(
        cookie_name,
        cookie_val,
        max_age=lifetime_days * 86400,
        httponly=True,
        samesite="Lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )


def clear_remember_cookie(response: HttpResponse) -> None:
    """Removes remember-me cookie from response."""
    cookie_name = settings.REMEMBER_COOKIE_NAME
    response.delete_cookie(cookie_name)


def create_remember_token(account: Account, request: HttpRequest) -> tuple[str, str]:
    """
    Phát hành remember-me token bền per ADR-0004 & TL-36.
    Trả về (series, raw_token) để gán vào cookie parking_remember_token.
    Chỉ lưu SHA-256 hash của raw_token trong persistent_login_token.
    """
    series = secrets.token_hex(16)  # 32 characters
    raw_token = secrets.token_hex(32)  # 64 characters
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    max_ip = PersistentLoginToken._meta.get_field("ip_address").max_length or 45
    max_ua = PersistentLoginToken._meta.get_field("user_agent").max_length or 255
    ip_address = (get_client_ip(request) or "")[:max_ip]
    user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:max_ua]
    now = timezone.now()
    lifetime_days = settings.REMEMBER_TOKEN_LIFETIME_DAYS
    expires_at = now + timedelta(days=lifetime_days)

    # Limit active tokens per account (OQ-87, ADR-0004)
    max_tokens = settings.REMEMBER_MAX_TOKENS_PER_ACCOUNT
    existing_tokens = PersistentLoginToken.objects.filter(account=account).order_by(
        "created_at"
    )
    count = existing_tokens.count()
    if count >= max_tokens:
        excess = count - max_tokens + 1
        old_ids = list(existing_tokens.values_list("id", flat=True)[:excess])
        PersistentLoginToken.objects.filter(id__in=old_ids).delete()

    PersistentLoginToken.objects.create(
        series=series,
        token_hash=token_hash,
        account=account,
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=now,
        last_used_at=now,
        expires_at=expires_at,
    )

    return series, raw_token


def revoke_remember_token_by_series(series: str) -> None:
    """Thu hồi remember token theo series khi đăng xuất (TL-36 plain DELETE)."""
    PersistentLoginToken.objects.filter(series=series).delete()


def revoke_all_account_tokens(account_id: int) -> None:
    """Thu hồi toàn bộ remember token của tài khoản khi phát hiện tín hiệu bị đánh cắp."""
    PersistentLoginToken.objects.filter(account_id=account_id).delete()


def login_account(
    request: HttpRequest,
    account: Account,
    remember: bool = False,
    response: HttpResponse | None = None,
) -> None:
    """
    Thiết lập phiên đăng nhập cho người dùng:
    - auth_login(request, account)
    - request.session.cycle_key()
    - request.session.set_expiry(0) per ADR-0004 and TL-53 (browser-session cookie)
    - Nếu remember=True và có response: tạo remember token và gán cookie.
    """
    auth_login(request, account)
    request.session.cycle_key()
    request.session.set_expiry(0)

    if remember and response is not None:
        series, raw_token = create_remember_token(account, request)
        set_remember_cookie(response, series, raw_token)


def logout_account(
    request: HttpRequest,
    response: HttpResponse | None = None,
) -> None:
    """
    Đăng xuất người dùng:
    - Hủy Django session (auth_logout(request)).
    - Nếu có cookie remember-me, thu hồi dòng persistent_login_token tương ứng.
    - Xóa cookies session và remember-me trên response.
    """
    cookie_name = settings.REMEMBER_COOKIE_NAME
    remember_cookie = request.COOKIES.get(cookie_name)
    if remember_cookie and ":" in remember_cookie:
        series = remember_cookie.split(":", 1)[0].strip()
        if series:
            revoke_remember_token_by_series(series)

    auth_logout(request)

    if response is not None:
        response.delete_cookie(settings.SESSION_COOKIE_NAME)
        clear_remember_cookie(response)


def request_password_reset(request: HttpRequest, email: str) -> str | None:
    """
    Xử lý yêu cầu đặt lại mật khẩu per REQ-4.1-F04, OQ-84, TL-36:
    1. Kiểm tra rate limit (OQ-84: 3 req/giờ per email, 10 req/giờ per IP).
    2. Tìm tài khoản theo email (anti-enumeration: nếu không tìm thấy, vẫn trả về None mà không báo lỗi).
    3. Hủy bỏ (xóa plain DELETE per TL-36) các token chưa dùng trước đó của tài khoản.
    4. Sinh token ngẫu nhiên bảo mật (raw_token), tính mã băm SHA-256.
    5. Lưu PasswordResetToken với thời hạn (mặc định 15 phút).
    6. Gửi email hướng dẫn đặt lại mật khẩu kèm mã token.
    7. Trả về raw_token (phục vụ audit/testing).
    """
    limiter = PasswordResetLimiter()
    limiter.check_and_increment(request, email)

    norm_email = email.strip().lower()
    account = Account.objects.filter(
        email__iexact=norm_email, is_active=True, deleted_at__isnull=True
    ).first()

    if account is None or not account.email:
        # Anti-enumeration protection (OWASP): do not reveal whether the email exists
        return None

    # Revoke previous unused reset tokens for this account (TL-36 plain DELETE permitted)
    PasswordResetToken.objects.filter(account=account, used_at__isnull=True).delete()

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    lifetime_minutes = getattr(settings, "PASSWORD_RESET_TOKEN_LIFETIME_MINUTES", 15)
    now = timezone.now()
    expires_at = now + timedelta(minutes=lifetime_minutes)
    client_ip = (get_client_ip(request) or "")[:45]

    PasswordResetToken.objects.create(
        account=account,
        token_hash=token_hash,
        expires_at=expires_at,
        requested_ip=client_ip,
        created_at=now,
    )

    subject = "[Hệ thống Bãi đỗ xe] Yêu cầu đặt lại mật khẩu"
    body = (
        f"Xin chào,\n\n"
        f"Chúng tôi đã nhận được yêu cầu đặt lại mật khẩu cho tài khoản {account.email}.\n\n"
        f"Mã xác thực đặt lại mật khẩu của bạn là:\n"
        f"{raw_token}\n\n"
        f"Mã này có hiệu lực trong vòng {lifetime_minutes} phút.\n"
        f"Nếu bạn không thực hiện yêu cầu này, vui lòng bỏ qua email và mật khẩu của bạn sẽ được giữ nguyên.\n\n"
        f"Trân trọng,\n"
        f"Ban Quản lý Bãi đỗ xe"
    )
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@parking.com")

    send_mail(
        subject=subject,
        message=body,
        from_email=from_email,
        recipient_list=[account.email],
        fail_silently=True,
    )

    return raw_token


def confirm_password_reset(token: str, new_password: str) -> Account:
    """
    Xác nhận đặt lại mật khẩu bằng token một lần per REQ-4.1-F04, TL-36:
    1. Tính hash SHA-256 của token.
    2. Tìm PasswordResetToken còn hiệu lực (used_at IS NULL, expires_at > now).
    3. Nếu không tìm thấy hoặc hết hạn -> ném BusinessAPIException(PROP-4.1-P08, 400).
    4. Cập nhật mật khẩu mới của tài khoản qua Argon2 (set_password).
    5. Đánh dấu token đã sử dụng (used_at) và thu hồi toàn bộ remember-me tokens per OWASP.
    """
    clean_token = token.strip()
    if not clean_token:
        raise BusinessAPIException(
            code="PROP-4.1-P08",
            message=get_prop_message(
                "PROP-4.1-P08",
                "Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    token_hash = hashlib.sha256(clean_token.encode("utf-8")).hexdigest()
    now = timezone.now()

    reset_token = (
        PasswordResetToken.objects.filter(
            token_hash=token_hash,
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .select_related("account")
        .first()
    )

    if reset_token is None or reset_token.account is None:
        raise BusinessAPIException(
            code="PROP-4.1-P08",
            message=get_prop_message(
                "PROP-4.1-P08",
                "Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    account = reset_token.account
    if not account.is_active or account.deleted_at is not None:
        raise BusinessAPIException(
            code="PROP-4.1-P08",
            message=get_prop_message(
                "PROP-4.1-P08",
                "Mã đặt lại mật khẩu không hợp lệ hoặc đã hết hạn.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        account.set_password(new_password)
        account.save()

        # Mark token as consumed
        reset_token.used_at = now
        reset_token.save(update_fields=["used_at"])

        # Revoke all persistent login tokens per OWASP credential rotation
        revoke_all_account_tokens(account.id)

    return account
