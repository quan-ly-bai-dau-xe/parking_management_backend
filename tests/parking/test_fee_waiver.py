"""
Integration and edge-case tests for Fee Waiver during Check-Out per TL-58 and TL-59.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.tickets.models import Payment

pytestmark = pytest.mark.django_db


def unique_session_code():
    return f"#PK-WV-{uuid.uuid4().hex[:6].upper()}"


@pytest.fixture
def auth_employee():
    emp = Account.objects.filter(role="EMPLOYEE", is_active=True).first()
    if not emp:
        emp = Account.objects.get(email="luong.mai.phuong@example.org")
    return emp


@pytest.fixture
def auth_manager():
    mgr = Account.objects.filter(role="MANAGER", is_active=True).first()
    if not mgr:
        mgr = Account.objects.get(email="hoang.dinh.khang@example.com")
    return mgr


@pytest.fixture
def auth_customer():
    cust = Account.objects.filter(role="CUSTOMER", is_active=True).first()
    if not cust:
        cust = Account.objects.get(email="trinh.xuan.truong@example.com")
    return cust


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test Waiver", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test Waiver", direction="OUT", is_active=True
        )
    return gate


@pytest.fixture
def open_transient_session(in_gate):
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-WAIVER-01",
        license_plate="51H-888.99",
        license_plate_norm="51H88899",
        entry_time=now - timedelta(hours=3),  # 3 hours = 30,000 VND
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    return session


# ==============================================================================
# SECTION 1: CORE FEE WAIVER & RBAC TESTS
# ==============================================================================


def test_fee_waiver_employee_forbidden(auth_employee, out_gate, open_transient_session):
    """Nhân viên (EMPLOYEE) yêu cầu miễn cước -> 403 Forbidden PROP-4.5.1-P18."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    payload = {
        "session_code": open_transient_session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": "Sự cố kỹ thuật",
    }
    response = client.post(
        "/api/v1/parking/sessions/check-out/", payload, format="json"
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "PROP-4.5.1-P18"
    assert "Quản lý" in response.data["message"]


def test_fee_waiver_manager_missing_reason_rejected(
    auth_manager, out_gate, open_transient_session
):
    """Quản lý (MANAGER) gửi waive_fee=True nhưng waiver_reason rỗng -> 400 Bad Request PROP-4.5.1-P19."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    payload = {
        "session_code": open_transient_session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": "   ",
    }
    response = client.post(
        "/api/v1/parking/sessions/check-out/", payload, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P19"


def test_fee_waiver_manager_success_with_audit_trail(
    auth_manager, out_gate, open_transient_session
):
    """
    Quản lý (MANAGER) miễn cước thành công:
    - 200 OK
    - fee_amount = 0.00
    - payment = None
    - Không có Payment record trong DB
    - session.notes ghi chú kiểm toán
    - ActivityLog được tạo với action SESSION_CHECK_OUT_WAIVED
    """
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    waiver_reason_text = "Sự cố camera nhận diện không đọc được thẻ xe vé tháng"
    payload = {
        "session_code": open_transient_session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": waiver_reason_text,
        "notes": "Xe ra ca sáng",
    }

    initial_payment_count = Payment.objects.count()
    response = client.post(
        "/api/v1/parking/sessions/check-out/", payload, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data

    # Kiểm tra session trong response
    assert Decimal(str(data["session"]["fee_amount"])) == Decimal("0.00")
    assert data["payment"] is None
    assert Payment.objects.count() == initial_payment_count

    # Kiểm tra session.notes có vết kiểm toán
    notes_in_resp = data["session"]["notes"]
    assert "[MIỄN CƯỚC ĐẶC CÁCH]" in notes_in_resp
    assert waiver_reason_text in notes_in_resp
    assert auth_manager.email in notes_in_resp

    # Kiểm tra DB session được đóng
    open_transient_session.refresh_from_db()
    assert open_transient_session.exit_time is not None
    assert open_transient_session.fee_amount == Decimal("0.00")
    assert waiver_reason_text in open_transient_session.notes

    # Kiểm tra ActivityLog
    log = ActivityLog.objects.filter(
        action="SESSION_CHECK_OUT_WAIVED",
        entity_id=open_transient_session.id,
    ).first()
    assert log is not None
    assert log.actor_account == auth_manager
    assert waiver_reason_text in log.message
    assert auth_manager.email in log.message


def test_fee_waiver_false_backward_compatible(auth_employee, out_gate, in_gate):
    """Khi waive_fee=False: cước phí tính bình thường, đòi payment_method khi fee > 0."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-NORMAL-01",
        license_plate="51H-777.66",
        license_plate_norm="51H77766",
        entry_time=now - timedelta(hours=2),  # 2 hours = 20,000 VND
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Không truyền payment_method khi waive_fee=False -> 400 PROP-4.5.1-P09
    payload_missing_payment = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": False,
    }
    resp1 = client.post(
        "/api/v1/parking/sessions/check-out/", payload_missing_payment, format="json"
    )
    assert resp1.status_code == status.HTTP_400_BAD_REQUEST
    assert resp1.data["code"] == "PROP-4.5.1-P09"

    # Truyền payment_method hợp lệ -> 200 OK và tạo Payment record
    payload_valid = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "payment_method": "CASH",
        "waive_fee": False,
    }
    resp2 = client.post(
        "/api/v1/parking/sessions/check-out/", payload_valid, format="json"
    )
    assert resp2.status_code == status.HTTP_200_OK
    assert Decimal(str(resp2.data["session"]["fee_amount"])) == Decimal("20000.00")
    assert resp2.data["payment"] is not None
    assert Decimal(str(resp2.data["payment"]["amount"])) == Decimal("20000.00")


