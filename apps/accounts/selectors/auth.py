"""
Account selectors for database queries per Schema v2, TL-01, and TL-21.
"""

import re
from typing import Any

from apps.accounts.models import Account


def normalize_login_identifier(identifier: Any) -> str:
    """
    Chuẩn hóa tên đăng nhập theo TL-01, TL-21, và Schema v2:
    - Nếu chứa '@', chuyển thành lower-case sau khi strip.
    - Nếu là số điện thoại (không chứa '@'), loại bỏ khoảng trắng, dấu chấm, dấu gạch ngang.
    - Trả về chuỗi rỗng nếu không hợp lệ hoặc rỗng.
    """
    if not identifier or not isinstance(identifier, str):
        return ""
    clean = identifier.strip()
    if not clean:
        return ""
    if "@" in clean:
        return clean.lower()
    return re.sub(r"[\s.\-]+", "", clean)


def get_active_account_by_identifier(identifier: Any) -> Account | None:
    """
    Tra cứu tài khoản đang hoạt động (is_active=True, deleted_at__isnull=True)
    dựa trên email (case-insensitive) hoặc số điện thoại (đã loại bỏ khoảng trắng, dấu chấm, gạch ngang).

    Theo D2 & TL-21:
    - Nếu chứa ký tự '@', tra cứu theo lower(email) khớp index uq_account_email_active.
    - Nếu không chứa '@', chuẩn hóa chuỗi số (bỏ dấu cách, chấm, gạch ngang) và kiểm tra regex ^[0-9]{9,15}$.
    - Trả về Account nếu tìm thấy, ngược lại trả về None.
    """
    norm = normalize_login_identifier(identifier)
    if not norm:
        return None

    if "@" in norm:
        # Tra cứu theo email không phân biệt chữ hoa/thường khớp partial index uq_account_email_active
        return Account.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            email__iexact=norm,
        ).first()

    # Chuẩn hóa số điện thoại: kiểm tra regex ^[0-9]{9,15}$
    if re.match(r"^[0-9]{9,15}$", norm):
        return Account.objects.filter(
            is_active=True,
            deleted_at__isnull=True,
            phone=norm,
        ).first()

    return None


# Short public name of get_active_account_by_identifier (exported by apps.accounts.selectors).
get_account_by_identifier = get_active_account_by_identifier
