"""
Core Auth & Endpoints Test Suite per SRS 4.1, ADR-0004, and TL-52.
"""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import (
    Account,
    PasswordResetToken,
    PersistentLoginToken,
)
from apps.accounts.selectors.auth import (
    get_account_by_identifier,
    get_active_account_by_identifier,
)
from apps.accounts.serializers.auth import LoginSerializer
from apps.accounts.services.auth import (
    check_password_anti_timing,
    get_dummy_password_hash,
    login_account,
)
from apps.core.messages import PROPOSAL_MESSAGES, SRS_MESSAGES


class CoreAuthSettingsTest(TestCase):
    """Kiểm tra cấu hình bảo mật mật khẩu, CORS và CSRF per F03, F04."""

    def test_base_settings_hasher_order(self):
        """Khẳng định Argon2PasswordHasher đứng đầu trong config.settings.base per TL-52 và Rule 07."""
        from config.settings import base as base_settings

        self.assertGreaterEqual(len(base_settings.PASSWORD_HASHERS), 1)
        self.assertEqual(
            base_settings.PASSWORD_HASHERS[0],
            "django.contrib.auth.hashers.Argon2PasswordHasher",
        )

    def test_cors_middleware_and_apps_wired(self):
        """Khẳng định corsheaders được khai báo trong INSTALLED_APPS và MIDDLEWARE per TL-52 và Rule 07."""
        from config.settings import base as base_settings

        self.assertIn("corsheaders", base_settings.INSTALLED_APPS)
        self.assertIn("corsheaders.middleware.CorsMiddleware", base_settings.MIDDLEWARE)

        # CorsMiddleware phải đứng trước CommonMiddleware
        cors_idx = base_settings.MIDDLEWARE.index(
            "corsheaders.middleware.CorsMiddleware"
        )
        common_idx = base_settings.MIDDLEWARE.index(
            "django.middleware.common.CommonMiddleware"
        )
        self.assertLess(cors_idx, common_idx)

    def test_cors_and_csrf_security_flags(self):
        """Khẳng định các cờ an ninh CORS, CSRF và Session tuân thủ Rule 07."""
        from config.settings import base as base_settings

        self.assertFalse(base_settings.CORS_ALLOW_ALL_ORIGINS)
        self.assertTrue(base_settings.CORS_ALLOW_CREDENTIALS)
        self.assertFalse(base_settings.CSRF_COOKIE_HTTPONLY)
        self.assertTrue(base_settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(base_settings.SESSION_COOKIE_SAMESITE, "Lax")

    def test_cors_preflight_allowed_origin_returns_headers(self):
        """
        OPTIONS preflight từ allowed origin trả về đầy đủ headers CORS per TL-53.
        """
        with self.settings(
            CORS_ALLOWED_ORIGINS=["http://localhost:3000"], CORS_ALLOW_CREDENTIALS=True
        ):
            client = Client()
            response = client.options(
                reverse("auth-login"),
                HTTP_ORIGIN="http://localhost:3000",
                HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
                HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-csrftoken",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Origin"),
                "http://localhost:3000",
            )
            self.assertEqual(
                response.headers.get("Access-Control-Allow-Credentials"), "true"
            )
            self.assertIn(
                "x-csrftoken",
                response.headers.get("Access-Control-Allow-Headers", "").lower(),
            )

    def test_cors_preflight_disallowed_origin_returns_no_allow_origin(self):
        """
        OPTIONS preflight từ disallowed origin không có header Access-Control-Allow-Origin per TL-53.
        """
        with self.settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"]):
            client = Client()
            response = client.options(
                reverse("auth-login"),
                HTTP_ORIGIN="http://untrusted-attacker.com",
                HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            )
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_cors_simple_request_disallowed_origin_returns_no_allow_origin(self):
        """
        Simple GET request từ disallowed origin không có header Access-Control-Allow-Origin per TL-53.
        """
        with self.settings(CORS_ALLOWED_ORIGINS=["http://localhost:3000"]):
            client = Client()
            response = client.get(
                reverse("auth-csrf"),
                HTTP_ORIGIN="http://untrusted-attacker.com",
            )
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_admin_login_without_csrf_returns_html_403(self) -> None:
        """
        CSRF failure on Django admin login delegates to Django default HTML view.
        """
        client = Client(enforce_csrf_checks=True)
        response = client.post("/admin/login/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        content_type = response.headers.get("Content-Type", "")
        self.assertTrue(
            content_type.startswith("text/html"),
            f"Kỳ vọng Content-Type text/html nhưng nhận được {content_type}",
        )

    def test_accounts_settings_exist_with_expected_types(self) -> None:
        """
        Verify that 10 named settings required by the accounts application
        exist on django.conf.settings with expected types and default values.
        """
        from django.conf import settings

        expected_settings: dict[str, tuple[type, object]] = {
            "REMEMBER_COOKIE_NAME": (str, "parking_remember_token"),
            "REMEMBER_ROTATION_GRACE_SECONDS": (int, 30),
            "REMEMBER_TOKEN_LIFETIME_DAYS": (int, 30),
            "REMEMBER_MAX_TOKENS_PER_ACCOUNT": (int, 10),
            "AUTH_THROTTLE_PAIR_LIMIT": (int, 5),
            "AUTH_THROTTLE_IDENTIFIER_LIMIT": (int, 20),
            "AUTH_THROTTLE_IP_LIMIT": (int, 30),
            "AUTH_THROTTLE_WINDOW_SECONDS": (int, 900),
            "NUM_PROXIES": (int, 0),
            "SESSION_COOKIE_AGE": (int, 43200),
        }

        for setting_name, (
            expected_type,
            expected_default,
        ) in expected_settings.items():
            self.assertTrue(
                hasattr(settings, setting_name),
                f"Setting {setting_name} không tồn tại trên django.conf.settings",
            )
            value = getattr(settings, setting_name)
            self.assertIsInstance(
                value,
                expected_type,
                f"Setting {setting_name} có kiểu {type(value).__name__}, kỳ vọng {expected_type.__name__}",
            )
            self.assertEqual(
                value,
                expected_default,
                f"Setting {setting_name} có giá trị {value!r}, kỳ vọng {expected_default!r}",
            )

    def test_no_getattr_settings_with_defaults_in_accounts(self) -> None:
        """
        Static scan verifying that apps/accounts contains no getattr calls on settings,
        ensuring all default values reside strictly in config/settings/base.py.
        """
        import ast
        from pathlib import Path

        from django.conf import settings

        accounts_dir = Path(settings.BASE_DIR) / "apps" / "accounts"
        violations = []

        for py_path in sorted(accounts_dir.rglob("*.py")):
            tree = ast.parse(py_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "settings"
                ):
                    arg_name = (
                        node.args[1].value
                        if isinstance(node.args[1], ast.Constant)
                        else "unknown"
                    )
                    violations.append(
                        f"{py_path.name}:{node.lineno} -> getattr(settings, {arg_name!r})"
                    )

        self.assertEqual(
            violations,
            [],
            f"Phát hiện getattr(settings, ...) vi phạm tại: {violations}",
        )


class CSRFBootstrapEndpointTest(TestCase):
    """Kiểm tra endpoint GET /api/v1/auth/csrf/ per F06, TL-52, ADR-0004."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("auth-csrf")

    def test_csrf_bootstrap_sets_cookie_and_returns_200(self):
        """GET csrf/ thiết lập cookie csrftoken và trả về 200 OK kèm envelope."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {"detail": "Khởi tạo cookie CSRF thành công."},
        )
        self.assertIn("csrftoken", response.cookies)

    def test_csrf_bootstrap_returns_vietnamese_catalog_message(self):
        """
        GET csrf/ trả về thông điệp tiếng Việt từ catalog PROP-4.1-P02 per TL-53.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json().get("detail"),
            "Khởi tạo cookie CSRF thành công.",
        )


class LoginEndpointTest(TestCase):
    """Kiểm tra endpoint POST /api/v1/auth/login/ per F07, F08, TL-52, ADR-0004."""

    def setUp(self):
        # enforce_csrf_checks=False is explicitly justified here to isolate authentication credentials,
        # account roles, and response payload validation from CSRF middleware protection.
        # End-to-end CSRF compliance is tested independently with enforce_csrf_checks=True below.
        self.client = Client(enforce_csrf_checks=False)
        self.url = reverse("auth-login")
        self.password = "StrongPass123!"

        # Tạo tài khoản thử nghiệm cho 3 vai trò
        self.mgr_account = Account.objects.create_user(
            email="manager@parking.com",
            phone="0911223344",
            password=self.password,
            role="MANAGER",
        )
        self.emp_account = Account.objects.create_user(
            email="employee@parking.com",
            phone="0922334455",
            password=self.password,
            role="EMPLOYEE",
        )
        self.cust_account = Account.objects.create_user(
            email="customer@parking.com",
            phone="0933445566",
            password=self.password,
            role="CUSTOMER",
        )

        # Tài khoản không hoạt động
        self.inactive_account = Account.objects.create_user(
            email="inactive@parking.com",
            phone="0944556677",
            password=self.password,
            role="EMPLOYEE",
            is_active=False,
        )

    def test_login_success_by_email_case_insensitive(self):
        """Đăng nhập thành công bằng email không phân biệt chữ hoa/chữ thường (TL-21)."""
        # Thử với chữ hoa hỗn hợp
        payload = {
            "identifier": "MaNaGeR@parking.com",
            "password": self.password,
            "remember": False,
        }
        response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], self.mgr_account.id)
        self.assertEqual(data["email"], "manager@parking.com")
        self.assertEqual(data["role"], "MANAGER")

        # Session cookie phải được thiết lập
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)

        # Không chọn remember -> không có cookie remember
        self.assertNotIn("parking_remember_token", response.cookies)

        # last_login phải được cập nhật
        self.mgr_account.refresh_from_db()
        self.assertIsNotNone(self.mgr_account.last_login)

    def test_login_success_by_phone_with_formatting_separators(self):
        """Đăng nhập thành công bằng số điện thoại có dấu phân cách (dấu cách, chấm, gạch ngang)."""
        payload = {
            "identifier": "0922-334.455",
            "password": self.password,
            "remember": False,
        }
        response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], self.emp_account.id)
        self.assertEqual(data["phone"], "0922334455")
        self.assertEqual(data["role"], "EMPLOYEE")

    def test_login_with_remember_me_issues_token_and_cookie(self):
        """Đăng nhập với remember=True phát hành cookie và lưu token vào DB (ADR-0004)."""
        payload = {
            "identifier": "customer@parking.com",
            "password": self.password,
            "remember": True,
        }
        response = self.client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Cookie parking_remember_token phải có
        self.assertIn("parking_remember_token", response.cookies)
        cookie = response.cookies["parking_remember_token"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

        # Kiểm tra token trong cơ sở dữ liệu
        val = cookie.value
        self.assertIn(":", val)
        series, raw_token = val.split(":", 1)

        token_row = PersistentLoginToken.objects.filter(series=series).first()
        self.assertIsNotNone(token_row)
        self.assertEqual(token_row.account_id, self.cust_account.id)
        # Token thô tuyệt đối không được lưu trong DB, chỉ lưu hash
        self.assertNotEqual(token_row.token_hash, raw_token)

    def test_empty_or_whitespace_payload_returns_400_msg_m03(self):
        """Mọi tổ hợp trống, khoảng trắng, thiếu trường đều trả về 400 với MSG-4.1-M03."""
        expected_msg = SRS_MESSAGES["MSG-4.1-M03"]
        invalid_payloads = [
            {},  # Thiếu cả hai
            {"identifier": ""},  # Trống identifier
            {"identifier": "   ", "password": self.password},  # Khoảng trắng
            {"identifier": "manager@parking.com", "password": ""},  # Trống password
            {
                "identifier": "manager@parking.com",
                "password": "   ",
            },  # Password chỉ có khoảng trắng
            {"identifier": None, "password": self.password},  # None
            {"identifier": 123456, "password": self.password},  # Sai kiểu
            {"identifier": "manager@parking.com", "password": 12345},  # Sai kiểu
        ]

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                res = self.client.post(
                    self.url, payload, content_type="application/json"
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                data = res.json()
                self.assertEqual(data["code"], "MSG-4.1-M03")
                self.assertEqual(data["message"], expected_msg)

    def test_auth_failures_return_uniform_401_msg_m02(self):
        """
        Tài khoản không tồn tại, sai mật khẩu, tài khoản vô hiệu hóa đều trả về
        phản hồi HTTP 401 đồng nhất từng byte với MSG-4.1-M02 (chống enumeration).
        """
        expected_msg = SRS_MESSAGES["MSG-4.1-M02"]
        failure_cases = [
            {
                "identifier": "unknown@parking.com",
                "password": "AnyPassword123!",
            },  # Không tồn tại
            {
                "identifier": "manager@parking.com",
                "password": "WrongPassword!",
            },  # Sai mật khẩu
            {
                "identifier": "inactive@parking.com",
                "password": self.password,
            },  # Bị vô hiệu hóa
            {
                "identifier": "invalid_phone_letters_abc",
                "password": self.password,
            },  # Identifier sai cú pháp
        ]

        responses = []
        for case in failure_cases:
            with self.subTest(case=case):
                res = self.client.post(self.url, case, content_type="application/json")
                self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
                data = res.json()
                self.assertEqual(data["code"], "MSG-4.1-M02")
                self.assertEqual(data["message"], expected_msg)
                self.assertEqual(data["details"], {})
                responses.append(res.content)

        # Khẳng định thân phản hồi giống hệt nhau từng byte
        for resp_content in responses[1:]:
            self.assertEqual(resp_content, responses[0])

    def test_response_never_exposes_sensitive_data(self):
        """Phản hồi thành công tuyệt đối không chứa password, hash hay raw token."""
        payload = {
            "identifier": "manager@parking.com",
            "password": self.password,
            "remember": True,
        }
        response = self.client.post(self.url, payload, content_type="application/json")
        body_str = response.content.decode("utf-8").lower()
        self.assertNotIn("password", body_str)
        self.assertNotIn("hash", body_str)
        self.assertNotIn("token_hash", body_str)

    def test_login_without_csrf_header_rejected_with_403_json_envelope(self):
        """
        Login request không có CSRF header phải bị từ chối với HTTP 403 per TL-53
        và trả về JSON error envelope PROP-4.1-P06.
        """
        client = Client(enforce_csrf_checks=True)
        payload = {
            "identifier": self.mgr_account.email,
            "password": self.password,
            "remember": False,
        }
        response = client.post(self.url, payload, content_type="application/json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(
            response.headers.get("Content-Type", "").startswith("application/json")
        )
        data = response.json()
        self.assertEqual(data.get("code"), "PROP-4.1-P06")
        self.assertIn("details", data)

    def test_login_with_invalid_csrf_header_rejected_with_403_json_envelope(self):
        """
        Login request với token CSRF sai lệch phải trả về HTTP 403 JSON envelope per TL-53.
        """
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("auth-csrf"))
        payload = {
            "identifier": self.mgr_account.email,
            "password": self.password,
            "remember": False,
        }
        response = client.post(
            self.url,
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN="invalid_forged_csrf_token_value",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json().get("code"), "PROP-4.1-P06")

    def test_login_with_matching_csrf_cookie_and_header_succeeds_200(self):
        """
        POST login gửi kèm cookie và header X-CSRFToken hợp lệ per TL-53
        với enforce_csrf_checks=True phải được xác thực thành công và trả về HTTP 200 OK.
        """
        client = Client(enforce_csrf_checks=True)
        csrf_response = client.get(reverse("auth-csrf"))
        self.assertEqual(csrf_response.status_code, status.HTTP_200_OK)
        csrf_token = csrf_response.cookies["csrftoken"].value

        payload = {
            "identifier": self.mgr_account.email,
            "password": self.password,
            "remember": False,
        }
        response = client.post(
            self.url,
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["id"], self.mgr_account.id)

    def test_login_session_cookie_has_no_max_age_and_no_expires_for_both_remember_values(
        self,
    ):
        """
        Session cookie không được chứa Max-Age hoặc Expires (browser-session cookie)
        cho cả hai trường hợp remember=False và remember=True per ADR-0004 và TL-53.
        """
        # enforce_csrf_checks=False is explicitly justified here to isolate session cookie lifetime
        # and attributes verification from CSRF validation.
        client = Client(enforce_csrf_checks=False)
        payload_false = {
            "identifier": self.mgr_account.email,
            "password": self.password,
            "remember": False,
        }
        res_false = client.post(
            self.url,
            payload_false,
            content_type="application/json",
        )
        self.assertEqual(res_false.status_code, status.HTTP_200_OK)
        session_cookie_false = res_false.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(
            session_cookie_false.get("max-age"),
            "",
            "Session cookie must not have Max-Age",
        )
        self.assertEqual(
            session_cookie_false.get("expires"),
            "",
            "Session cookie must not have Expires",
        )

        client.logout()
        res_true = client.post(
            self.url,
            {**payload_false, "remember": True},
            content_type="application/json",
        )
        self.assertEqual(res_true.status_code, status.HTTP_200_OK)
        session_cookie_true = res_true.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(
            session_cookie_true.get("max-age"),
            "",
            "Session cookie must not have Max-Age when remember=True",
        )
        self.assertEqual(
            session_cookie_true.get("expires"),
            "",
            "Session cookie must not have Expires when remember=True",
        )

    def test_session_rejected_when_older_than_session_cookie_age_setting(self):
        """
        Phiên làm việc quá 12 giờ mặc định của SESSION_COOKIE_AGE per TL-53
        phải bị từ chối 401 khi kiểm tra với injected clock.
        """
        # enforce_csrf_checks=False is explicitly justified here to isolate server-side session
        # expiration verification across injected time offsets from CSRF validation.
        client = Client(enforce_csrf_checks=False)
        payload = {
            "identifier": self.emp_account.email,
            "password": self.password,
            "remember": False,
        }
        res = client.post(self.url, payload, content_type="application/json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Trước khi hết hạn (trong vòng 12h) -> Thành công
        res_valid = client.get(reverse("auth-me"))
        self.assertEqual(res_valid.status_code, status.HTTP_200_OK)

        # Sau 13 giờ (vượt quá 12 giờ) -> Bị từ chối 401
        future_time = timezone.now() + timedelta(hours=13)
        with patch("django.utils.timezone.now", return_value=future_time):
            res_expired = client.get(reverse("auth-me"))
            self.assertEqual(res_expired.status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutEndpointTest(TestCase):
    """Kiểm tra endpoint POST /api/v1/auth/logout/ per F09, TL-52, ADR-0004."""

    def setUp(self):
        # enforce_csrf_checks=False is explicitly justified here to isolate session flushing and
        # token purging behavior from CSRF checks. CSRF rejection and compliance are tested
        # independently with enforce_csrf_checks=True in dedicated test methods below.
        self.client = Client(enforce_csrf_checks=False)
        self.login_url = reverse("auth-login")
        self.logout_url = reverse("auth-logout")
        self.password = "StrongPass123!"

        self.account = Account.objects.create_user(
            email="logout_test@parking.com",
            password=self.password,
            role="EMPLOYEE",
        )

    def test_logout_flushes_session_and_clears_remember_token(self):
        """Đăng xuất hủy session, xóa cookie và thu hồi token trong database."""
        # 1. Đăng nhập trước
        login_res = self.client.post(
            self.login_url,
            {
                "identifier": "logout_test@parking.com",
                "password": self.password,
                "remember": True,
            },
            content_type="application/json",
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)
        remember_cookie = login_res.cookies["parking_remember_token"].value
        series = remember_cookie.split(":", 1)[0]
        self.assertTrue(PersistentLoginToken.objects.filter(series=series).exists())

        # 2. Gọi đăng xuất
        logout_res = self.client.post(self.logout_url)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)
        self.assertEqual(logout_res.json(), {"detail": "Đăng xuất thành công."})

        # Cookie phải bị xóa (max-age=0 hoặc expires trong quá khứ)
        self.assertEqual(logout_res.cookies["parking_remember_token"]["max-age"], 0)

        # Dòng token trong DB phải bị xóa
        self.assertFalse(PersistentLoginToken.objects.filter(series=series).exists())

    def test_logout_is_idempotent_for_anonymous_user(self):
        """Người dùng chưa đăng nhập gọi logout vẫn an toàn và trả về 200 OK."""
        res = self.client.post(self.logout_url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json(), {"detail": "Đăng xuất thành công."})

    def test_logout_without_csrf_header_rejected_with_403(self):
        """
        Logout request không có CSRF header phải bị từ chối với HTTP 403 per TL-53.
        """
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json().get("code"), "PROP-4.1-P06")

    def test_logout_with_invalid_csrf_header_rejected_with_403(self):
        """
        Logout request với token CSRF sai lệch với enforce_csrf_checks=True per TL-53
        phải bị từ chối với HTTP 403 và trả về JSON error envelope PROP-4.1-P06.
        """
        client = Client(enforce_csrf_checks=True)
        client.get(reverse("auth-csrf"))
        response = client.post(
            self.logout_url,
            HTTP_X_CSRFTOKEN="invalid_forged_csrf_token_value",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json().get("code"), "PROP-4.1-P06")

    def test_logout_with_matching_csrf_cookie_and_header_succeeds_200(self):
        """
        POST logout gửi kèm cookie và header X-CSRFToken hợp lệ per TL-53
        với enforce_csrf_checks=True phải đăng xuất thành công và trả về HTTP 200 OK.
        """
        client = Client(enforce_csrf_checks=True)
        csrf_response = client.get(reverse("auth-csrf"))
        self.assertEqual(csrf_response.status_code, status.HTTP_200_OK)
        csrf_token = csrf_response.cookies["csrftoken"].value

        response = client.post(
            self.logout_url,
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json().get("detail"),
            "Đăng xuất thành công.",
        )

    def test_logout_returns_vietnamese_catalog_message(self):
        """
        Logout thành công phải trả về thông điệp tiếng Việt từ catalog PROP-4.1-P03 per TL-53.
        """
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json().get("detail"),
            "Đăng xuất thành công.",
        )


class CurrentUserEndpointTest(TestCase):
    """Kiểm tra endpoint GET /api/v1/auth/me/ per F10, TL-52, ADR-0004."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("auth-me")
        self.password = "StrongPass123!"

        self.account = Account.objects.create_user(
            email="me_user@parking.com",
            phone="0955667788",
            password=self.password,
            role="EMPLOYEE",
        )

    def test_me_unauthenticated_returns_401_msg_m02(self):
        """Yêu cầu chưa xác thực trả về 401 với MSG-4.1-M02."""
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        data = res.json()
        self.assertEqual(data["code"], "MSG-4.1-M02")
        self.assertEqual(data["message"], SRS_MESSAGES["MSG-4.1-M02"])

    def test_unauthenticated_me_matches_standard_protected_endpoint_envelope(self):
        """
        /me/ unauthenticated phải trả về cùng cấu trúc envelope per TL-53
        với các protected endpoint khác (như /lookup/vehicles/).
        """
        res_me = self.client.get(self.url)
        res_parking = self.client.get("/api/v1/parking/vehicle-lookup/")
        self.assertEqual(res_me.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res_parking.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            res_me.json().get("details"), res_parking.json().get("details")
        )

    def test_me_authenticated_returns_user_profile(self):
        """Yêu cầu đã xác thực trả về 200 OK kèm thông tin tài khoản."""
        self.client.force_login(self.account)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["id"], self.account.id)
        self.assertEqual(data["email"], "me_user@parking.com")
        self.assertEqual(data["phone"], "0955667788")
        self.assertEqual(data["role"], "EMPLOYEE")


