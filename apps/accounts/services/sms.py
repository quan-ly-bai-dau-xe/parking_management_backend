"""
SMS Service and Provider Backends for Parking Management Backend.
Provides pluggable SMS dispatching for OTP, notifications, and security alerts.
Supports Console/Logger output for development and in-memory outbox for testing.
"""

from __future__ import annotations

import abc
import contextlib
import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


def normalize_vietnamese_phone(phone: Any) -> str:
    """
    Chuẩn hóa số điện thoại Việt Nam theo quy chuẩn quốc tế và Schema v2:
    - Loại bỏ dấu cách, dấu chấm, dấu gạch ngang, dấu ngoặc.
    - Chuyển đầu số quốc tế '+84' hoặc '84' thành '0'.
    - Kiểm tra độ dài hợp lệ (9-15 chữ số theo constraint ck_*_phone_digits).
    """
    if not phone or not isinstance(phone, str):
        return ""
    clean = re.sub(r"[\s.\-()]+", "", phone.strip())
    if clean.startswith("+84"):
        clean = "0" + clean[3:]
    elif clean.startswith("84") and len(clean) >= 11:
        clean = "0" + clean[2:]
    return clean


def is_valid_phone_number(phone: str) -> bool:
    """
    Kiểm tra tính hợp lệ của số điện thoại:
    - Bắt đầu bằng 0 và tiếp theo là đầu số di động phổ biến tại VN (3, 5, 7, 8, 9)
    - Hoặc chuỗi 9 đến 15 chữ số hợp chuẩn database.
    """
    clean = normalize_vietnamese_phone(phone)
    if not clean:
        return False
    return bool(re.match(r"^(0[35789][0-9]{8}|[0-9]{9,15})$", clean))


class BaseSMSBackend(abc.ABC):
    """Lớp cơ sở trừu tượng cho tất cả các SMS provider."""

    @abc.abstractmethod
    def send_sms(self, phone: str, message: str) -> bool:
        """Gửi tin nhắn SMS đến số điện thoại chỉ định."""
        pass


class ConsoleSMSBackend(BaseSMSBackend):
    """
    Backend in SMS ra console và ghi log.
    Sử dụng cho môi trường development và staging mà không tốn chi phí SMS thực tế.
    """

    def send_sms(self, phone: str, message: str) -> bool:
        clean_phone = normalize_vietnamese_phone(phone)
        logger.info(
            "[SMS DISPATCH] To: %s | Message: %s",
            clean_phone,
            message,
        )
        safe_msg = message
        try:
            print("\n==================== [SMS CONSOLE] ====================")
            print(f"To:      {clean_phone}")
            print(f"Message: {safe_msg}")
            print("=======================================================\n")
        except UnicodeEncodeError:
            safe_msg = message.encode("ascii", errors="replace").decode("ascii")
            print(f"Message: {safe_msg}")
            print("=======================================================\n")
        return True


class MockSMSBackend(BaseSMSBackend):
    """
    Backend lưu tin nhắn SMS vào danh sách outbox trong bộ nhớ.
    Phục vụ cho việc kiểm thử tự động (automated tests).
    """

    outbox: list[dict[str, str]] = []

    def send_sms(self, phone: str, message: str) -> bool:
        clean_phone = normalize_vietnamese_phone(phone)
        self.outbox.append(
            {
                "phone": clean_phone,
                "message": message,
            }
        )
        return True

    @classmethod
    def reset(cls) -> None:
        """Xóa toàn bộ tin nhắn trong outbox."""
        cls.outbox.clear()


class VonageSMSBackend(BaseSMSBackend):
    """
    Backend gửi SMS thực tế qua Vonage (Nexmo) SMS REST API.
    Docs: https://developer.vonage.com/en/messages/concepts/sms
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        from_sender: str | None = None,
    ):
        self.api_key = api_key if api_key is not None else settings.VONAGE_API_KEY
        self.api_secret = (
            api_secret if api_secret is not None else settings.VONAGE_API_SECRET
        )
        self.from_sender = (
            from_sender if from_sender is not None else settings.VONAGE_FROM
        )

    def format_international_phone(self, phone: str) -> str:
        """
        Chuyển đổi số điện thoại Việt Nam sang định dạng E.164 (bỏ dấu +)
        Ví dụ: 0766709535 -> 84766709535
        """
        clean = normalize_vietnamese_phone(phone)
        if clean.startswith("0"):
            return "84" + clean[1:]
        if clean.startswith("+84"):
            return clean[1:]
        if clean.startswith("84"):
            return clean
        return clean

    def send_sms(self, phone: str, message: str) -> bool:
        if not self.api_key or not self.api_secret:
            logger.error(
                "[VONAGE SMS] Thiếu VONAGE_API_KEY hoặc VONAGE_API_SECRET trong cấu hình."
            )
            return False

        to_phone = self.format_international_phone(phone)
        url = "https://rest.nexmo.com/sms/json"
        payload_data = json.dumps(
            {
                "api_key": self.api_key,
                "api_secret": self.api_secret,
                "to": to_phone,
                "from": self.from_sender,
                "text": message,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                resp_text = response.read().decode("utf-8")
                data = json.loads(resp_text)
            messages = data.get("messages", [])
            if not messages:
                logger.error(
                    "[VONAGE SMS] Không có dữ liệu tin nhắn trả về từ Vonage: %s",
                    data,
                )
                return False

            first_msg = messages[0]
            status = str(first_msg.get("status", ""))
            if status == "0":
                msg_id = first_msg.get("message-id")
                logger.info(
                    "[VONAGE SMS SUCCESS] Đã gửi tin nhắn đến %s thành công. Message ID: %s",
                    to_phone,
                    msg_id,
                )
                with contextlib.suppress(Exception):
                    print(
                        f"\n[VONAGE SMS SUCCESS] Đã gửi tin nhắn thực tế tới {to_phone} qua Vonage! (Message ID: {msg_id})"
                    )
                return True
            else:
                err_text = first_msg.get(
                    "error-text", f"Lỗi không xác định (mã lỗi: {status})"
                )
                logger.error(
                    "[VONAGE SMS ERROR] Gửi tin nhắn thất bại tới %s: %s (Status: %s)",
                    to_phone,
                    err_text,
                    status,
                )
                with contextlib.suppress(Exception):
                    print(
                        f"\n[VONAGE SMS ERROR] Vonage trả về lỗi khi gửi tới {to_phone}: {err_text} (Code: {status})"
                    )
                return False
        except Exception as exc:
            logger.exception(
                "[VONAGE SMS EXCEPTION] Lỗi kết nối tới Vonage API: %s", exc
            )
            with contextlib.suppress(Exception):
                print(
                    f"\n[VONAGE SMS EXCEPTION] Không thể kết nối tới Vonage API: {exc}"
                )
            return False


def get_sms_backend() -> BaseSMSBackend:
    """Khởi tạo instance của SMS Backend dựa trên cấu hình SMS_BACKEND trong settings."""
    backend_path = settings.SMS_BACKEND
    backend_cls = import_string(backend_path)
    return backend_cls()


def send_sms(phone: str, message: str) -> bool:
    """
    Hàm tiện ích gửi SMS qua backend được cấu hình.
    Trả về True nếu gửi thành công.
    """
    backend = get_sms_backend()
    return backend.send_sms(phone, message)
