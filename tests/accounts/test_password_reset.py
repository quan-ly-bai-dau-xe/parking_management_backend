"""
Password Reset Unit & Integration Tests per REQ-4.1-F04, OQ-84, TL-36, and ADR-0004.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, PasswordResetToken, PersistentLoginToken
from apps.accounts.serializers.auth import (
    ForgotPasswordSerializer,
    ResetPasswordConfirmSerializer,
)
from apps.accounts.services.auth import (
    confirm_password_reset,
    request_password_reset,
)
from apps.accounts.services.throttling import PasswordResetLimiter
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import PROPOSAL_MESSAGES


class ForgotPasswordSerializerTest(SimpleTestCase):
    """Kiểm tra validation của ForgotPasswordSerializer per TL-52."""

    def test_valid_email_passes(self):
        serializer = ForgotPasswordSerializer(data={"email": "Employee@Parking.com "})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["email"], "employee@parking.com")

    def test_empty_email_fails(self):
        serializer = ForgotPasswordSerializer(data={"email": "   "})
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

    def test_invalid_email_format_fails(self):
        serializer = ForgotPasswordSerializer(data={"email": "not-an-email"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)


class ResetPasswordConfirmSerializerTest(SimpleTestCase):
    """Kiểm tra validation của ResetPasswordConfirmSerializer per SRS 4.3.3 và Rule 07."""

    def test_valid_payload_passes(self):
        payload = {
            "token": "valid-token-123",
            "new_password": "ValidPassword123!",
            "confirm_password": "ValidPassword123!",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        self.assertTrue(serializer.is_valid())

    def test_password_mismatch_fails_with_prop_message(self):
        payload = {
            "token": "valid-token-123",
            "new_password": "ValidPassword123!",
            "confirm_password": "DifferentPassword123!",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            serializer.is_valid(raise_exception=True)
        exc = ctx.exception
        self.assertEqual(exc.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("confirm_password", exc.details)
        self.assertEqual(
            exc.details["confirm_password"][0], PROPOSAL_MESSAGES["PROP-4.1-P09"]
        )

    def test_password_complexity_missing_uppercase(self):
        payload = {
            "token": "token-123",
            "new_password": "lowercase123!",
            "confirm_password": "lowercase123!",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("new_password", ctx.exception.details)

    def test_password_complexity_missing_digit(self):
        payload = {
            "token": "token-123",
            "new_password": "NoDigitPassword!",
            "confirm_password": "NoDigitPassword!",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("new_password", ctx.exception.details)

    def test_password_complexity_missing_special_char(self):
        payload = {
            "token": "token-123",
            "new_password": "NoSpecialChar123",
            "confirm_password": "NoSpecialChar123",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        with self.assertRaises(BusinessAPIException) as ctx:
            serializer.is_valid(raise_exception=True)
        self.assertIn("new_password", ctx.exception.details)

    def test_password_too_short(self):
        payload = {
            "token": "token-123",
            "new_password": "Short1!",
            "confirm_password": "Short1!",
        }
        serializer = ResetPasswordConfirmSerializer(data=payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn("new_password", serializer.errors)


class PasswordResetLimiterTest(SimpleTestCase):
    """Kiểm tra rate limit 3 req/giờ per email và 10 req/giờ per IP per OQ-84."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.limiter = PasswordResetLimiter()

    def tearDown(self):
        cache.clear()

    def test_email_throttle_limit_enforced(self):
        request = self.factory.post(
            "/api/v1/auth/forgot-password/", REMOTE_ADDR="192.168.1.100"
        )
        email = "test.throttle@parking.com"

        # 3 requests allowed
        for _ in range(3):
            self.limiter.check_and_increment(request, email)

        # 4th request must raise 429
        with self.assertRaises(BusinessAPIException) as ctx:
            self.limiter.check_and_increment(request, email)

        self.assertEqual(ctx.exception.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P07")
        self.assertEqual(ctx.exception.message, PROPOSAL_MESSAGES["PROP-4.1-P07"])

    def test_ip_throttle_limit_enforced(self):
        client_ip = "10.0.0.99"
        request = self.factory.post(
            "/api/v1/auth/forgot-password/", REMOTE_ADDR=client_ip
        )

        # 10 requests with different emails from same IP
        for i in range(10):
            self.limiter.check_and_increment(request, f"diff_{i}@parking.com")

        # 11th request must raise 429
        with self.assertRaises(BusinessAPIException) as ctx:
            self.limiter.check_and_increment(request, "diff_10@parking.com")

        self.assertEqual(ctx.exception.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P07")


class PasswordResetServiceMockTest(SimpleTestCase):
    """Kiểm tra logic nghiệp vụ Password Reset độc lập qua mock per TL-52."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.request = self.factory.post(
            "/api/v1/auth/forgot-password/", REMOTE_ADDR="127.0.0.1"
        )
        self.mock_account = MagicMock(spec=Account)
        self.mock_account.id = 123
        self.mock_account.email = "mock.user@parking.com"
        self.mock_account.is_active = True
        self.mock_account.deleted_at = None
        self.mock_account.set_password = MagicMock()
        self.mock_account.save = MagicMock()

    def tearDown(self):
        cache.clear()

    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_anti_enumeration_non_existent_email(self, mock_acc_filter):
        mock_acc_filter.return_value.first.return_value = None

        token = request_password_reset(self.request, "nobody@parking.com")
        self.assertIsNone(token)
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_anti_enumeration_inactive_account(self, mock_acc_filter):
        self.mock_account.is_active = False
        mock_acc_filter.return_value.first.return_value = None

        token = request_password_reset(self.request, self.mock_account.email)
        self.assertIsNone(token)
        self.assertEqual(len(mail.outbox), 0)

    @patch("apps.accounts.services.auth.send_mail")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.create")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    @patch("apps.accounts.services.auth.Account.objects.filter")
    def test_request_password_reset_success(
        self, mock_acc_filter, mock_token_filter, mock_token_create, mock_send_mail
    ):
        mock_acc_filter.return_value.first.return_value = self.mock_account

        token = request_password_reset(self.request, self.mock_account.email)

        self.assertIsNotNone(token)
        mock_token_filter.return_value.delete.assert_called_once()
        mock_token_create.assert_called_once()
        mock_send_mail.assert_called_once()

    @patch("apps.accounts.services.auth.transaction.atomic")
    @patch("apps.accounts.services.auth.revoke_all_account_tokens")
    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    def test_confirm_password_reset_success(
        self, mock_token_filter, mock_revoke_tokens, mock_atomic
    ):
        mock_atomic.return_value.__enter__.return_value = None
        mock_atomic.return_value.__exit__.return_value = None

        mock_token = MagicMock(spec=PasswordResetToken)
        mock_token.account = self.mock_account
        mock_token.used_at = None
        mock_token.expires_at = timezone.now() + timedelta(minutes=15)
        mock_token.save = MagicMock()

        mock_token_filter.return_value.select_related.return_value.first.return_value = mock_token

        account = confirm_password_reset("valid-token", "NewPassword123!")

        self.assertEqual(account, self.mock_account)
        self.mock_account.set_password.assert_called_once_with("NewPassword123!")
        self.mock_account.save.assert_called_once()
        mock_revoke_tokens.assert_called_once_with(self.mock_account.id)
        mock_token.save.assert_called_once_with(update_fields=["used_at"])

    @patch("apps.accounts.services.auth.PasswordResetToken.objects.filter")
    def test_confirm_password_reset_invalid_token_fails(self, mock_token_filter):
        mock_token_filter.return_value.select_related.return_value.first.return_value = None

        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_password_reset("invalid-token", "NewPassword123!")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P08")


class PasswordResetViewMockTest(SimpleTestCase):
    """Kiểm tra DRF Views cho ForgotPasswordView và ResetPasswordConfirmView."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    @patch("apps.accounts.views.auth.request_password_reset")
    def test_forgot_password_view_post_success(self, mock_req_reset):
        from apps.accounts.views.auth import ForgotPasswordView

        view = ForgotPasswordView.as_view()
        request = self.factory.post(
            "/api/v1/auth/forgot-password/",
            data={"email": "employee@parking.com"},
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], PROPOSAL_MESSAGES["PROP-4.1-P04"])
        mock_req_reset.assert_called_once()

    @patch("apps.accounts.views.auth.confirm_password_reset")
    def test_reset_password_confirm_view_post_success(self, mock_confirm):
        from apps.accounts.views.auth import ResetPasswordConfirmView

        view = ResetPasswordConfirmView.as_view()
        request = self.factory.post(
            "/api/v1/auth/reset-password/",
            data={
                "token": "valid-token-abc",
                "new_password": "NewSecurePass123!",
                "confirm_password": "NewSecurePass123!",
            },
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True

        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], PROPOSAL_MESSAGES["PROP-4.1-P05"])
        mock_confirm.assert_called_once_with("valid-token-abc", "NewSecurePass123!")