class SelectorsAndServicesTest(TestCase):
    """Kiểm tra logic unit cho selectors và services per F05, F08."""

    def setUp(self):
        self.account = Account.objects.create_user(
            email="selector_test@parking.com",
            phone="0988776655",
            password="StrongPassword123!",
            role="CUSTOMER",
        )

    def test_selectors_by_email_and_phone(self):
        """Tra cứu chính xác bằng email hoặc số điện thoại định dạng khác nhau."""
        by_email = get_active_account_by_identifier("SELECTOR_TEST@PARKING.COM")
        self.assertIsNotNone(by_email)
        self.assertEqual(by_email.id, self.account.id)

        by_phone = get_active_account_by_identifier("0988-776.655")
        self.assertIsNotNone(by_phone)
        self.assertEqual(by_phone.id, self.account.id)

        # Alias kiểm tra
        by_alias = get_account_by_identifier("0988776655")
        self.assertIsNotNone(by_alias)
        self.assertEqual(by_alias.id, self.account.id)

    def test_anti_timing_dummy_check_returns_false(self):
        """Hàm kiểm tra hash giả anti-timing luôn trả về False an toàn."""
        res = check_password_anti_timing("RandomPasswordTry123!")
        self.assertFalse(res)

    def test_login_serializer_run_validation_does_not_swallow_unexpected_exceptions(
        self,
    ):
        """
        LoginSerializer.run_validation không bắt blanket Exception per TL-53,
        các lỗi không mong muốn như TypeError không được bị bọc thành MSG-4.1-M03.
        """
        with patch(
            "rest_framework.serializers.Serializer.run_validation",
            side_effect=TypeError("Unexpected code bug"),
        ):
            serializer = LoginSerializer(
                data={"identifier": "test@parking.com", "password": "pwd"}
            )
            with self.assertRaises(TypeError):
                serializer.is_valid()

    def test_get_dummy_password_hash_does_not_swallow_runtime_error(self):
        """
        get_dummy_password_hash không bắt blanket Exception per TL-53,
        lỗi nghiêm trọng như RuntimeError không được bị nuốt.
        """
        with (
            patch(
                "apps.accounts.services.auth.get_hasher",
                side_effect=RuntimeError("Fatal hasher error"),
            ),
            self.assertRaises(RuntimeError),
        ):
            get_dummy_password_hash()

    def test_login_account_executes_single_account_update_query(self):
        """
        login_account chỉ thực thi đúng 1 câu UPDATE vào bảng account cho last_login per TL-53.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        req = self.client.request().wsgi_request
        with CaptureQueriesContext(connection) as ctx:
            login_account(req, self.account, remember=False)

        account_updates = [
            q["sql"]
            for q in ctx.captured_queries
            if "UPDATE" in q["sql"] and "account" in q["sql"].lower()
        ]
        self.assertEqual(len(account_updates), 1)

    def test_unused_prop_p04_not_in_message_catalog(self):
        """
        PROP-4.1-P04 không được API sử dụng nên không tồn tại trong message catalog per TL-53.
        """
        self.assertNotIn("PROP-4.1-P04", PROPOSAL_MESSAGES)

    def test_all_registered_prop_4_1_messages_used_in_apps(self) -> None:
        """Khẳng định mọi mã PROP-4.1-P## đăng ký trong messages.py đều được sử dụng trong apps/ per TL-53."""
        import re
        from pathlib import Path

        prop_pattern = re.compile(r"^PROP-4\.1-P\d+$")
        target_codes = {code for code in PROPOSAL_MESSAGES if prop_pattern.match(code)}

        apps_dir = Path(settings.BASE_DIR) / "apps"
        messages_path = (apps_dir / "core" / "messages.py").resolve()
        used_codes = set()

        for py_path in apps_dir.rglob("*.py"):
            if py_path.resolve() == messages_path:
                continue
            content = py_path.read_text(encoding="utf-8", errors="ignore")
            for code in target_codes:
                if code in content:
                    used_codes.add(code)

        unused_codes = target_codes - used_codes
        self.assertEqual(
            unused_codes,
            set(),
            f"Các mã PROP-4.1-P## sau đã đăng ký nhưng không được dùng trong apps/: {sorted(unused_codes)}",
        )

    def test_normalize_login_identifier_edge_cases(self) -> None:
        """
        Test các nhánh biên của normalize_login_identifier và get_active_account_by_identifier.
        """
        from apps.accounts.selectors.auth import (
            get_active_account_by_identifier,
            normalize_login_identifier,
        )

        self.assertEqual(normalize_login_identifier(None), "")
        self.assertEqual(normalize_login_identifier(""), "")
        self.assertEqual(normalize_login_identifier("   "), "")
        self.assertEqual(normalize_login_identifier(12345), "")
        self.assertIsNone(get_active_account_by_identifier(None))

        self.assertIsNone(get_active_account_by_identifier(""))
        self.assertIsNone(
            get_active_account_by_identifier("nonexistent_without_at_or_digits")
        )

    def test_permission_denied_with_csrf_text_not_sniffed(self) -> None:
        """
        DRF PermissionDenied containing 'csrf' keyword preserves MSG-4.2-M01.
        """
        from rest_framework.exceptions import (
            PermissionDenied as DRFPermissionDenied,
        )

        from apps.core.exceptions import custom_exception_handler

        exc = DRFPermissionDenied("Custom csrf permission failure")
        response = custom_exception_handler(exc, {})
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data.get("code"), "MSG-4.2-M01")
        self.assertEqual(
            response.data.get("message"),
            "Bạn không có quyền thực hiện thao tác này.",
        )


