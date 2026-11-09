"""
Authentication services for accounts app per ADR-0004, Schema v2, and TL-01.
"""

import hashlib
import re
import secrets
from datetime import timedelta
from typing import NoReturn

from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.hashers import check_password, get_hasher
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import connection, transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from rest_framework import status

from apps.accounts.models import Account, PasswordResetToken, PersistentLoginToken
from apps.accounts.selectors.auth import get_active_account_by_identifier
from apps.accounts.services.firebase_otp import (
    format_phone_number as fb_format_phone_number,
    is_firebase_configured,
    send_sms_otp as fb_send_sms_otp,
    verify_sms_otp as fb_verify_sms_otp,
)
from apps.accounts.services.sms import (
    is_valid_phone_number,
    normalize_vietnamese_phone,
    send_sms,
)
from apps.accounts.services.throttling import (
    PasswordResetLimiter,
    SMSOTPLimiter,
    get_client_ip,
)
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message, get_srs_message
from apps.customers.models import Customer

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


def hash_token(token: str, key_salt: str = "accounts.password_reset_token") -> str:
    """
    Tạo mã băm bảo mật HMAC-SHA256 cho token đặt lại mật khẩu và mã OTP.
    Sử dụng salted_hmac kết hợp SECRET_KEY theo khuyến nghị của Django & OWASP,
    ngăn chặn tấn công rainbow table và giải quyết triệt để cảnh báo CodeQL
    (Use of a broken or weak cryptographic hashing algorithm on sensitive data).
    """
    return salted_hmac(key_salt, token, algorithm="sha256").hexdigest()


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
    token_hash = hash_token(raw_token)

    lifetime_minutes = settings.PASSWORD_RESET_TOKEN_LIFETIME_MINUTES
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
    from_email = settings.DEFAULT_FROM_EMAIL

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

    token_hash = hash_token(clean_token)
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


def generate_numeric_otp(length: int = 6) -> str:
    """Sinh mã OTP số ngẫu nhiên an toàn bằng thư viện secrets."""
    low = 10 ** (length - 1)
    high = 10**length
    return f"{secrets.randbelow(high - low) + low:0{length}d}"