class PasswordResetServiceTest(TestCase):
    """Kiểm tra logic nghiệp vụ của request_password_reset và confirm_password_reset."""

    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()
        self.request = self.factory.post(
            "/api/v1/auth/forgot-password/", REMOTE_ADDR="127.0.0.1"
        )
        self.account = Account.objects.create(
            email="reset.user@parking.com",
            phone="0911222333",
            password="InitialHashedPassword123!",
            role="EMPLOYEE",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()
        PasswordResetToken.objects.filter(account=self.account).delete()
        PersistentLoginToken.objects.filter(account=self.account).delete()
        Account.objects.filter(id=self.account.id).delete()

    def test_anti_enumeration_non_existent_email_returns_none(self):
        """Email không tồn tại không làm phát sinh token hoặc ngoại lệ per OWASP."""
        token = request_password_reset(self.request, "nonexistent@parking.com")
        self.assertIsNone(token)
        self.assertEqual(len(mail.outbox), 0)

    def test_anti_enumeration_inactive_account_returns_none(self):
        """Tài khoản bị vô hiệu hóa (is_active=False) không phát sinh token."""
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        token = request_password_reset(self.request, self.account.email)
        self.assertIsNone(token)
        self.assertEqual(len(mail.outbox), 0)

    def test_request_password_reset_success(self):
        """Tạo token hợp lệ, lưu vào DB và gửi email thông báo."""
        raw_token = request_password_reset(self.request, self.account.email)
        self.assertIsNotNone(raw_token)

        # Kiểm tra bản ghi trong DB
        db_token = PasswordResetToken.objects.filter(account=self.account).first()
        self.assertIsNotNone(db_token)
        self.assertIsNone(db_token.used_at)
        self.assertGreater(db_token.expires_at, timezone.now())

        # Kiểm tra email được gửi
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn(self.account.email, sent_email.to)
        self.assertIn(raw_token, sent_email.body)

    def test_request_password_reset_invalidates_prior_tokens(self):
        """Yêu cầu reset mới sẽ xóa bỏ các token cũ chưa sử dụng (TL-36 plain DELETE)."""
        token1 = request_password_reset(self.request, self.account.email)
        self.assertIsNotNone(token1)

        token2 = request_password_reset(self.request, self.account.email)
        self.assertIsNotNone(token2)

        # Chỉ còn 1 token duy nhất trong DB
        tokens = PasswordResetToken.objects.filter(account=self.account)
        self.assertEqual(tokens.count(), 1)

    def test_confirm_password_reset_success(self):
        """Đặt lại mật khẩu thành công: cập nhật hash, ghi nhận used_at và thu hồi session cũ."""
        raw_token = request_password_reset(self.request, self.account.email)
        new_password = "BrandNewPassword123!"

        # Tạo sẵn persistent login token giả lập session cũ
        PersistentLoginToken.objects.create(
            series="series-old-session-1234",
            token_hash="fake-token-hash",
            account=self.account,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 1
        )

        updated_account = confirm_password_reset(raw_token, new_password)

        # Mật khẩu mới được thiết lập và có thể verify bằng check_password
        self.assertTrue(updated_account.check_password(new_password))

        # Token reset được đánh dấu used_at
        db_token = PasswordResetToken.objects.filter(account=self.account).first()
        self.assertIsNotNone(db_token.used_at)

        # Toàn bộ persistent tokens cũ bị thu hồi
        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 0
        )

    def test_confirm_password_reset_token_reuse_fails(self):
        """Token đã sử dụng không thể dùng lại lần thứ hai (Single-use per TL-36)."""
        raw_token = request_password_reset(self.request, self.account.email)
        confirm_password_reset(raw_token, "FirstNewPassword123!")

        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_password_reset(raw_token, "SecondNewPassword123!")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P08")

    def test_confirm_password_reset_expired_token_fails(self):
        """Token hết hạn sẽ bị từ chối với mã lỗi PROP-4.1-P08."""
        raw_token = request_password_reset(self.request, self.account.email)
        db_token = PasswordResetToken.objects.filter(account=self.account).first()
        db_token.expires_at = timezone.now() - timedelta(minutes=1)
        db_token.save(update_fields=["expires_at"])

        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_password_reset(raw_token, "ValidPassword123!")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P08")

    def test_confirm_password_reset_nonexistent_token_fails(self):
        """Token không tồn tại sẽ bị từ chối với mã lỗi PROP-4.1-P08."""
        with self.assertRaises(BusinessAPIException) as ctx:
            confirm_password_reset("completely-invalid-token", "ValidPassword123!")

        self.assertEqual(ctx.exception.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ctx.exception.code, "PROP-4.1-P08")