class AccountModelsTest(TestCase):
    """
    Test suite verifying Account, AccountManager, and Token model methods,
    properties, and string representations to ensure 100% models coverage.
    """

    def test_account_str_representations(self) -> None:
        # Verify __str__ fallback priority: email -> phone -> Account #id
        acc_email = Account(id=101, email="user@example.com")
        self.assertEqual(str(acc_email), "user@example.com")

        acc_phone = Account(id=102, phone="0912345678")
        self.assertEqual(str(acc_phone), "0912345678")

        acc_id_only = Account(id=103)
        self.assertEqual(str(acc_id_only), "Account #103")

    def test_account_permissions_and_staff_flags(self) -> None:
        # Staff and superuser capabilities are tied to MANAGER role
        mgr = Account(role="MANAGER")
        self.assertTrue(mgr.is_staff)
        self.assertTrue(mgr.is_superuser)
        self.assertTrue(mgr.has_perm("accounts.add_account"))
        self.assertTrue(mgr.has_module_perms("accounts"))

        emp = Account(role="EMPLOYEE")
        self.assertFalse(emp.is_staff)
        self.assertFalse(emp.is_superuser)
        self.assertFalse(emp.has_perm("accounts.add_account"))
        self.assertFalse(emp.has_module_perms("accounts"))

    def test_persistent_and_reset_token_str(self) -> None:
        token = PersistentLoginToken(id=1, series="series_abc123", account_id=101)
        self.assertEqual(str(token), "Token series series_abc123 for Account #101")

        reset_token = PasswordResetToken(id=77, account_id=101)
        self.assertEqual(str(reset_token), "ResetToken #77 for Account #101")

    def test_account_manager_user_creation_variants(self) -> None:
        # Require at least email or phone
        with self.assertRaises(ValueError):
            Account.objects.create_user(email=None, phone=None)

        # Usable vs unusable password handling
        user_no_pw = Account.objects.create_user(
            email="nopw@parking.com", password=None
        )
        self.assertFalse(user_no_pw.has_usable_password())

        # Superuser helper sets MANAGER role and active status
        admin = Account.objects.create_superuser(
            email="admin@parking.com", password="AdminPassword123!"
        )
        self.assertEqual(admin.role, "MANAGER")
        self.assertTrue(admin.is_active)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_account_manager_soft_delete_query_methods(self) -> None:
        # Ensure proxy methods on AccountManager delegate to SoftDeleteQuerySet
        self.assertTrue(hasattr(Account.objects.with_deleted(), "filter"))
        self.assertTrue(hasattr(Account.objects.only_deleted(), "filter"))

        # Exercise restore and soft_delete proxy delegates on manager
        with patch.object(Account.objects, "get_queryset") as mock_get_qs:
            Account.objects.restore()
            mock_get_qs.return_value.restore.assert_called_once()

            Account.objects.soft_delete(user=None)
            mock_get_qs.return_value.soft_delete.assert_called_once_with(user=None)