# ==============================================================================
# SECTION 2: DEFENSIVE AUTHORIZATION & INPUT VALIDATION
# ==============================================================================


def test_fee_waiver_customer_bypass_attempt(auth_customer, out_gate, in_gate):
    """
    Tài khoản CUSTOMER cố tình gửi request check-out kèm waive_fee=True.
    Kỳ vọng: Chặn ngay ở tầng View permission (IsEmployeeOrManager) -> 403 Forbidden.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-CUST-WAIVE",
        license_plate="51K-CUST.01",
        license_plate_norm="51KCUST01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_customer)

    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": "Tôi là khách VIP muốn miễn phí",
    }
    resp = client.post("/api/v1/parking/sessions/check-out/", payload, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "MSG-4.2-M01"


def test_fee_waiver_employee_bypass_attempt_prop_18(auth_employee, out_gate, in_gate):
    """
    Nhân viên EMPLOYEE cố tình gửi waive_fee=True.
    Kỳ vọng: 403 Forbidden với mã nghiệp vụ PROP-4.5.1-P18.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-EMP-WAIVE",
        license_plate="51K-EMP.01",
        license_plate_norm="51KEMP01",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": "Nhân viên tự ý miễn",
    }
    resp = client.post("/api/v1/parking/sessions/check-out/", payload, format="json")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "PROP-4.5.1-P18"


