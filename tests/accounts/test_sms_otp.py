"""
SMS OTP Unit & Integration Tests for Password Reset and Customer Registration.
Covers SMS provider dispatch, phone normalization, rate limits, anti-brute force,
anti-enumeration, and complete registration/reset workflows.
"""

from __future__ import annotations

import contextlib
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Account, PasswordResetToken
from apps.accounts.serializers.auth import (
    ForgotPasswordSMSSerializer,
    RegisterSMSConfirmSerializer,
    RegisterSMSRequestSerializer,
    ResetPasswordSMSConfirmSerializer,
)
from apps.accounts.services.auth import (
    confirm_password_reset_sms,
    confirm_register_sms,
    generate_numeric_otp,
    hash_token,
    request_password_reset_sms,
    request_register_otp,
)
from apps.accounts.services.sms import (
    ConsoleSMSBackend,
    MockSMSBackend,
    VonageSMSBackend,
    is_valid_phone_number,
    normalize_vietnamese_phone,
)
from apps.accounts.services.throttling import SMSOTPLimiter
from apps.accounts.views.auth import (
    ForgotPasswordSMSView,
    RegisterSMSConfirmView,
    RegisterSMSRequestView,
    ResetPasswordSMSConfirmView,
)
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import PROPOSAL_MESSAGES
from apps.customers.models import Customer


