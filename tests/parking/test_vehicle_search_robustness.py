"""
Boundary Stress Testing Suite for Vehicle Search Robustness.

Stress-test Dimensions:
1. SQL Injection & Operator Escaping:
   - Malicious injection payloads (' OR '1'='1, '; DROP TABLE, UNION SELECT, stacked queries).
   - LIKE/ILIKE wildcards (%, _, \\\\\\\\) and pattern DoS stress.
2. Unicode, Emoji, Unusual Whitespace, and Separators:
   - Emoji (🚗, 🚙, 🔥, 👨‍👩‍👧‍👦), complex multi code points, foreign languages.
   - Non-breaking spaces (\\u00a0), tabs, newlines, zero-width chars.
   - Unusual separators in license plate (43.K.860.50, 43--K--860--50, (43K) 860 50).
   - Unusual phone formats (+84 868 851 325, 84868851325, (+84) 868-851-325).
3. Extreme Lengths & Boundary Values:
   - 10,000 characters parameter stress (q, customer_name, phone, license_plate).
   - LIKE pattern DoS stress (%_ * 5,000).
   - Boundary checks: 1 char after trim -> 400, 2 chars after trim -> 200.
   - Pagination boundaries: page_size=0, page_size=-1, page_size=50 vs page_size=51.
4. Soft-Delete Leakage & Customer Anonymization:
   - Soft-deleted vehicles (deleted_at IS NOT NULL) never leak under any query.
   - Active vehicles belonging to soft-deleted customers never leak under any query.
   - Anonymized customer (is_anonymized = True) PII is strictly masked (no real name/phone).
   - Soft-deleted tickets and blacklist entries are strictly ignored.
5. Zero N+1 Queries & Scale Stress:
   - Batch hydration verified on 50 vehicles with active tickets, open sessions, and blacklist.
   - Query count invariance: O(1) database queries (<= 6 queries) regardless of result count.
6. Combinatorial & Edge Queries:
   - All 4 search parameters combined.
   - Punctuation-only queries.
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    PlateBlacklist,
    VehicleEntryExitLog,
)
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="verification_emp_m3@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_manager():
    mgr, _ = Account.objects.get_or_create(
        email="verification_mgr_m3@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="verification_cust_m3@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


# ---------------------------------------------------------------------------
# 1. SQL Injection & Operator Escaping Stress Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "' OR '1'='1",
        "' OR 1=1 --",
        "admin' --",
        "' OR ''='",
        "1' ORDER BY 1--+",
        "1' UNION SELECT NULL, NULL, NULL--",
    ],
)
def test_sql_injection_in_q_does_not_leak_all_records(auth_employee, payload):
    """Payload SQLi trong q không thể phá vỡ logic truy vấn hoặc làm rò rỉ toàn bộ CSDL."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/", {"q": payload})
    assert response.status_code == status.HTTP_200_OK
    # Không được trả về toàn bộ xe trong hệ thống
    total_vehicles = Vehicle.objects.filter(deleted_at__isnull=True).count()
    assert response.data["count"] < total_vehicles
    assert response.data["count"] == 0 or len(response.data["results"]) == 0


def test_sql_injection_drop_table_attempt(auth_employee):
    """Thử nghiệm tấn công '; DROP TABLE vehicle; --' trong customer_name."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    payload = "'; DROP TABLE vehicle; --"
    response = client.get("/api/v1/parking/vehicle-search/", {"customer_name": payload})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    # Bảng vehicle vẫn nguyên vẹn
    assert Vehicle.objects.count() > 0


def test_sql_injection_stacked_queries_sleep(auth_employee):
    """Thử nghiệm Time-based Blind SQLi (pg_sleep) trong license_plate."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    payload = "43K'; SELECT pg_sleep(3); --"
    response = client.get("/api/v1/parking/vehicle-search/", {"license_plate": payload})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0