def test_fee_waiver_reason_empty_and_whitespace(auth_manager, out_gate, in_gate):
    """
    Quản lý (MANAGER) gửi waive_fee=True nhưng waiver_reason là None, rỗng, hoặc toàn dấu cách.
    Kỳ vọng: 400 Bad Request PROP-4.5.1-P19.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-EMPTY-REASON",
        license_plate="51K-REASON.01",
        license_plate_norm="51KREASON01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    # 1. Rỗng hoàn toàn
    resp1 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "",
        },
        format="json",
    )
    assert resp1.status_code == status.HTTP_400_BAD_REQUEST
    assert resp1.data["code"] == "PROP-4.5.1-P19"

    # 2. Toàn dấu cách
    resp2 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "      ",
        },
        format="json",
    )
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert resp2.data["code"] == "PROP-4.5.1-P19"


def test_fee_waiver_reason_length_limits(auth_manager, out_gate, in_gate):
    """
    - Chuỗi vượt quá 255 ký tự (256 ký tự) -> 400 DRF Serializer Error
    - Chuỗi chính xác 255 ký tự -> 200 OK thành công
    """
    now = timezone.now()
    session1 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-LEN-256",
        license_plate="51K-LEN.256",
        license_plate_norm="51KLEN256",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    # 256 ký tự
    long_reason_256 = "A" * 256
    resp_too_long = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session1.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": long_reason_256,
        },
        format="json",
    )
    assert resp_too_long.status_code == status.HTTP_400_BAD_REQUEST
    assert "waiver_reason" in str(resp_too_long.data)

    # 255 ký tự chuẩn
    session2 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-LEN-255",
        license_plate="51K-LEN.255",
        license_plate_norm="51KLEN255",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    valid_reason_255 = "B" * 255
    resp_valid_255 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session2.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": valid_reason_255,
        },
        format="json",
    )
    assert resp_valid_255.status_code == status.HTTP_200_OK
    session2.refresh_from_db()
    assert session2.exit_time is not None
    assert session2.fee_amount == Decimal("0.00")


def test_fee_waiver_special_characters_and_injection_safety(
    auth_manager, out_gate, in_gate
):
    """
    Truyền lý do miễn phí chứa ký tự XSS, SQL Injection string, và Unicode/Emoji.
    Lưu trữ an toàn, không bị lỗi cú pháp, ActivityLog lưu nguyên vẹn.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-INJECTION",
        license_plate="51K-INJ.01",
        license_plate_norm="51KINJ01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    safe_reason = (
        "<script>alert('xss')</script> '; DROP TABLE test; -- 🚗 Sự cố camera 🛠️"
    )
    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": safe_reason,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK

    session.refresh_from_db()
    assert safe_reason in session.notes
    assert session.fee_amount == Decimal("0.00")

    log = ActivityLog.objects.filter(
        action="SESSION_CHECK_OUT_WAIVED", entity_id=session.id
    ).first()
    assert log is not None
    assert safe_reason in log.message