class SMSBackendAndPhoneHelperTest(TestCase):
    """Kiểm tra logic chuẩn hóa số điện thoại và hệ thống SMS provider backend."""

    def setUp(self):
        MockSMSBackend.reset()

    def test_normalize_vietnamese_phone(self):
        self.assertEqual(normalize_vietnamese_phone("+84912345678"), "0912345678")
        self.assertEqual(normalize_vietnamese_phone("84912345678"), "0912345678")
        self.assertEqual(normalize_vietnamese_phone("0912-345-678"), "0912345678")
        self.assertEqual(normalize_vietnamese_phone("0912.345.678"), "0912345678")
        self.assertEqual(normalize_vietnamese_phone("(0912) 345 678"), "0912345678")
        self.assertEqual(normalize_vietnamese_phone(""), "")
        self.assertEqual(normalize_vietnamese_phone(None), "")

    def test_is_valid_phone_number(self):
        self.assertTrue(is_valid_phone_number("0912345678"))
        self.assertTrue(is_valid_phone_number("0387654321"))
        self.assertTrue(is_valid_phone_number("0771234567"))
        self.assertTrue(is_valid_phone_number("+84988776655"))
        self.assertFalse(is_valid_phone_number("12345"))
        self.assertFalse(is_valid_phone_number("abc0912345678"))
        self.assertFalse(is_valid_phone_number(""))

    def test_mock_sms_backend_send(self):
        backend = MockSMSBackend()
        success = backend.send_sms("0912345678", "Mã xác thực 123456")
        self.assertTrue(success)
        self.assertEqual(len(MockSMSBackend.outbox), 1)
        self.assertEqual(MockSMSBackend.outbox[0]["phone"], "0912345678")
        self.assertIn("123456", MockSMSBackend.outbox[0]["message"])

    def test_console_sms_backend(self):
        backend = ConsoleSMSBackend()
        self.assertTrue(backend.send_sms("0912345678", "Test Console Message"))

    def test_vonage_format_international_phone(self):
        backend = VonageSMSBackend()
        self.assertEqual(
            backend.format_international_phone("0766709535"), "84766709535"
        )
        self.assertEqual(
            backend.format_international_phone("+84766709535"), "84766709535"
        )
        self.assertEqual(
            backend.format_international_phone("84766709535"), "84766709535"
        )

    def test_vonage_sms_backend_missing_credentials(self):
        backend = VonageSMSBackend(api_key="", api_secret="")
        self.assertFalse(backend.send_sms("0766709535", "Test message"))

    @patch("urllib.request.urlopen")
    def test_vonage_sms_backend_send_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"messages": [{"to": "84766709535", "message-id": "vonage-msg-12345", "status": "0"}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        backend = VonageSMSBackend(
            api_key="test_key", api_secret="test_secret", from_sender="TestBrand"
        )
        result = backend.send_sms("0766709535", "Mã OTP 123456")
        self.assertTrue(result)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("rest.nexmo.com", req.full_url)

    @patch("urllib.request.urlopen")
    def test_vonage_sms_backend_send_failure(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"messages": [{"to": "84766709535", "status": "29", "error-text": "Non-whitelisted destination"}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        backend = VonageSMSBackend(api_key="test_key", api_secret="test_secret")
        result = backend.send_sms("0766709535", "Mã OTP 123456")
        self.assertFalse(result)

    def test_generate_numeric_otp(self):
        for _ in range(10):
            otp = generate_numeric_otp(6)
            self.assertEqual(len(otp), 6)
            self.assertTrue(otp.isdigit())
            self.assertTrue(100000 <= int(otp) <= 999999)


class SMSOTPLimiterTest(TestCase):
    """Kiểm tra giới hạn tần suất gửi SMS OTP và thời gian chờ cooldown 60s."""

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()
        self.limiter = SMSOTPLimiter()

    def test_cooldown_enforced(self):
        request = self.rf.post(
            "/api/v1/auth/forgot-password/sms/", REMOTE_ADDR="192.168.1.100"
        )
        self.limiter.check_and_increment(request, "0912345678", action="test")

        # Ngay lập tức gọi tiếp -> bị chặn bởi cooldown 60s
        with self.assertRaises(BusinessAPIException) as ctx:
            self.limiter.check_and_increment(request, "0912345678", action="test")
        self.assertEqual(ctx.exception.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P17")

    def test_phone_throttle_limit_enforced(self):
        request = self.rf.post(
            "/api/v1/auth/forgot-password/sms/", REMOTE_ADDR="192.168.1.101"
        )
        # Giả lập bypass cooldown bằng cách xóa key cooldown
        norm_phone = "0912345679"
        cooldown_key = self.limiter.get_cooldown_key(norm_phone, "test_limit")

        # Cho phép 3 lần
        for _ in range(3):
            cache.delete(cooldown_key)
            self.limiter.check_and_increment(request, norm_phone, action="test_limit")

        # Lần 4 vượt quá giới hạn 3 req/giờ per phone
        cache.delete(cooldown_key)
        with self.assertRaises(BusinessAPIException) as ctx:
            self.limiter.check_and_increment(request, norm_phone, action="test_limit")
        self.assertEqual(ctx.exception.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P12")


class SMSOTPSerializersTest(TestCase):
    """Kiểm tra serialization và validation của các payload SMS OTP."""

    def test_forgot_password_sms_serializer_valid(self):
        s = ForgotPasswordSMSSerializer(data={"phone": " 0912345678 "})
        self.assertTrue(s.is_valid())
        self.assertEqual(s.validated_data["phone"], "0912345678")

    def test_forgot_password_sms_serializer_invalid_phone(self):
        s = ForgotPasswordSMSSerializer(data={"phone": "invalid-phone"})
        with self.assertRaises(BusinessAPIException) as ctx:
            s.is_valid(raise_exception=True)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P15")

    def test_reset_password_sms_confirm_serializer_valid(self):
        payload = {
            "phone": "0912345678",
            "otp": "123456",
            "new_password": "NewSecurePassword123!",
            "confirm_password": "NewSecurePassword123!",
        }
        s = ResetPasswordSMSConfirmSerializer(data=payload)
        self.assertTrue(s.is_valid())

    def test_reset_password_sms_confirm_serializer_invalid_otp(self):
        payload = {
            "phone": "0912345678",
            "otp": "123",
            "new_password": "NewSecurePassword123!",
            "confirm_password": "NewSecurePassword123!",
        }
        s = ResetPasswordSMSConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            s.is_valid(raise_exception=True)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P11")

    def test_reset_password_sms_confirm_serializer_password_mismatch(self):
        payload = {
            "phone": "0912345678",
            "otp": "123456",
            "new_password": "NewSecurePassword123!",
            "confirm_password": "DifferentPassword123!",
        }
        s = ResetPasswordSMSConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            s.is_valid(raise_exception=True)
        self.assertEqual(ctx.exception.code, "PROP-GEN-P01")

    def test_register_sms_request_serializer_valid(self):
        s = RegisterSMSRequestSerializer(data={"phone": "+84912345678"})
        self.assertTrue(s.is_valid())
        self.assertEqual(s.validated_data["phone"], "0912345678")

    def test_register_sms_confirm_serializer_valid(self):
        payload = {
            "phone": "0912345678",
            "otp": "654321",
            "password": "SecurePassword123!",
            "confirm_password": "SecurePassword123!",
            "full_name": "Nguyễn Văn A",
            "identity_card_number": "012345678901",
            "email": "vana@example.com",
        }
        s = RegisterSMSConfirmSerializer(data=payload)
        self.assertTrue(s.is_valid())


class SMSOTPPasswordResetServiceTest(TestCase):
    """Kiểm tra service đặt lại mật khẩu qua SMS OTP."""

    def setUp(self):
        cache.clear()
        MockSMSBackend.reset()
        self.rf = RequestFactory()

    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_request_password_reset_sms_anti_enumeration(self, mock_account_filter):
        mock_account_filter.return_value.first.return_value = None
        request = self.rf.post(
            "/api/v1/auth/forgot-password/sms/", REMOTE_ADDR="192.168.1.10"
        )
        result = request_password_reset_sms(request, "0999999999")
        self.assertIsNone(result)
        self.assertEqual(len(MockSMSBackend.outbox), 0)

    @patch("apps.accounts.services.auth.send_sms")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.create")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_request_password_reset_sms_success(
        self, mock_account_filter, mock_token_filter, mock_token_create, mock_send_sms
    ):
        mock_account = MagicMock(spec=Account)
        mock_account.id = 42
        mock_account.phone = "0912345678"
        mock_account.is_active = True
        mock_account.deleted_at = None
        mock_account_filter.return_value.first.return_value = mock_account

        request = self.rf.post(
            "/api/v1/auth/forgot-password/sms/", REMOTE_ADDR="192.168.1.20"
        )
        otp = request_password_reset_sms(request, "0912345678")

        self.assertIsNotNone(otp)
        self.assertEqual(len(otp), 6)
        mock_send_sms.assert_called_once()
        self.assertIn(otp, mock_send_sms.call_args[0][1])

    @patch("apps.accounts.services.auth.revoke_all_account_tokens")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_confirm_password_reset_sms_success(
        self, mock_account_filter, mock_token_filter, mock_revoke
    ):
        mock_account = MagicMock(spec=Account)
        mock_account.id = 42
        mock_account.phone = "0912345678"
        mock_account_filter.return_value.first.return_value = mock_account

        mock_token = MagicMock(spec=PasswordResetToken)
        mock_token.account = mock_account
        mock_token.used_at = None
        mock_token.expires_at = timezone.now() + timedelta(minutes=5)
        mock_token_filter.return_value.first.return_value = mock_token

        with patch("django.db.transaction.atomic"):
            account = confirm_password_reset_sms(
                "0912345678", "123456", "NewValidPassword123!"
            )

        self.assertEqual(account, mock_account)
        mock_account.set_password.assert_called_with("NewValidPassword123!")
        mock_account.save.assert_called_once()
        self.assertIsNotNone(mock_token.used_at)
        mock_revoke.assert_called_with(42)

    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_confirm_password_reset_sms_brute_force_lockout(
        self, mock_account_filter, mock_token_filter
    ):
        mock_account = MagicMock(spec=Account)
        mock_account.id = 99
        mock_account_filter.return_value.first.return_value = mock_account
        mock_token_filter.return_value.first.return_value = None

        # Gửi sai 5 lần
        for _ in range(5):
            with contextlib.suppress(BusinessAPIException):
                confirm_password_reset_sms(
                    "0912345678", "000000", "NewValidPassword123!"
                )

        # Lần thứ 6: bị khóa do nhập sai quá 5 lần
        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_password_reset_sms("0912345678", "000000", "NewValidPassword123!")
        self.assertEqual(ctx.exception.code, "PROP-4.1-P16")


class SMSOTPRegisterServiceTest(TestCase):
    """Kiểm tra service đăng ký tài khoản qua SMS OTP."""

    def setUp(self):
        cache.clear()
        MockSMSBackend.reset()
        self.rf = RequestFactory()

    def test_request_register_otp_duplicate_phone_fails(self):
        request = self.rf.post(
            "/api/v1/auth/register/sms/request/", REMOTE_ADDR="192.168.1.30"
        )
        mock_filter = MagicMock()
        mock_filter.exists.return_value = True
        with (
            patch.object(Account.objects, "filter", return_value=mock_filter),
            self.assertRaises(BusinessAPIException) as ctx,
        ):
            request_register_otp(request, "0912345678")
        self.assertEqual(ctx.exception.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P13")

    def test_request_register_otp_success(self):
        request = self.rf.post(
            "/api/v1/auth/register/sms/request/", REMOTE_ADDR="192.168.1.31"
        )
        mock_filter = MagicMock()
        mock_filter.exists.return_value = False
        with (
            patch.object(Account.objects, "filter", return_value=mock_filter),
            patch("apps.accounts.services.auth.send_sms") as mock_send_sms,
        ):
            otp = request_register_otp(request, "0912345678")

        self.assertIsNotNone(otp)
        self.assertEqual(len(otp), 6)
        # Kiểm tra OTP đã được lưu vào cache
        cached = cache.get("otp:register:0912345678")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["token_hash"], hash_token(otp))
        mock_send_sms.assert_called_once()

    def test_confirm_register_sms_expired_otp_fails(self):
        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_register_sms(
                phone="0912345678",
                otp="123456",
                password="SecurePassword123!",
                full_name="Nguyễn Văn A",
            )
        self.assertEqual(ctx.exception.code, "PROP-4.1-P11")

    def test_confirm_register_sms_success(self):
        # Lưu OTP hợp lệ vào cache
        otp = "123456"
        cache.set(
            "otp:register:0912345678",
            {"token_hash": hash_token(otp), "attempts": 0},
            timeout=300,
        )

        mock_acc = MagicMock(spec=Account)
        mock_acc.id = 101
        mock_acc.phone = "0912345678"
        mock_acc.role = "CUSTOMER"

        mock_cust = MagicMock(spec=Customer)
        mock_cust.id = 202
        mock_cust.code = "KH0001"
        mock_cust.full_name = "Nguyễn Văn A"

        mock_cursor_ctx = MagicMock()
        mock_cursor_ctx.fetchone.return_value = [0]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor_ctx

        mock_acc_filter = MagicMock()
        mock_acc_filter.exists.return_value = False
        mock_cust_filter = MagicMock()
        mock_cust_filter.exists.return_value = False

        with (
            patch("django.db.transaction.atomic"),
            patch("apps.accounts.services.auth.connection", mock_conn),
            patch.object(Account.objects, "filter", return_value=mock_acc_filter),
            patch.object(Account.objects, "create_user", return_value=mock_acc),
            patch.object(Customer.objects, "filter", return_value=mock_cust_filter),
            patch.object(Customer.objects, "create", return_value=mock_cust),
        ):
            acc, cust = confirm_register_sms(
                phone="0912345678",
                otp=otp,
                password="SecurePassword123!",
                full_name="Nguyễn Văn A",
                identity_card_number="012345678901",
                email="vana@example.com",
            )

        self.assertEqual(acc.id, 101)
        self.assertEqual(cust.code, "KH0001")
        # Cache OTP đã được xóa
        self.assertIsNone(cache.get("otp:register:0912345678"))


class SMSOTPViewsTest(TestCase):
    """Kiểm tra các endpoints REST API của SMS OTP."""

    def setUp(self):
        cache.clear()
        self.rf = RequestFactory()

    @patch("apps.accounts.views.auth.request_password_reset_sms")
    def test_forgot_password_sms_view_post_success(self, mock_req_sms):
        view = ForgotPasswordSMSView.as_view()
        request = self.rf.post(
            "/api/v1/auth/forgot-password/sms/",
            data={"phone": "0912345678"},
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Mã OTP xác thực đã được gửi", response.data["detail"])

    @patch("apps.accounts.views.auth.confirm_password_reset_sms")
    def test_reset_password_sms_confirm_view_post_success(self, mock_conf_sms):
        view = ResetPasswordSMSConfirmView.as_view()
        request = self.rf.post(
            "/api/v1/auth/reset-password/sms/",
            data={
                "phone": "0912345678",
                "otp": "123456",
                "new_password": "NewSecurePassword123!",
                "confirm_password": "NewSecurePassword123!",
            },
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Đặt lại mật khẩu thành công", response.data["detail"])

    @patch("apps.accounts.views.auth.request_register_otp")
    def test_register_sms_request_view_post_success(self, mock_reg_sms):
        view = RegisterSMSRequestView.as_view()
        request = self.rf.post(
            "/api/v1/auth/register/sms/request/",
            data={"phone": "0912345678"},
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("Mã OTP xác thực đã được gửi", response.data["detail"])

    @patch("apps.accounts.views.auth.confirm_register_sms")
    def test_register_sms_confirm_view_post_success(self, mock_conf_reg):
        mock_acc = MagicMock()
        mock_acc.id = 11
        mock_acc.email = "vana@example.com"
        mock_acc.phone = "0912345678"
        mock_acc.role = "CUSTOMER"
        mock_acc.is_active = True
        mock_acc.last_login = None

        mock_cust = MagicMock()
        mock_cust.id = 22
        mock_cust.code = "KH0001"
        mock_cust.full_name = "Nguyễn Văn A"
        mock_cust.phone = "0912345678"

        mock_conf_reg.return_value = (mock_acc, mock_cust)

        view = RegisterSMSConfirmView.as_view()
        request = self.rf.post(
            "/api/v1/auth/register/sms/confirm/",
            data={
                "phone": "0912345678",
                "otp": "123456",
                "password": "SecurePassword123!",
                "confirm_password": "SecurePassword123!",
                "full_name": "Nguyễn Văn A",
            },
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["detail"], PROPOSAL_MESSAGES["PROP-4.1-P14"])
        self.assertEqual(response.data["account"]["role"], "CUSTOMER")
        self.assertEqual(response.data["customer"]["code"], "KH0001")