def request_password_reset_sms(
    request: HttpRequest, phone: str, recaptcha_token: str | None = None
) -> dict[str, Any] | None:
    """
    Xử lý yêu cầu đặt lại mật khẩu qua SMS OTP per REQ-4.1-F04, TL-01, OQ-03:
    1. Chuẩn hóa và kiểm tra số điện thoại hợp lệ.
    2. Giới hạn tần suất và cooldown 60s qua SMSOTPLimiter.
    3. Tìm tài khoản hoạt động theo số điện thoại (anti-enumeration).
    4. Hủy token reset chưa dùng trước đó của tài khoản.
    5. Sinh OTP 6 chữ số, lưu hash SHA-256 vào PasswordResetToken (hết hạn sau 5 phút).
    6. Gửi OTP qua Firebase Identity Toolkit REST API (hoặc SMS provider/console fallback).
    7. Trả về dict chứa session_info và otp (phục vụ FE và testing).
    """
    clean_phone = normalize_vietnamese_phone(phone)
    if not is_valid_phone_number(clean_phone):
        raise BusinessAPIException(
            code="PROP-4.1-P15",
            message=get_prop_message(
                "PROP-4.1-P15", "Số điện thoại không đúng định dạng."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    limiter = SMSOTPLimiter()
    limiter.check_and_increment(request, clean_phone, action="reset")

    account = Account.objects.filter(
        phone=clean_phone, is_active=True, deleted_at__isnull=True
    ).first()

    if account is None:
        # Anti-enumeration: trả về None nhưng không tiết lộ số điện thoại có tồn tại hay không
        return None

    # Hủy các token reset chưa dùng của tài khoản
    PasswordResetToken.objects.filter(account=account, used_at__isnull=True).delete()

    otp = generate_numeric_otp(6)
    token_hash = hash_token(otp)

    lifetime_seconds = settings.SMS_OTP_LIFETIME_SECONDS
    now = timezone.now()
    expires_at = now + timedelta(seconds=lifetime_seconds)
    client_ip = (get_client_ip(request) or "")[:45]

    PasswordResetToken.objects.create(
        account=account,
        token_hash=token_hash,
        expires_at=expires_at,
        requested_ip=client_ip,
        created_at=now,
    )

    # Đặt lại bộ đếm số lần xác thực sai
    attempt_key = f"otp_attempts:reset:{account.id}"
    cache.set(attempt_key, 0, timeout=lifetime_seconds)

    # 1. Gửi qua Firebase Phone Auth REST API
    session_info = None
    is_mock = True
    try:
        fb_result = fb_send_sms_otp(clean_phone, recaptcha_token)
        session_info = fb_result.get("sessionInfo")
        is_mock = fb_result.get("isMock", False)
        if session_info:
            cache.set(f"firebase_session:reset:{clean_phone}", session_info, timeout=lifetime_seconds)
    except Exception as fb_exc:
        # Ghi log nhưng không chặn luồng nếu SMS Console/Mock đang bật
        pass

    message = (
        f"[Bãi đỗ xe] Mã OTP xác thực đặt lại mật khẩu của bạn là: {otp}. "
        f"Mã có hiệu lực trong {lifetime_seconds // 60} phút. Vui lòng không chia sẻ mã này cho bất kỳ ai."
    )
    send_sms(clean_phone, message)

    return {
        "otp": otp,
        "session_info": session_info,
        "is_mock": is_mock,
        "phone": clean_phone,
    }


def confirm_password_reset_sms(
    phone: str,
    otp: str,
    new_password: str,
    session_info: str | None = None,
    firebase_token: str | None = None,
) -> Account:
    """
    Xác nhận đặt lại mật khẩu bằng mã OTP nhận qua SMS hoặc Firebase Phone Auth:
    1. Kiểm tra định dạng số điện thoại và OTP.
    2. Chống brute-force: tối đa 5 lần nhập sai sẽ vô hiệu hóa mã OTP.
    3. Xác minh qua Firebase Identity Toolkit REST API (nếu có session_info) hoặc PasswordResetToken.
    4. Cập nhật mật khẩu mới bằng Argon2 và thu hồi remember tokens.
    """
    clean_phone = normalize_vietnamese_phone(phone)
    clean_otp = otp.strip()

    if (
        not is_valid_phone_number(clean_phone)
        or len(clean_otp) != 6
        or not clean_otp.isdigit()
    ):
        raise BusinessAPIException(
            code="PROP-4.1-P11",
            message=get_prop_message(
                "PROP-4.1-P11", "Mã OTP không chính xác hoặc đã hết hạn."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    account = Account.objects.filter(
        phone=clean_phone, is_active=True, deleted_at__isnull=True
    ).first()

    if account is None:
        raise BusinessAPIException(
            code="PROP-4.1-P11",
            message=get_prop_message(
                "PROP-4.1-P11", "Mã OTP không chính xác hoặc đã hết hạn."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    attempt_key = f"otp_attempts:reset:{account.id}"
    attempts = int(cache.get(attempt_key, 0) or 0)
    max_attempts = settings.SMS_OTP_MAX_ATTEMPTS

    if attempts >= max_attempts:
        PasswordResetToken.objects.filter(
            account=account, used_at__isnull=True
        ).delete()
        cache.delete(attempt_key)
        raise BusinessAPIException(
            code="PROP-4.1-P16",
            message=get_prop_message(
                "PROP-4.1-P16",
                "Bạn đã nhập sai mã OTP quá 5 lần. Mã OTP này đã bị hủy, vui lòng yêu cầu mã mới.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    now = timezone.now()
    verified_by_firebase = False

    # Thử xác minh qua Firebase nếu có session_info (truyền lên hoặc lưu trong cache)
    active_session_info = session_info or cache.get(f"firebase_session:reset:{clean_phone}")
    if active_session_info and is_firebase_configured():
        try:
            fb_auth = fb_verify_sms_otp(active_session_info, clean_otp)
            if fb_auth.get("status") == "success":
                verified_by_firebase = True
        except Exception:
            pass

    token_hash = hash_token(clean_otp)
    reset_token = PasswordResetToken.objects.filter(
        account=account,
        token_hash=token_hash,
        used_at__isnull=True,
        expires_at__gt=now,
    ).first()

    if not verified_by_firebase and reset_token is None:
        cache.set(attempt_key, attempts + 1, timeout=300)
        raise BusinessAPIException(
            code="PROP-4.1-P11",
            message=get_prop_message(
                "PROP-4.1-P11", "Mã OTP không chính xác hoặc đã hết hạn."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        account.set_password(new_password)
        account.save()

        if reset_token:
            reset_token.used_at = now
            reset_token.save(update_fields=["used_at"])

        revoke_all_account_tokens(account.id)
        cache.delete(attempt_key)
        cache.delete(f"firebase_session:reset:{clean_phone}")

    return account


def request_register_otp(
    request: HttpRequest, phone: str, recaptcha_token: str | None = None
) -> dict[str, Any]:
    """
    Yêu cầu mã OTP qua SMS để đăng ký tài khoản khách hàng mới:
    1. Chuẩn hóa số điện thoại, kiểm tra định dạng.
    2. Kiểm tra số điện thoại chưa tồn tại trong tài khoản hoạt động.
    3. Áp dụng giới hạn tần suất gửi OTP và cooldown 60s.
    4. Sinh OTP 6 chữ số, lưu hash SHA-256 vào cache với thời hạn 5 phút.
    5. Gửi SMS chứa OTP qua Firebase Phone Auth REST API (hoặc SMS provider/console fallback).
    6. Trả về dict chứa session_info và otp (phục vụ FE và testing).
    """
    clean_phone = normalize_vietnamese_phone(phone)
    if not is_valid_phone_number(clean_phone):
        raise BusinessAPIException(
            code="PROP-4.1-P15",
            message=get_prop_message(
                "PROP-4.1-P15", "Số điện thoại không đúng định dạng."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Kiểm tra số điện thoại đã tồn tại
    if Account.objects.filter(
        phone=clean_phone, is_active=True, deleted_at__isnull=True
    ).exists():
        raise BusinessAPIException(
            code="PROP-4.1-P13",
            message=get_prop_message(
                "PROP-4.1-P13", "Số điện thoại đã tồn tại trong hệ thống."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )

    limiter = SMSOTPLimiter()
    limiter.check_and_increment(request, clean_phone, action="register")

    otp = generate_numeric_otp(6)
    token_hash = hash_token(otp)
    lifetime_seconds = settings.SMS_OTP_LIFETIME_SECONDS

    # 1. Gửi qua Firebase Phone Auth REST API
    session_info = None
    is_mock = True
    try:
        fb_result = fb_send_sms_otp(clean_phone, recaptcha_token)
        session_info = fb_result.get("sessionInfo")
        is_mock = fb_result.get("isMock", False)
        if session_info:
            cache.set(f"firebase_session:register:{clean_phone}", session_info, timeout=lifetime_seconds)
    except Exception as fb_exc:
        pass

    cache_key = f"otp:register:{clean_phone}"
    cache.set(
        cache_key,
        {
            "token_hash": token_hash,
            "session_info": session_info,
            "attempts": 0,
        },
        timeout=lifetime_seconds,
    )

    message = (
        f"[Bãi đỗ xe] Mã OTP xác thực đăng ký tài khoản của bạn là: {otp}. "
        f"Mã có hiệu lực trong {lifetime_seconds // 60} phút. Vui lòng không chia sẻ mã này cho bất kỳ ai."
    )
    send_sms(clean_phone, message)

    return {
        "otp": otp,
        "session_info": session_info,
        "is_mock": is_mock,
        "phone": clean_phone,
    }


def confirm_register_sms(
    phone: str,
    otp: str,
    password: str,
    full_name: str,
    identity_card_number: str | None = None,
    email: str | None = None,
    session_info: str | None = None,
    firebase_token: str | None = None,
) -> tuple[Account, Customer]:
    """
    Xác thực OTP và hoàn tất đăng ký tài khoản Khách hàng (CUSTOMER) per OQ-03, TL-01:
    1. Kiểm tra mã OTP qua Firebase Phone Auth REST API (nếu có session_info) hoặc cache.
    2. Chống brute-force: tối đa 5 lần nhập sai sẽ vô hiệu hóa mã OTP.
    3. Kiểm tra tính duy nhất của Phone, Email và CCCD.
    4. Tạo Account (role=CUSTOMER) với mật khẩu băm Argon2.
    5. Tạo Customer với mã KH%04d theo sequence advisory lock, liên kết với Account.
    6. Xóa OTP trong cache và trả về (Account, Customer).
    """
    clean_phone = normalize_vietnamese_phone(phone)
    clean_otp = otp.strip()

    if (
        not is_valid_phone_number(clean_phone)
        or len(clean_otp) != 6
        or not clean_otp.isdigit()
    ):
        raise BusinessAPIException(
            code="PROP-4.1-P11",
            message=get_prop_message(
                "PROP-4.1-P11", "Mã OTP không chính xác hoặc đã hết hạn."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    cache_key = f"otp:register:{clean_phone}"
    cache_data = cache.get(cache_key)

    attempts = int(cache_data.get("attempts", 0) or 0) if isinstance(cache_data, dict) else 0
    max_attempts = settings.SMS_OTP_MAX_ATTEMPTS

    if attempts >= max_attempts:
        cache.delete(cache_key)
        raise BusinessAPIException(
            code="PROP-4.1-P16",
            message=get_prop_message(
                "PROP-4.1-P16",
                "Bạn đã nhập sai mã OTP quá 5 lần. Mã OTP này đã bị hủy, vui lòng yêu cầu mã mới.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    verified_by_firebase = False
    active_session_info = session_info or (cache_data.get("session_info") if isinstance(cache_data, dict) else None) or cache.get(f"firebase_session:register:{clean_phone}")
    if active_session_info and is_firebase_configured():
        try:
            fb_auth = fb_verify_sms_otp(active_session_info, clean_otp)
            if fb_auth.get("status") == "success":
                verified_by_firebase = True
        except Exception:
            pass

    token_hash = hash_token(clean_otp)
    cached_hash = cache_data.get("token_hash") if isinstance(cache_data, dict) else None

    if not verified_by_firebase and (not cached_hash or token_hash != cached_hash):
        if isinstance(cache_data, dict):
            cache_data["attempts"] = attempts + 1
            cache.set(cache_key, cache_data, timeout=300)
        raise BusinessAPIException(
            code="PROP-4.1-P11",
            message=get_prop_message(
                "PROP-4.1-P11", "Mã OTP không chính xác hoặc đã hết hạn."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Kiểm tra trùng lặp số điện thoại
    if Account.objects.filter(phone=clean_phone, deleted_at__isnull=True).exists():
        raise BusinessAPIException(
            code="PROP-4.1-P13",
            message=get_prop_message(
                "PROP-4.1-P13", "Số điện thoại đã tồn tại trong hệ thống."
            ),
            status_code=status.HTTP_409_CONFLICT,
        )

    clean_email = email.strip().lower() if email and email.strip() else None
    if (
        clean_email
        and Account.objects.filter(
            email__iexact=clean_email, deleted_at__isnull=True
        ).exists()
    ):
        raise BusinessAPIException(
            code="MSG-4.3.1-M05",
            message="Dữ liệu email đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
            status_code=status.HTTP_409_CONFLICT,
        )

    # CCCD/CMND: kiểm tra hoặc tự tạo fallback hợp lệ đáp ứng ck_customer_idcard_digits (9-20 chữ số)
    clean_id_card = (
        identity_card_number.strip()
        if identity_card_number and str(identity_card_number).strip()
        else None
    )
    if clean_id_card:
        if not re.match(r"^[0-9]{9,20}$", clean_id_card):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Số CCCD/CMND phải gồm từ 9 đến 20 chữ số.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if Customer.objects.filter(
            identity_card_number=clean_id_card,
            deleted_at__isnull=True,
            is_anonymized=False,
        ).exists():
            raise BusinessAPIException(
                code="PROP-4.1-P18",
                message=get_prop_message(
                    "PROP-4.1-P18", "Số CCCD/CMND đã tồn tại trong hệ thống."
                ),
                status_code=status.HTTP_409_CONFLICT,
            )
    else:
        # Tự tạo placeholder duy nhất gồm 12 chữ số theo số điện thoại: "99" + 10 số cuối
        clean_id_card = f"99{clean_phone[-10:].zfill(10)}"
        # Đảm bảo duy nhất nếu số này đã vô tình trùng
        if Customer.objects.filter(
            identity_card_number=clean_id_card,
            deleted_at__isnull=True,
            is_anonymized=False,
        ).exists():
            clean_id_card = f"88{clean_phone[-10:].zfill(10)}"

    with transaction.atomic():
        account = Account.objects.create_user(
            email=clean_email,
            phone=clean_phone,
            password=password,
            role="CUSTOMER",
            is_active=True,
        )

        # Khóa advisory lock và sinh mã khách hàng KH%04d
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext('customer_code_sequence'));"
            )
            cursor.execute(
                """
                SELECT COALESCE(
                    MAX(
                        CASE
                            WHEN code ~ '^KH[0-9]+$' THEN SUBSTRING(code FROM 3)::INTEGER
                            ELSE 0
                        END
                    ), 0
                )
                FROM customer;
                """
            )
            max_num = cursor.fetchone()[0]
            customer_code = f"KH{max_num + 1:04d}"

        customer = Customer.objects.create(
            code=customer_code,
            full_name=full_name.strip(),
            identity_card_number=clean_id_card,
            phone=clean_phone,
            email=clean_email,
            account=account,
            status="ACTIVE",
        )

        cache.delete(cache_key)

    return account, customer
