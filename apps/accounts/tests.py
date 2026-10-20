import json
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import Account, PersistentLoginToken

User = get_user_model()


class LoginViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.login_url = reverse("login")
        self.user_data = {
            "username": "testuser",
            "password": "Testpass123!",
            "role": "EMPLOYEE",
        }
        # Create a test user
        self.user = Account.objects.create_user(
            username=self.user_data["username"],
            password=self.user_data["password"],
            role=self.user_data["role"],
        )

    def test_login_success(self):
        """Test successful login with valid credentials"""
        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertIn("user", response.json()["data"])
        self.assertEqual(
            response.json()["data"]["user"]["username"], self.user_data["username"]
        )

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {"username": self.user_data["username"], "password": "wrongpassword"}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["error"]["message"],
            "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
        )

    def test_login_missing_username(self):
        """Test login with missing username"""
        response = self.client.post(
            self.login_url,
            data=json.dumps({"username": "", "password": self.user_data["password"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["error"]["message"],
            "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
        )

    def test_login_missing_password(self):
        """Test login with missing password"""
        response = self.client.post(
            self.login_url,
            data=json.dumps({"username": self.user_data["username"], "password": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["error"]["message"],
            "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
        )

    def test_login_special_characters_username(self):
        """Test login with special characters in username"""
        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {"username": "test@user#", "password": self.user_data["password"]}
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["error"]["message"],
            "Tên đăng nhập không chứa ký tự đặc biệt",
        )

    def test_login_inactive_user(self):
        """Test login with inactive user"""
        # Deactivate the user
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(
            response.json()["error"]["message"], "Tài khoản đã được vô hiệu hóa"
        )

    @patch("apps.accounts.views.timezone")
    def test_login_remember_me_creates_token(self, mock_timezone):
        """Test that remember me creates a persistent login token"""
        # Mock timezone.now() to return a fixed time
        fixed_time = datetime(2026, 10, 18, 12, 0, 0)
        mock_timezone.now.return_value = fixed_time
        mock_timezone.timedelta = timedelta

        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"],
                    "remember_me": True,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)

        # Check that a persistent login token was created
        tokens = PersistentLoginToken.objects.filter(account=self.user)
        self.assertEqual(tokens.count(), 1)

        token = tokens.first()
        self.assertEqual(token.account, self.user)
        self.assertIsNotNone(token.series)
        self.assertIsNotNone(token.token_hash)
        self.assertEqual(token.ip_address, "testserver")  # Django test client IP
        # Check expiration is 30 days from fixed_time
        self.assertEqual(token.expires_at, fixed_time + timedelta(days=30))

    def test_login_session_fixation_protection(self):
        """Test that session key is cycled after login"""
        # Get initial session key
        session_before = self.client.session
        session_key_before = session_before.session_key

        response = self.client.post(
            self.login_url,
            data=json.dumps(
                {
                    "username": self.user_data["username"],
                    "password": self.user_data["password"],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Get session key after login
        session_after = self.client.session
        session_key_after = session_after.session_key

        # Session key should have changed (cycled)
        self.assertNotEqual(session_key_before, session_key_after)

    def test_login_invalid_json(self):
        """Test login with invalid JSON"""
        response = self.client.post(
            self.login_url, data="invalid json", content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["success"], False)
        self.assertEqual(response.json()["error"]["message"], "Yêu cầu không hợp lệ")
