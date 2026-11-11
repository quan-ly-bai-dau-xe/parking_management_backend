"""
Firebase SMS OTP Verification Service.
Integrates Firebase Phone Authentication REST API (Identity Toolkit v1)
for User Registration and Forgot Password flows per SRS specifications.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from django.conf import settings
import requests

logger = logging.getLogger(__name__)

# Search candidates for firebase_config.json
SEARCH_PATHS = [
    os.path.join(settings.BASE_DIR, "firebase_config.json"),
    os.path.join(os.path.dirname(settings.BASE_DIR), "firebase_config.json"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_config.json"),
]


def load_firebase_config() -> dict[str, Any]:
    """
    Đọc cấu hình Firebase từ file firebase_config.json hoặc environment variables.
    """
    config: dict[str, Any] = {}

    for path in SEARCH_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    if config.get("apiKey") and "YOUR_FIREBASE" not in config.get("apiKey", ""):
                        return config
            except Exception as e:
                logger.warning("Không thể đọc file cấu hình %s: %s", path, e)

    # Fallback to Django settings or environment variables
    api_key = getattr(settings, "FIREBASE_API_KEY", "") or os.environ.get("FIREBASE_API_KEY", "") or os.environ.get("VITE_FIREBASE_API_KEY", "")
    project_id = getattr(settings, "FIREBASE_PROJECT_ID", "") or os.environ.get("FIREBASE_PROJECT_ID", "") or os.environ.get("VITE_FIREBASE_PROJECT_ID", "")

    if api_key and "YOUR_FIREBASE" not in api_key:
        config["apiKey"] = api_key
    if project_id:
        config["projectId"] = project_id

    return config


def is_firebase_configured() -> bool:
    """Kiểm tra Firebase đã được cấu hình với API Key thực tế chưa."""
    config = load_firebase_config()
    api_key = config.get("apiKey", "")
    return bool(api_key and "YOUR_FIREBASE" not in api_key and len(api_key) > 10)


def format_phone_number(phone: str) -> str:
    """
    Định dạng số điện thoại về chuẩn quốc tế E.164 (VD: 0766709535 -> +84766709535).
    """
    if not phone:
        return ""
    clean = str(phone).strip().replace(" ", "").replace("-", "").replace(".", "").replace("(", "").replace(")", "")
    if clean.startswith("+84"):
        return clean
    if clean.startswith("84"):
        return "+" + clean
    if clean.startswith("0"):
        return "+84" + clean[1:]
    if not clean.startswith("+"):
        return "+84" + clean
    return clean


def mask_phone_number(phone: str) -> str:
    """
    Che giấu số điện thoại để log hoặc thông báo an toàn theo chuẩn bảo mật PII / CodeQL.
    VD: +84766709535 -> +84***35
    """
    if not phone or len(phone) <= 5:
        return "***"
    return f"{phone[:3]}***{phone[-2:]}"


def send_sms_otp(phone_number: str, recaptcha_token: str | None = None) -> dict[str, Any]:
    """
    Gửi mã xác thực OTP qua Firebase Phone Authentication REST API.
    
    :param phone_number: Số điện thoại người nhận (VD: '+84766709535' hoặc '0766709535')
    :param recaptcha_token: Token reCAPTCHA (tùy chọn)
    :return: dict chứa 'phoneNumber', 'sessionInfo', 'isMock', 'testOtp'
    """
    phone_e164 = format_phone_number(phone_number)
    masked_phone = mask_phone_number(phone_e164)
    config = load_firebase_config()
    api_key = config.get("apiKey")

    # Nếu chưa có cấu hình Firebase thật: Chạy chế độ test/fallback
    if not api_key or "YOUR_FIREBASE" in api_key:
        logger.info(
            "[Firebase OTP Dev Mode] Chưa cấu hình API Key. Tạo phiên OTP thử nghiệm cho %s",
            masked_phone,
        )
        mock_session = f"mock_session_{phone_e164.replace('+', '')}_{os.urandom(8).hex()}"
        print("\n==================== [FIREBASE OTP TEST] ====================")
        print(f"Số điện thoại: {masked_phone}")
        print("Mã OTP thử nghiệm: 123456")
        print("Session Info: [REDACTED]")
        print("=============================================================\n")
        return {
            "phoneNumber": phone_e164,
            "sessionInfo": mock_session,
            "isMock": True,
            "testOtp": "123456",
        }

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key={api_key}"
    payload: dict[str, Any] = {"phoneNumber": phone_e164}
    if recaptcha_token:
        payload["recaptchaToken"] = recaptcha_token

    try:
        resp = requests.post(url, json=payload, timeout=20)
        data = resp.json()
    except Exception as exc:
        logger.error("[Firebase OTP Connection Error] %s", exc)
        raise RuntimeError(f"Không thể kết nối tới Firebase: {exc}") from exc

    if not resp.ok:
        err = data.get("error", {})
        err_msg = err.get("message", resp.text)

        if "MISSING_RECAPTCHA_TOKEN" in err_msg:
            raise RuntimeError(
                f"Firebase yêu cầu xác thực reCAPTCHA cho số {masked_phone}.\n"
                "Gợi ý: Thêm số vào 'Phone numbers for testing' trên Firebase Console để test miễn phí."
            )
        if "INVALID_PHONE_NUMBER" in err_msg:
            raise RuntimeError(f"Số điện thoại không hợp lệ: {masked_phone}")
        if "TOO_MANY_ATTEMPTS_TRY_LATER" in err_msg:
            raise RuntimeError("Đã gửi quá nhiều yêu cầu trong thời gian ngắn. Vui lòng thử lại sau!")
        raise RuntimeError(f"Lỗi Firebase ({resp.status_code}): {err_msg}")

    return {
        "phoneNumber": phone_e164,
        "sessionInfo": data.get("sessionInfo"),
        "isMock": False,
    }


def verify_sms_otp(session_info: str, otp_code: str) -> dict[str, Any]:
    """
    Xác minh mã OTP mà người dùng nhập vào thông qua Firebase Identity Toolkit REST API.
    
    :param session_info: Chuỗi sessionInfo nhận được từ send_sms_otp
    :param otp_code: Mã OTP 6 chữ số
    :return: dict thông tin người dùng xác thực (uid, phoneNumber, idToken, status)
    """
    clean_code = str(otp_code).strip()
    config = load_firebase_config()
    api_key = config.get("apiKey")

    # Kiểm tra phiên test/mock
    if not api_key or "YOUR_FIREBASE" in api_key or (session_info and session_info.startswith("mock_session_")):
        if clean_code in ("123456", "000000"):
            return {
                "status": "success",
                "uid": f"mock_uid_{os.urandom(6).hex()}",
                "phoneNumber": session_info.split("_")[2] if "_" in session_info else "+84900000000",
                "isMock": True,
            }
        raise RuntimeError("Mã OTP thử nghiệm không chính xác (mặc định: 123456).")

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPhoneNumber?key={api_key}"
    payload = {
        "sessionInfo": session_info,
        "code": clean_code,
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
        data = resp.json()
    except Exception as exc:
        logger.error("[Firebase OTP Verify Connection Error] %s", exc)
        raise RuntimeError(f"Lỗi kết nối xác minh Firebase: {exc}") from exc

    if not resp.ok:
        err = data.get("error", {})
        err_msg = err.get("message", resp.text)
        if "INVALID_CODE" in err_msg:
            raise RuntimeError("Mã OTP không chính xác. Vui lòng kiểm tra lại!")
        if "SESSION_EXPIRED" in err_msg:
            raise RuntimeError("Mã OTP hoặc phiên làm việc đã hết hạn. Vui lòng gửi lại mã mới!")
        raise RuntimeError(f"Lỗi xác minh OTP ({resp.status_code}): {err_msg}")

    return {
        "status": "success",
        "uid": data.get("localId"),
        "phoneNumber": data.get("phoneNumber"),
        "idToken": data.get("idToken"),
        "refreshToken": data.get("refreshToken"),
        "isMock": False,
    }

