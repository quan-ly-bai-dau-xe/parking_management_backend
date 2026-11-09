import json
import os
import unittest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
import django
django.setup()

from apps.accounts.services.firebase_otp import format_phone_number, send_sms_otp, verify_sms_otp

class FirebaseOTPServiceTests(unittest.TestCase):
    def test_format_phone_number(self):
        self.assertEqual(format_phone_number("0766709535"), "+84766709535")
        self.assertEqual(format_phone_number("+84766709535"), "+84766709535")
        self.assertEqual(format_phone_number("84766709535"), "+84766709535")
        self.assertEqual(format_phone_number("076 670-9535"), "+84766709535")

    def test_mock_session_verify(self):
        mock_session = "mock_session_test_0766709535"
        auth_data = verify_sms_otp(mock_session, "123456")
        self.assertEqual(auth_data["status"], "success")
        self.assertTrue(auth_data.get("isMock"))

    def test_invalid_otp_fails(self):
        mock_session = "mock_session_test_0766709535"
        with self.assertRaises(RuntimeError):
            verify_sms_otp(mock_session, "999999")

if __name__ == "__main__":
    unittest.main()