class PasswordResetEndpointApiTest(TestCase):
    """Kiểm tra end-to-end các API endpoints qua DRF APIClient."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.account = Account.objects.create(
            email="api.user@parking.com",
            phone="0933444555",
            password="HashedInitial123!",
            role="CUSTOMER",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()
        PasswordResetToken.objects.filter(account=self.account).delete()
        Account.objects.filter(id=self.account.id).delete()

    def test_forgot_password_endpoint_existing_email(self):
        """POST /api/v1/auth/forgot-password/ trả về 200 OK với thông điệp tiêu chuẩn."""
        url = reverse("auth-forgot-password")
        response = self.client.post(url, {"email": self.account.email}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["detail"], PROPOSAL_MESSAGES["PROP-4.1-P04"])

    def test_forgot_password_endpoint_non_existing_email(self):
        """POST /api/v1/auth/forgot-password/ với email không tồn tại vẫn trả về 200 OK (Anti-enumeration)."""
        url = reverse("auth-forgot-password")
        response = self.client.post(
            url, {"email": "does_not_exist@parking.com"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["detail"], PROPOSAL_MESSAGES["PROP-4.1-P04"])

    def test_forgot_password_endpoint_invalid_email_format(self):
        """POST /api/v1/auth/forgot-password/ với email sai định dạng trả về 400 Bad Request."""
        url = reverse("auth-forgot-password")
        response = self.client.post(url, {"email": "invalid-email"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_full_reset_password_workflow(self):
        """Quy trình hoàn chỉnh: Gửi yêu cầu -> Lấy token -> Đặt lại mật khẩu mới -> Đăng nhập."""
        # 1. Gửi yêu cầu đặt lại mật khẩu
        forgot_url = reverse("auth-forgot-password")
        res_forgot = self.client.post(
            forgot_url, {"email": self.account.email}, format="json"
        )
        self.assertEqual(res_forgot.status_code, status.HTTP_200_OK)

        # Lấy token từ email đã gửi
        self.assertEqual(len(mail.outbox), 1)
        raw_token = (
            mail.outbox[0]
            .body.split("Mã xác thực đặt lại mật khẩu của bạn là:\n")[1]
            .split("\n\n")[0]
            .strip()
        )

        # 2. Gửi request đặt lại mật khẩu mới
        reset_url = reverse("auth-reset-password")
        new_password = "BrandNewSuperSecret123!"
        res_reset = self.client.post(
            reset_url,
            {
                "token": raw_token,
                "new_password": new_password,
                "confirm_password": new_password,
            },
            format="json",
        )
        self.assertEqual(res_reset.status_code, status.HTTP_200_OK)
        self.assertEqual(res_reset.json()["detail"], PROPOSAL_MESSAGES["PROP-4.1-P05"])

        # 3. Thử đăng nhập bằng mật khẩu mới
        login_url = reverse("auth-login")
        res_login = self.client.post(
            login_url,
            {
                "identifier": self.account.email,
                "password": new_password,
            },
            format="json",
        )
        self.assertEqual(res_login.status_code, status.HTTP_200_OK)
        self.assertEqual(res_login.json()["email"], self.account.email)