def test_escape_like_wildcard_stress(auth_employee):
    """Ký tự đặc biệt LIKE (%, _, \\) được escape an toàn và không gây lỗi cú pháp hoặc tràn match."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    wildcard_payloads = [
        "%%%%",
        "____",
        "\\\\\\\\",
        "43%_K",
        "\\%\\_\\\\",
        "%43K%",
    ]
    for p in wildcard_payloads:
        response = client.get("/api/v1/parking/vehicle-search/", {"q": p})
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data


# ---------------------------------------------------------------------------
# 2. Unicode, Emoji, Unusual Whitespace, and Separators Stress Tests
# ---------------------------------------------------------------------------


def test_emoji_and_multilingual_inputs(auth_employee):
    """Hệ thống xử lý an toàn Emoji, ký tự đa ngôn ngữ mà không gây lỗi mã hóa UTF-8."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    emoji_queries = [
        "🚗🚙",
        "✨🔥🚗",
        "👨‍👩‍👧‍👦",  # Complex ZWJ sequence
        "Xe số 1 🚗",
        "日本語の車",
        "سيارة",
        "한국어",
    ]
    for eq in emoji_queries:
        response = client.get("/api/v1/parking/vehicle-search/", {"q": eq})
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data["results"], list)


def test_unusual_whitespace_handling(auth_employee):
    """Khoảng trắng đặc biệt (tab, newline, non-breaking space \\u00a0) được trim đúng quy cách."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1 ký tự sau khi trim tab và newline -> 400 Bad Request
    response = client.get("/api/v1/parking/vehicle-search/", {"q": "\t\n X \t\n"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"

    # Non-breaking space \u00a0 bọc hai đầu từ khóa hợp lệ -> 200 OK
    response_nbsp = client.get(
        "/api/v1/parking/vehicle-search/", {"q": "\u00a0\u00a043K\u00a0\u00a0"}
    )
    assert response_nbsp.status_code == status.HTTP_200_OK


def test_unusual_plate_separators_matching(auth_employee):
    """Các ký tự phân cách bất thường trong biển số vẫn khớp chính xác nhờ chuẩn hóa."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    # Xe mẫu trong seed: 43K-860.50 (norm: 43K86050)
    unusual_plates = [
        "43.K.860.50",
        "43--K--860--50",
        "43/K/860/50",
        "43*K*860*50",
        "(43K) 860 50",
        "43_K_860_50",
    ]
    for plate in unusual_plates:
        response = client.get(
            "/api/v1/parking/vehicle-search/", {"license_plate": plate}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1
        assert any(
            r["vehicle"]["license_plate_norm"] == "43K86050"
            for r in response.data["results"]
        )


def test_unusual_phone_formats_matching(auth_employee):
    """Các biến thể số điện thoại (+84, 84, dấu chấm, ngoặc) đều tìm thấy đúng khách hàng."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    # Số điện thoại mẫu: 0868851325
    phone_formats = [
        "+84868851325",
        "+84 868 851 325",
        "+84.868.851.325",
        "+84-868-851-325",
        "(+84) 868 851 325",
        "84868851325",
    ]
    for phone in phone_formats:
        response = client.get("/api/v1/parking/vehicle-search/", {"phone": phone})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] >= 1
        assert any(
            r["customer"]["phone"] == "0868851325" for r in response.data["results"]
        )


# ---------------------------------------------------------------------------
# 3. Extreme Lengths & Boundary Values Stress Tests
# ---------------------------------------------------------------------------


def test_extreme_length_10000_chars(auth_employee):
    """Tham số có độ dài cực lớn (10,000 ký tự) không gây quá tải hệ thống hay tràn bộ nhớ."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    huge_q = "X" * 10000
    response = client.get("/api/v1/parking/vehicle-search/", {"q": huge_q})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0


def test_extreme_pattern_dos_stress(auth_employee):
    """Mẫu LIKE phức tạp lặp lại (%_ * 2000) không gây ReDoS hoặc làm chậm PostgreSQL."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    dos_pattern = "%_" * 2000
    response = client.get("/api/v1/parking/vehicle-search/", {"q": dos_pattern})
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0


@pytest.mark.parametrize(
    "param_name",
    ["q", "customer_name", "phone", "license_plate"],
)
def test_boundary_single_char_after_trim_rejected(auth_employee, param_name):
    """Tham số có đúng 1 ký tự sau khi trim đều bị từ chối với 400 PROP-GEN-P01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/", {param_name: "   A   "})
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert param_name in response.data["details"]


@pytest.mark.parametrize(
    "param_name,val",
    [
        ("q", "  43  "),
        ("customer_name", "  An  "),
        ("phone", "  08  "),
        ("license_plate", "  51  "),
    ],
)
def test_boundary_two_chars_after_trim_accepted(auth_employee, param_name, val):
    """Tham số có đúng 2 ký tự sau khi trim được chấp nhận (200 OK)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/", {param_name: val})
    assert response.status_code == status.HTTP_200_OK


def test_pagination_boundary_limits(auth_employee):
    """Kiểm tra biên phân trang: page_size=0, page_size=-1, page_size=51 bị từ chối; page_size=50 được chấp nhận."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # page_size = 0
    res0 = client.get(
        "/api/v1/parking/vehicle-search/", {"q": "Toyota", "page_size": 0}
    )
    assert res0.status_code == status.HTTP_400_BAD_REQUEST

    # page_size = -5
    res_neg = client.get(
        "/api/v1/parking/vehicle-search/", {"q": "Toyota", "page_size": -5}
    )
    assert res_neg.status_code == status.HTTP_400_BAD_REQUEST

    # page_size = 51 (> max_page_size 50)
    res51 = client.get(
        "/api/v1/parking/vehicle-search/", {"q": "Toyota", "page_size": 51}
    )
    assert res51.status_code == status.HTTP_400_BAD_REQUEST

    # page_size = 50 (hợp lệ)
    res50 = client.get(
        "/api/v1/parking/vehicle-search/", {"q": "Toyota", "page_size": 50}
    )
    assert res50.status_code == status.HTTP_200_OK
    assert res50.data["page_size"] == 50


# ---------------------------------------------------------------------------
# 4. Soft-Delete Leakage & Customer Anonymization Stress Tests
# ---------------------------------------------------------------------------


def test_soft_deleted_vehicle_never_leaks_under_any_query_param(auth_employee):
    """Phương tiện bị xóa mềm tuyệt đối không bao giờ rò rỉ trong bất kỳ tiêu chí tìm kiếm nào."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-LK-01",
        full_name="Đặng Kiểm Tra Xóa Mềm",
        phone="0977889900",
        identity_card_number="049090998811",
    )
    v = Vehicle.objects.create(
        code="XE-LK-01",
        license_plate="43Z-999.88",
        license_plate_norm="43Z99988",
        model_name="Innova",
        vehicle_type=vtype,
        customer=cust,
        deleted_at=timezone.now(),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    test_queries = [
        {"q": v.license_plate},
        {"q": v.license_plate_norm},
        {"q": cust.full_name},
        {"q": cust.phone},
        {"license_plate": v.license_plate},
        {"customer_name": cust.full_name},
        {"phone": cust.phone},
    ]

    for q_params in test_queries:
        res = client.get("/api/v1/parking/vehicle-search/", q_params)
        assert res.status_code == status.HTTP_200_OK
        returned_plates = [
            item["vehicle"]["license_plate_norm"] for item in res.data["results"]
        ]
        assert v.license_plate_norm not in returned_plates


def test_soft_deleted_customer_vehicle_never_leaks(auth_employee):
    """Xe có deleted_at IS NULL nhưng thuộc khách hàng đã bị xóa mềm tuyệt đối không rò rỉ."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-LK-02",
        full_name="Ngô Đã Bị Xóa Mềm",
        phone="0988776655",
        identity_card_number="049090998822",
        deleted_at=timezone.now(),
    )
    v = Vehicle.objects.create(
        code="XE-LK-02",
        license_plate="43Z-888.77",
        license_plate_norm="43Z88877",
        model_name="Corolla",
        vehicle_type=vtype,
        customer=cust,
        deleted_at=None,  # Xe chưa bị xóa, nhưng chủ xe đã bị xóa
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    test_queries = [
        {"q": v.license_plate},
        {"q": cust.full_name},
        {"license_plate": v.license_plate},
        {"customer_name": cust.full_name},
    ]

    for q_params in test_queries:
        res = client.get("/api/v1/parking/vehicle-search/", q_params)
        assert res.status_code == status.HTTP_200_OK
        returned_plates = [
            item["vehicle"]["license_plate_norm"] for item in res.data["results"]
        ]
        assert v.license_plate_norm not in returned_plates


def test_anonymized_customer_pii_strictly_masked(auth_employee):
    """Khách hàng ẩn danh (is_anonymized=True) tuyệt đối không lộ họ tên thật và số điện thoại."""
    vtype = VehicleType.objects.first()
    real_name = "Trần Thị Tuyệt Mật"
    real_phone = "0934567890"

    cust = Customer.objects.create(
        code="KH-ANON01",
        full_name=real_name,
        phone=real_phone,
        identity_card_number="049090998833",
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )
    v = Vehicle.objects.create(
        code="XE-ANON01",
        license_plate="43Z-777.66",
        license_plate_norm="43Z77766",
        model_name="Cross",
        vehicle_type=vtype,
        customer=cust,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Tìm kiếm theo biển số xe
    res = client.get(
        "/api/v1/parking/vehicle-search/", {"license_plate": v.license_plate}
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.data["count"] == 1
    item = res.data["results"][0]

    cust_res = item["customer"]
    assert cust_res["is_anonymized"] is True
    assert cust_res["full_name"] == "Khách hàng ẩn danh"
    assert cust_res["phone"] is None

    # Quét toàn bộ nội dung response JSON để đảm bảo PII không lộ ở bất kỳ field nào
    raw_content = str(res.content, encoding="utf-8")
    assert real_name not in raw_content
    assert real_phone not in raw_content


def test_soft_deleted_ticket_and_inactive_blacklist_ignored(auth_employee):
    """Vé đã xóa mềm và blacklist không hoạt động/đã xóa mềm không được hiển thị là active."""
    vtype = VehicleType.objects.first()
    ttype = TicketType.objects.first()

    cust = Customer.objects.create(
        code="KH-TK01",
        full_name="Bùi Kiểm Tra Vé",
        phone="0912999888",
        identity_card_number="049090998844",
    )
    v = Vehicle.objects.create(
        code="XE-TK01",
        license_plate="43Z-666.55",
        license_plate_norm="43Z66655",
        model_name="Camry",
        vehicle_type=vtype,
        customer=cust,
    )

    # Tạo vé nhưng đã hết hạn và bị xóa mềm (tuân thủ ck_ticket_delete_only_expired)
    used_slots = set(
        Ticket.objects.filter(deleted_at__isnull=True).values_list("slot_id", flat=True)
    )
    slot = (
        ParkingSlot.objects.filter(
            deleted_at__isnull=True,
            allowed_vehicle_types__vehicle_type=vtype,
        )
        .exclude(id__in=used_slots)
        .first()
    )
    t_end = timezone.now() - timezone.timedelta(days=1)
    t_start = timezone.now() - timezone.timedelta(days=30)
    Ticket.objects.create(
        code="TK-IGN-01",
        customer=cust,
        vehicle=v,
        slot=slot,
        ticket_type=ttype,
        price=100000,
        status="ACTIVE",
        effective_from=t_start,
        effective_to=t_end,
        deleted_at=timezone.now(),  # Soft deleted after expiration
    )

    # Tạo blacklist nhưng is_active=False
    PlateBlacklist.objects.create(
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        reason="Nghi vấn cũ",
        is_active=False,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    res = client.get(
        "/api/v1/parking/vehicle-search/", {"license_plate": v.license_plate}
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.data["count"] == 1
    item = res.data["results"][0]

    assert item["active_ticket"] is None
    assert item["is_blacklisted"] is False


# ---------------------------------------------------------------------------
# 5. Zero N+1 Queries & Scale Stress Tests (50 Vehicles)
# ---------------------------------------------------------------------------


def test_zero_n_plus_one_scale_50_vehicles(
    auth_employee, django_assert_max_num_queries
):
    """
    Stress test Zero N+1 trên quy mô tối đa 50 xe trong 1 trang:
    - Tạo 50 xe thuộc 50 khách hàng.
    - Tạo phiên đỗ mở cho 20 xe.
    - Tạo vé active cho 30 xe.
    - Tạo danh sách đen cho 10 xe.
    - Đảm bảo toàn bộ quá trình xác thực + phân trang + batch hydration hoàn tất trong <= 6 queries.
    """
    vtype = VehicleType.objects.first()
    ttype = TicketType.objects.first()
    gate = ParkingGate.objects.filter(is_active=True).first()
    used_slots = set(
        Ticket.objects.filter(deleted_at__isnull=True).values_list("slot_id", flat=True)
    )
    free_slots = list(
        ParkingSlot.objects.filter(
            deleted_at__isnull=True,
            status="AVAILABLE",
            allowed_vehicle_types__vehicle_type=vtype,
        )
        .exclude(id__in=used_slots)
        .distinct()[:50]
    )

    now = timezone.now()
    created_vehicles = []

    for i in range(50):
        cust = Customer.objects.create(
            code=f"KH-S{i:04d}",
            full_name=f"Khách Hàng Quy Mô {i:03d}",
            phone=f"098100{i:04d}",
            identity_card_number=f"049090{i:06d}",
        )
        plate_raw = f"51S-{i:03d}.99"
        plate_norm = f"51S{i:03d}99"
        v = Vehicle.objects.create(
            code=f"XE-S{i:04d}",
            license_plate=plate_raw,
            license_plate_norm=plate_norm,
            model_name=f"ScaleCar-{i}",
            vehicle_type=vtype,
            customer=cust,
        )
        created_vehicles.append(v)

        # 20 xe đầu tiên có phiên đỗ mở (slot=None để biểu thị open parking không cố định)
        if i < 20:
            VehicleEntryExitLog.objects.create(
                session_code=f"#PK-STR-{i:04d}",
                license_plate=plate_raw,
                license_plate_norm=plate_norm,
                vehicle=v,
                entry_gate=gate,
                slot=None,
                entry_time=now - timezone.timedelta(hours=2),
                recognition_source="AI",
                ai_confidence=95.0,
                review_status="AUTO",
            )

        # 30 xe tiếp theo có vé active (gán slot riêng biệt)
        if 15 <= i < 45:
            Ticket.objects.create(
                code=f"TK-S{i:04d}",
                customer=cust,
                vehicle=v,
                slot=free_slots[i],
                ticket_type=ttype,
                price=500000,
                status="ACTIVE",
                effective_from=now - timezone.timedelta(days=5),
                effective_to=now + timezone.timedelta(days=25),
            )

        # 10 xe trong danh sách đen
        if i >= 40:
            PlateBlacklist.objects.create(
                license_plate=plate_raw,
                license_plate_norm=plate_norm,
                reason="Kiểm tra tải",
                is_active=True,
            )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Bắt buộc số lượng queries <= 6 bất kể có 50 bản ghi phức tạp
    with django_assert_max_num_queries(6):
        response = client.get(
            "/api/v1/parking/vehicle-search/",
            {"q": "Khách Hàng Quy Mô", "page_size": 50},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 50
        assert len(response.data["results"]) == 50

    # Kiểm tra tính toàn vẹn của batch hydration
    results = response.data["results"]
    parked_count = sum(1 for r in results if r["currently_parked"])
    active_ticket_count = sum(1 for r in results if r["active_ticket"] is not None)
    blacklist_count = sum(1 for r in results if r["is_blacklisted"])

    assert parked_count == 20
    assert active_ticket_count == 30
    assert blacklist_count == 10


# ---------------------------------------------------------------------------
# 6. Combinatorial Search & Conflicting Conditions Stress Tests
# ---------------------------------------------------------------------------


def test_combinatorial_all_four_parameters(auth_employee):
    """Tìm kiếm kết hợp cả 4 tham số đồng thời (q, customer_name, phone, license_plate)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    # Khớp xe mẫu 43K-860.50 của Trịnh Xuân Trường (0868851325)
    params = {
        "q": "43K",
        "customer_name": "Trường",
        "phone": "0868851325",
        "license_plate": "43K-860.50",
    }
    res = client.get("/api/v1/parking/vehicle-search/", params)
    assert res.status_code == status.HTTP_200_OK
    assert res.data["count"] == 1
    assert res.data["results"][0]["vehicle"]["license_plate_norm"] == "43K86050"


def test_conflicting_parameters_return_empty(auth_employee):
    """Điều kiện mâu thuẫn (tên khách hàng A nhưng số điện thoại khách hàng B) trả về 200 rỗng."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    params = {
        "customer_name": "Trịnh Xuân Trường",
        "phone": "0999999999",  # Số không thuộc khách hàng này
    }
    res = client.get("/api/v1/parking/vehicle-search/", params)
    assert res.status_code == status.HTTP_200_OK
    assert res.data["count"] == 0
    assert res.data["results"] == []
    assert res.data["message"] == "Không tìm thấy dữ liệu trùng khớp"


def test_punctuation_only_search_safe(auth_employee):
    """Tìm kiếm bằng chuỗi ký tự chỉ gồm dấu câu không gây lỗi hệ thống."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    punctuation_queries = ["---", "...", "???", ";;;", ",,,", "!!!", "@@@"]
    for q in punctuation_queries:
        res = client.get("/api/v1/parking/vehicle-search/", {"q": q})
        assert res.status_code == status.HTTP_200_OK
        assert "results" in res.data
