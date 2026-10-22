"""
Session code generator service for Parking Management Backend.
Generates race-safe session codes matching format #PK-YYYYMMDD-NNN per TL-05.
"""

import re
from typing import Any

from django.utils import timezone

from apps.parking.models import VehicleEntryExitLog


def generate_session_code(offset: int = 0, cursor: Any = None) -> str:
    """
    Sinh mã phiên đỗ xe an toàn race-condition theo định dạng #PK-YYYYMMDD-NNN.
    Ví dụ: #PK-20261018-001

    Khi truyền cursor trong transaction đã giữ advisory lock, hàm sẽ thực thi
    trực tiếp trên cursor đó để đảm bảo nhìn thấy mã mới nhất của transaction trước.
    """
    now = timezone.now()
    date_str = now.strftime("%Y%m%d")
    prefix = f"#PK-{date_str}-"

    if cursor is not None:
        # Thực thi qua cursor của transaction đã nắm advisory lock
        # Tối ưu hóa: dùng ORDER BY id DESC tận dụng btree primary key index scan
        cursor.execute(
            """
            SELECT session_code
            FROM vehicle_entry_exit_log
            WHERE session_code LIKE %s
            ORDER BY id DESC
            LIMIT 1;
            """,
            (f"{prefix}%",),
        )
        row = cursor.fetchone()
        latest_code = row[0] if row else None
    else:
        # Fallback ORM query
        latest_code = (
            VehicleEntryExitLog.objects.filter(session_code__startswith=prefix)
            .order_by("-id")
            .values_list("session_code", flat=True)
            .first()
        )

    next_seq = 1 + max(0, offset)
    if latest_code:
        match = re.search(r"-(\d+)$", latest_code)
        if match:
            try:
                next_seq = int(match.group(1)) + 1 + max(0, offset)
            except ValueError:
                next_seq = 1 + max(0, offset)

    candidate_code = f"{prefix}{next_seq:03d}"

    # Kiểm tra an toàn bổ sung nếu không có cursor lock
    if cursor is None:
        while VehicleEntryExitLog.objects.filter(session_code=candidate_code).exists():
            next_seq += 1
            candidate_code = f"{prefix}{next_seq:03d}"

    return candidate_code