def test_fee_waiver_false_cannot_sneak_without_payment_method(
    auth_manager, out_gate, in_gate
):
    """
    Gửi waive_fee=False nhưng có kèm waiver_reason và không kèm payment_method.
    Kỳ vọng: 400 Bad Request PROP-4.5.1-P09 (Bắt buộc phương thức thanh toán).
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-SNEAK",
        license_plate="51K-SNEAK.01",
        license_plate_norm="51KSNEAK01",
        entry_time=now - timedelta(hours=2),  # 2 hours = 20,000 VND
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": False,
            "waiver_reason": "Cố tình bỏ qua thanh toán",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-4.5.1-P09"


# ==============================================================================
# SECTION 3: CONCURRENCY & RACE CONDITIONS
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_double_checkout_prevented_by_select_for_update(
    auth_manager, out_gate, in_gate
):
    """
    Hai yêu cầu check-out đồng thời gửi đến cùng một phiên đỗ (1 waiver, 1 thường).
    Cơ chế select_for_update trong transaction.atomic() đảm bảo:
    - Đúng 1 yêu cầu thành công (HTTP 200).
    - Yêu cầu thứ 2 bị chặn với HTTP 409 Conflict (PROP-4.5.1-P10: Phiên đỗ xe này đã được kết thúc trước đó).
    - Không thể double-checkout hoặc sinh duplicate payment.
    """
    now = timezone.now()
    unique_suffix = uuid.uuid4().hex[:6].upper()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-CC-{unique_suffix}",
        license_plate=f"51K-CC.{unique_suffix[:4]}",
        license_plate_norm=f"51KCC{unique_suffix[:4]}",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    def do_checkout_waiver():
        connection.close()
        try:
            client = APIClient()
            client.force_authenticate(user=auth_manager)
            return client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session.session_code,
                    "exit_gate_id": out_gate.id,
                    "waive_fee": True,
                    "waiver_reason": "Thao tác đồng thời 1",
                },
                format="json",
            )
        finally:
            connection.close()

    def do_checkout_normal():
        connection.close()
        try:
            client = APIClient()
            client.force_authenticate(user=auth_manager)
            return client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session.session_code,
                    "exit_gate_id": out_gate.id,
                    "payment_method": "CASH",
                    "waive_fee": False,
                },
                format="json",
            )
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(do_checkout_waiver)
        future2 = executor.submit(do_checkout_normal)
        res1 = future1.result()
        res2 = future2.result()

    statuses = [res1.status_code, res2.status_code]
    assert 200 in statuses, f"Phải có 1 request 200 OK, kết quả: {statuses}"
    assert 409 in statuses, f"Request còn lại phải bị 409 Conflict, kết quả: {statuses}"

    err_res = res1 if res1.status_code == 409 else res2
    assert err_res.data["code"] == "PROP-4.5.1-P10"


# ==============================================================================
# SECTION 4: PAYMENT METHOD ENFORCEMENT & ACTIVITYLOG VERIFICATION
# ==============================================================================


def test_normal_checkout_missing_payment_method_raises_400_prop_09(
    auth_employee, in_gate, out_gate
):
    """Khi waive_fee=False và cước phí > 0: thiếu payment_method -> 400 PROP-4.5.1-P09."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-NOPAY.01",
        license_plate_norm="51KNOPAY01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": False,
    }
    resp = client.post("/api/v1/parking/sessions/check-out/", payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-4.5.1-P09"


def test_normal_checkout_invalid_payment_methods_rejected(
    auth_employee, in_gate, out_gate
):
    """Các phương thức thanh toán không được hỗ trợ (MOMO, CREDIT_CARD, ZALOPAY) hoặc None -> 400."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-INVPAY.01",
        license_plate_norm="51KINVPAY01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Trường hợp payment_method là None -> PROP-4.5.1-P09
    payload_none = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "payment_method": None,
        "waive_fee": False,
    }
    resp_none = client.post(
        "/api/v1/parking/sessions/check-out/", payload_none, format="json"
    )
    assert resp_none.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_none.data["code"] == "PROP-4.5.1-P09"

    # 2. Trường hợp payment_method ngoài choices -> 400 PROP-GEN-P01
    for invalid_method in ["MOMO", "CREDIT_CARD", "ZALOPAY"]:
        payload = {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": invalid_method,
            "waive_fee": False,
        }
        resp = client.post(
            "/api/v1/parking/sessions/check-out/", payload, format="json"
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "PROP-GEN-P01"


def test_normal_checkout_valid_payment_methods_succeed(
    auth_employee, in_gate, out_gate
):
    """Các phương thức hợp lệ: CASH, VIETQR -> 200 OK và tạo Payment status=PAID."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    for method in ["CASH", "VIETQR"]:
        now = timezone.now()
        session = VehicleEntryExitLog.objects.create(
            session_code=unique_session_code(),
            license_plate=f"51K-{method}.01",
            license_plate_norm=f"51K{method}01",
            entry_time=now - timedelta(hours=2),  # 2 hours = 20,000 VND
            entry_gate=in_gate,
            recognition_source="AI",
            review_status="AUTO",
        )
        payload = {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": method,
            "waive_fee": False,
        }
        resp = client.post(
            "/api/v1/parking/sessions/check-out/", payload, format="json"
        )
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["payment"] is not None
        assert resp.data["payment"]["method"] == method
        assert Decimal(str(resp.data["payment"]["amount"])) == Decimal("20000.00")
        assert resp.data["payment"]["status"] == "PAID"

        pmt = Payment.objects.get(session_id=session.id)
        assert pmt.status == "PAID"
        assert pmt.amount == Decimal("20000.00")
        assert pmt.method == method


def test_manager_waive_fee_no_payment_record_and_zero_fee_in_db(
    auth_manager, in_gate, out_gate
):
    """Quản lý miễn cước: Payment record KHÔNG được tạo, fee_amount=0.00 trong DB."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-WAIVE.99",
        license_plate_norm="51KWAIVE99",
        entry_time=now - timedelta(hours=5),  # Bình thường là 50.000 VNĐ
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    initial_payments_count = Payment.objects.count()
    client = APIClient()
    client.force_authenticate(user=auth_manager)

    waiver_reason = "Sự cố kỹ thuật: xe vé tháng không quét được thẻ tại barrier"
    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": waiver_reason,
        "notes": "Ghi chú nhân viên",
    }
    resp = client.post("/api/v1/parking/sessions/check-out/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data

    # 1. Phản hồi API
    assert data["payment"] is None
    assert Decimal(str(data["session"]["fee_amount"])) == Decimal("0.00")

    # 2. Database: KHÔNG có Payment record nào được tạo
    final_payments_count = Payment.objects.count()
    assert final_payments_count == initial_payments_count
    assert not Payment.objects.filter(session_id=session.id).exists()

    # 3. Database: session.fee_amount trong database là 0.00
    session.refresh_from_db()
    assert session.exit_time is not None
    assert session.fee_amount == Decimal("0.00")

    # 4. Database: session.notes lưu vết kiểm toán
    assert "[MIỄN CƯỚC ĐẶC CÁCH]" in session.notes
    assert waiver_reason in session.notes
    assert auth_manager.email in session.notes


def test_manager_waive_fee_ignores_redundant_payment_method(
    auth_manager, in_gate, out_gate
):
    """Nếu request vừa gửi waive_fee=True vừa gửi payment_method='CASH': vẫn không tạo Payment record."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-WAIVE.RED",
        license_plate_norm="51KWAIVERED",
        entry_time=now - timedelta(hours=3),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)

    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
        "waiver_reason": "Xe khách VIP của tòa nhà",
        "payment_method": "CASH",  # Thừa
    }
    resp = client.post("/api/v1/parking/sessions/check-out/", payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["payment"] is None
    assert not Payment.objects.filter(session_id=session.id).exists()
    session.refresh_from_db()
    assert session.fee_amount == Decimal("0.00")


def test_unauthorized_fee_waiver_does_not_modify_session(
    auth_employee, auth_customer, in_gate, out_gate
):
    """Khi bị từ chối quyền miễn cước (EMPLOYEE hoặc CUSTOMER), phiên đỗ không bị đóng hay sửa fee."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-UNAUTH.01",
        license_plate_norm="51KUNAUTH01",
        entry_time=now - timedelta(hours=3),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    # 1. Thử bởi EMPLOYEE -> 403 PROP-4.5.1-P18
    client_emp = APIClient()
    client_emp.force_authenticate(user=auth_employee)
    resp1 = client_emp.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "Nhân viên tự duyệt",
        },
        format="json",
    )
    assert resp1.status_code == status.HTTP_403_FORBIDDEN
    assert resp1.data["code"] == "PROP-4.5.1-P18"

    session.refresh_from_db()
    assert session.exit_time is None
    assert session.fee_amount == Decimal("0.00")

    # 2. Thử bởi CUSTOMER -> 403 MSG-4.2-M01
    client_cust = APIClient()
    client_cust.force_authenticate(user=auth_customer)
    resp2 = client_cust.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "Khách hàng tự miễn phí",
        },
        format="json",
    )
    assert resp2.status_code == status.HTTP_403_FORBIDDEN
    assert resp2.data["code"] == "MSG-4.2-M01"

    session.refresh_from_db()
    assert session.exit_time is None
    assert session.fee_amount == Decimal("0.00")


def test_activity_log_recorded_on_fee_waiver(auth_manager, in_gate, out_gate):
    """Khi waive_fee=True: ActivityLog có action='SESSION_CHECK_OUT_WAIVED'."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-ACTLOG.01",
        license_plate_norm="51KACTLOG01",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    waiver_reason = "Khách vip hội nghị tầng 5"
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": waiver_reason,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK

    log_entry = ActivityLog.objects.filter(
        action="SESSION_CHECK_OUT_WAIVED",
        entity_type="vehicle_entry_exit_log",
        entity_id=session.id,
    ).first()

    assert log_entry is not None, "ActivityLog phải tồn tại bản ghi tương ứng"
    assert log_entry.actor_account == auth_manager
    assert session.session_code in log_entry.message
    assert session.license_plate in log_entry.message
    assert waiver_reason in log_entry.message
    assert auth_manager.email in log_entry.message


def test_no_waive_activity_log_on_normal_checkout(auth_employee, in_gate, out_gate):
    """Khi check-out bình thường: KHÔNG tạo ActivityLog với action='SESSION_CHECK_OUT_WAIVED'."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=unique_session_code(),
        license_plate="51K-NOWAIVE.01",
        license_plate_norm="51KNOWAIVE01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "CASH",
            "waive_fee": False,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK

    assert not ActivityLog.objects.filter(
        action="SESSION_CHECK_OUT_WAIVED",
        entity_id=session.id,
    ).exists()
