"""
Kiem thu tu dong toan dien tinh nang SMS OTP (Quen mat khau va Dang ky).
Chay doc lap khong phu thuoc vao viec PostgreSQL container co bat hay khong.
"""

import os
import subprocess
import sys

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

import config.settings.test as st  # noqa: E402

# Dung SQLite memory cho test suite doc lap
st.DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

django.setup()

from django.test.runner import DiscoverRunner  # noqa: E402

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("   DANG CHAY KIEM THU TU DONG CHUC NANG SMS OTP")
    print("   - Quen mat khau qua SMS OTP (Request & Confirm)")
    print("   - Dang ky tai khoan Khach hang qua SMS OTP (Request & Confirm)")
    print("   - Rate limiting, Cooldown 60s, Anti-brute force, Anti-enumeration")
    print("=" * 70 + "\n")

    runner = DiscoverRunner(verbosity=2)
    failures = runner.run_tests(["tests.accounts.test_sms_otp"])
    if failures:
        print("\n[!] CO TEST BI THAT BAI!\n")
        sys.exit(1)
    else:
        print("\n[V] TAT CA 26 TEST CASES DA HOAN THANH XUAT SAC!\n")
        sys.exit(0)
