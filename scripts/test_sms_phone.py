"""
Script kiem thu tinh nang SMS OTP voi so dien thoai cu the.
Ho tro kiem tra truc tiep tren moi truong dev/test (Console) hoac gui thuc te qua Vonage SMS API.
"""

import os
import subprocess
import sys

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Tu dong su dung python trong .venv cua du an neu dang chay bang Python he thong
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_python = os.path.join(project_root, ".venv", "Scripts", "python.exe")
if os.path.exists(venv_python) and os.path.normcase(sys.executable) != os.path.normcase(
    venv_python
):
    sys.exit(subprocess.call([venv_python] + sys.argv))

# Them thu muc goc vao sys.path
sys.path.insert(0, project_root)

# Thiet lap moi truong Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

import django  # noqa: E402
import environ  # noqa: E402

import config.settings.test as st  # noqa: E402

# Doc cac bien cau hinh tu file .env neu co
env = environ.Env()
env_file = os.path.join(project_root, ".env")
if os.path.exists(env_file):
    env.read_env(env_file)

# Dung SQLite in-memory de test doc lap khong anh huong db that
st.DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Kiem tra xem co cau hinh Vonage hay khong
vonage_key = env("VONAGE_API_KEY", default="")
vonage_secret = env("VONAGE_API_SECRET", default="")
vonage_from = env("VONAGE_FROM", default="Vonage APIs")
use_vonage = ("--vonage" in sys.argv) or (
    bool(vonage_key and vonage_secret) and "--console" not in sys.argv
)

if use_vonage and vonage_key and vonage_secret:
    st.SMS_BACKEND = "apps.accounts.services.sms.VonageSMSBackend"
    st.VONAGE_API_KEY = vonage_key
    st.VONAGE_API_SECRET = vonage_secret
    st.VONAGE_FROM = vonage_from
else:
    st.SMS_BACKEND = "apps.accounts.services.sms.ConsoleSMSBackend"

django.setup()

# Khoi tao bang co so du lieu trong memory
from django.core.management import call_command  # noqa: E402

call_command("migrate", "--run-syncdb", verbosity=0)

from django.core.cache import cache  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from apps.accounts.models import Account  # noqa: E402
from apps.accounts.services.auth import (  # noqa: E402
    confirm_password_reset_sms,
    confirm_register_sms,
    request_password_reset_sms,
    request_register_otp,
)
from apps.accounts.services.sms import (  # noqa: E402
    get_sms_backend,
    is_valid_phone_number,
    normalize_vietnamese_phone,
    send_sms,
)
from apps.customers.models import Customer  # noqa: E402


def run_phone_sms_test(raw_phone: str):
    # Xoa cache de reset throttle va cooldown
    cache.clear()

    active_backend = get_sms_backend().__class__.__name__

    print("=" * 65)
    print(f" KIEM THU CHUC NANG SMS OTP CHO SO DIEN THOAI: {raw_phone}")
    print(f" SMS BACKEND: {active_backend}")
    if active_backend == "VonageSMSBackend":
        print(f" -> Vonage Sender ID: {st.VONAGE_FROM}")
    else:
        print(" -> Che do: Console Simulator (In ra man hinh)")
    print("=" * 65)

    # 1. Kiem tra dinh dang & chuan hoa
    clean_phone = normalize_vietnamese_phone(raw_phone)
    valid = is_valid_phone_number(clean_phone)
    print("\n[1] Ket qua chuan hoa so dien thoai:")
    print(f"    - So ban dau  : {raw_phone}")
    print(f"    - So chuan hoa: {clean_phone}")
    print(f"    - Hop le      : {'CO [OK]' if valid else 'KHONG HOP LE [FAIL]'}")

    if not valid:
        print(
            "\n[X] So dien thoai khong hop le! Vui long nhap so di dong VN (vi du: 0766709535, +84766709535)."
        )
        return

    # Don dep tai khoan cu neu co de test kich ban dang ky moi
    Customer.objects.filter(phone=clean_phone).delete()
    Account.objects.filter(phone=clean_phone).delete()

    rf = RequestFactory()
    req = rf.post("/api/v1/auth/", REMOTE_ADDR="127.0.0.1")

    # 2. Test gui truc tiep SMS don gian
    print("\n[2] Gui tin nhan SMS mau (Direct dispatch):")
    send_sms(
        clean_phone,
        f"[CastraVision/Parking] Xin chao! Day la tin nhan test den so {clean_phone}.",
    )

    # 3. Test kich ban Dang ky tai khoan qua SMS OTP
    print("\n[3] Kich ban 1: YEU CAU MA OTP DANG KY TAI KHOAN")
    try:
        otp_reg = request_register_otp(req, clean_phone)
        print(f"    -> [SUCCESS] Da sinh va gui ma OTP dang ky: {otp_reg}")

        # Xac thuc OTP de hoan tat dang ky
        print("\n[4] Kich ban 1 (Tiep): XAC NHAN OTP DE HOAN TAT DANG KY")
        new_account, customer = confirm_register_sms(
            phone=clean_phone,
            otp=otp_reg,
            password="StrongPassword123!",
            full_name="Nguyen Van A",
        )
        print("    -> [SUCCESS] Da tao tai khoan thanh cong!")
        print(f"       + ID           : {new_account.id}")
        print(f"       + Phone        : {new_account.phone}")
        print(f"       + Role         : {new_account.role}")
        print(f"       + Customer Code: {customer.code}")
    except Exception as e:
        print(f"    -> [ERROR] {e}")

    # Xoa cooldown cache de test luon kich ban Quen mat khau ngay sau do
    cache.delete(f"cooldown:sms:reset:{clean_phone}")
    cache.delete(f"throttle:sms:reset:phone:{clean_phone}")

    # 4. Test kich ban Quen mat khau qua SMS OTP
    print("\n[5] Kich ban 2: QUEN MAT KHAU - GUI MA OTP")
    try:
        otp_forgot = request_password_reset_sms(req, clean_phone)
        print(f"    -> [SUCCESS] Da sinh va gui ma OTP quen mat khau: {otp_forgot}")

        if otp_forgot:
            print("\n[6] Kich ban 2 (Tiep): XAC NHAN OTP VA DAT MAT KHAU MOI")
            updated_account = confirm_password_reset_sms(
                phone=clean_phone,
                otp=otp_forgot,
                new_password="NewSecurePassword456!",
            )
            print(
                f"    -> [SUCCESS] Dat lai mat khau moi thanh cong cho {updated_account.phone}!"
            )
    except Exception as e:
        print(f"    -> [ERROR] {e}")

    print("\n" + "=" * 65)
    print(" HOAN THANH KIEM TRA TOAN BO CHUC NANG SMS OTP!")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    filtered_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    phone_input = filtered_args[0].strip() if filtered_args else "0766709535"
    run_phone_sms_test(phone_input)
