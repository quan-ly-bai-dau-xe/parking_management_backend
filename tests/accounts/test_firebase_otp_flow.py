import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django
from django.test import override_settings

django.setup()

from apps.accounts.services.firebase_otp import (  # noqa: E402
    format_phone_number,
    mask_phone_number,
    send_sms_otp,
    verify_sms_otp,
)


class FirebaseOTPServiceTests(unittest.TestCase):
    def test_format_phone_number(self):
        self.assertEqual(format_phone_number("0766709535"), "+84766709535")
        self.assertEqual(format_phone_number("+84766709535"), "+84766709535")
        self.assertEqual(format_phone_number("84766709535"), "+84766709535")
        self.assertEqual(format_phone_number("076 670-9535"), "+84766709535")

    def test_mask_phone_number(self):
        self.assertEqual(mask_phone_number("+84766709535"), "+84***35")
        self.assertEqual(mask_phone_number("0766709535"), "076***35")
        self.assertEqual(mask_phone_number("123"), "***")
        self.assertEqual(mask_phone_number(""), "***")

    @override_settings(DEBUG=True, SMS_OTP_TEST_DOUBLE_ENABLED=True)
    @patch("apps.accounts.services.firebase_otp.load_firebase_config", return_value={})
    def test_send_sms_otp_dev_mode(self, _mock_config):
        result = send_sms_otp("0766709535")
        self.assertEqual(result["phoneNumber"], "+84766709535")
        self.assertTrue(result["sessionInfo"].startswith("mock_session_"))
        self.assertTrue(result["isMock"])
        self.assertEqual(result["testOtp"], "123456")

    @override_settings(DEBUG=True, SMS_OTP_TEST_DOUBLE_ENABLED=True)
    @patch("apps.accounts.services.firebase_otp.load_firebase_config", return_value={})
    def test_mock_session_verify(self, _mock_config):
        mock_session = "mock_session_test_0766709535"
        auth_data = verify_sms_otp(mock_session, "123456")
        self.assertEqual(auth_data["status"], "success")
        self.assertTrue(auth_data.get("isMock"))

    @override_settings(DEBUG=True, SMS_OTP_TEST_DOUBLE_ENABLED=True)
    @patch("apps.accounts.services.firebase_otp.load_firebase_config", return_value={})
    def test_invalid_otp_fails(self, _mock_config):
        mock_session = "mock_session_test_0766709535"
        with self.assertRaises(RuntimeError):
            verify_sms_otp(mock_session, "999999")

    @override_settings(
        DEBUG=False,
        SMS_OTP_TEST_DOUBLE_ENABLED=False,
        FIREBASE_API_KEY="AIzaSyRealProductionKeyForTest12345",
    )
    def test_mock_session_rejected_when_production_or_disabled(self):
        with self.assertRaises(RuntimeError):
            verify_sms_otp("mock_session_84988776655_attacker", "123456")


if __name__ == "__main__":
    unittest.main()
