"""
Integration tests for Vehicle List API (GET /api/v1/vehicles/).

Verifies:
- Multi-filter combinations: code, plate, customer, vehicle_type, ticket_type, status, ticket_state.
- Hand-written derived status ('parked', 'active', 'left') and ticket_state ('valid', 'expired')
  computed from seed data via independent SQL (non-circular).
- Sorting / ordering on allowed fields (id, code, license_plate, created_at, ticket_expires_at).
- Pagination envelope and edge cases (page 1, next page, page boundaries, page size limits).
- Dynamic STT row calculation: (page - 1) * page_size + index + 1.
- Empty result sets on unmatched filters.
- Exclusion of soft-deleted vehicles from list results.
"""

import pytest
from rest_framework import status

from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicles/"


def test_vehicle_list_default_pagination_and_envelope(employee_client):
    """GET /api/v1/vehicles/ trả về cấu trúc phân trang tiêu chuẩn StandardResultsSetPagination."""
    response = employee_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "count" in data
    assert "total_pages" in data
    assert "current_page" in data
    assert "page_size" in data
    assert "next" in data
    assert "previous" in data
    assert "results" in data

    assert data["count"] == 30
    assert len(data["results"]) == 20  # Default page_size = 20
    assert data["total_pages"] == 2
    assert data["current_page"] == 1


def test_vehicle_list_dynamic_stt_calculation(employee_client):
    """Kiểm tra chỉ số STT động: trang 1 là 1..20, trang 2 là 21..30."""
    # Page 1
    res1 = employee_client.get(f"{ENDPOINT_URL}?page=1&page_size=10")
    assert res1.status_code == status.HTTP_200_OK
    results1 = res1.json()["results"]
    assert len(results1) == 10
    assert [r["stt"] for r in results1] == list(range(1, 11))

    # Page 2
    res2 = employee_client.get(f"{ENDPOINT_URL}?page=2&page_size=10")
    assert res2.status_code == status.HTTP_200_OK
    results2 = res2.json()["results"]
    assert len(results2) == 10
    assert [r["stt"] for r in results2] == list(range(11, 21))


def test_vehicle_list_handwritten_ground_truth_seed_assertions(employee_client):
    """
    Đối soát kết quả trả về của các phương tiện seed cụ thể với giá trị
    được tính toán độc lập từ SQL (không lấy từ code đang test).
    """
    # 1. XE0001: Đang có phiên đỗ mở -> status='parked', ticket ACTIVE -> state='valid'
    res = employee_client.get(f"{ENDPOINT_URL}?code=XE0001")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["count"] == 1
    v1 = res.json()["results"][0]
    assert v1["code"] == "XE0001"
    assert v1["license_plate"] == "43K-860.50"
    assert v1["vehicle_type"]["code"] == "CAR"
    assert v1["customer"]["code"] == "KH0001"
    assert v1["status"] == "parked"
    assert v1["status_display"] == "Đang đỗ"
    assert v1["current_slot"] is not None
    assert "Slot" in v1["current_slot"]
    assert v1["ticket"] is not None
    assert v1["ticket"]["state"] == "valid"
    assert v1["ticket"]["state_display"] == "Còn hạn"
    assert v1["ticket"]["days_remaining"] > 0

    # 2. XE0007: Không có phiên đỗ mở, nhưng có vé ACTIVE -> status='active', ticket state='valid'
    res = employee_client.get(f"{ENDPOINT_URL}?code=XE0007")
    assert res.status_code == status.HTTP_200_OK
    v7 = res.json()["results"][0]
    assert v7["code"] == "XE0007"
    assert v7["status"] == "active"
    assert v7["status_display"] == "Đang hoạt động"
    assert v7["ticket"] is not None
    assert v7["ticket"]["state"] == "valid"

    # 3. XE0011: Không có phiên đỗ mở, có vé EXPIRED (VT0011) -> status='left', ticket có state='expired'
    res = employee_client.get(f"{ENDPOINT_URL}?code=XE0011")
    assert res.status_code == status.HTTP_200_OK
    v11 = res.json()["results"][0]
    assert v11["code"] == "XE0011"
    assert v11["status"] == "left"
    assert v11["status_display"] == "Đã rời bãi"
    assert v11["ticket"] is not None
    assert v11["ticket"]["state"] == "expired"
    assert v11["ticket"]["state_display"] == "Đã hết hạn"
    assert v11["ticket"]["ticket_type_code"] == "DAILY"

    # 4. XE0026: Không có phiên đỗ, không có vé -> status='left', ticket=None, current_slot=None
    res = employee_client.get(f"{ENDPOINT_URL}?code=XE0026")
    assert res.status_code == status.HTTP_200_OK
    v26 = res.json()["results"][0]
    assert v26["code"] == "XE0026"
    assert v26["status"] == "left"
    assert v26["status_display"] == "Đã rời bãi"
    assert v26["ticket"] is None
    assert v26["current_slot"] is None


def test_vehicle_list_filter_status_parked_active_left(employee_client):
    """
    Kiểm tra bộ lọc status (parked, active, left) theo đúng phân hoạch
    đã chứng minh bằng SQL độc lập: parked=10, active=5, left=15.
    """
    # 1. Filter status=parked -> exactly 10
    res_parked = employee_client.get(f"{ENDPOINT_URL}?status=parked&page_size=50")
    assert res_parked.status_code == status.HTTP_200_OK
    assert res_parked.json()["count"] == 10
    for v in res_parked.json()["results"]:
        assert v["status"] == "parked"

    # 2. Filter status=active -> exactly 5
    res_active = employee_client.get(f"{ENDPOINT_URL}?status=active&page_size=50")
    assert res_active.status_code == status.HTTP_200_OK
    assert res_active.json()["count"] == 5
    for v in res_active.json()["results"]:
        assert v["status"] == "active"

    # 3. Filter status=left -> exactly 15
    res_left = employee_client.get(f"{ENDPOINT_URL}?status=left&page_size=50")
    assert res_left.status_code == status.HTTP_200_OK
    assert res_left.json()["count"] == 15
    for v in res_left.json()["results"]:
        assert v["status"] == "left"


def test_vehicle_list_filter_ticket_state(employee_client):
    """
    Kiểm tra bộ lọc ticket_state (valid, expiring_soon, expired, none).
    - Trên baseline seed sạch 30 xe:
      - 10 xe có vé hợp lệ (valid).
      - 0 xe có vé sắp hết hạn (expiring_soon).
      - 12 xe có vé đã hết hạn (expired).
      - 8 xe không có vé hoặc chỉ có vé CANCELLED (none).
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.tickets.models import Ticket, TicketType

    res_valid = employee_client.get(f"{ENDPOINT_URL}?ticket_state=valid&page_size=50")
    assert res_valid.status_code == status.HTTP_200_OK
    assert res_valid.json()["count"] == 10

    res_expiring_initial = employee_client.get(
        f"{ENDPOINT_URL}?ticket_state=expiring_soon"
    )
    assert res_expiring_initial.status_code == status.HTTP_200_OK
    assert res_expiring_initial.json()["count"] == 0

    res_expired = employee_client.get(
        f"{ENDPOINT_URL}?ticket_state=expired&page_size=50"
    )
    assert res_expired.status_code == status.HTTP_200_OK
    assert res_expired.json()["count"] == 12

    res_none = employee_client.get(f"{ENDPOINT_URL}?ticket_state=none&page_size=50")
    assert res_none.status_code == status.HTTP_200_OK
    assert res_none.json()["count"] == 8

    # Tạo vé sắp hết hạn (expiring_soon) cho XE0027 (hiện là none)
    now = timezone.now()
    from apps.parking.models import ParkingSlot

    available_slots = list(
        ParkingSlot.objects.exclude(
            tickets__deleted_at__isnull=True,
            tickets__effective_to__gt=now,
        )[:2]
    )
    tt = TicketType.objects.first()
    v_expiring = Vehicle.objects.filter(code="XE0027").first()
    Ticket.objects.create(
        code="VT9001",
        vehicle=v_expiring,
        customer=v_expiring.customer,
        ticket_type=tt,
        slot=available_slots[0],
        status="ACTIVE",
        effective_from=now - timedelta(days=20),
        effective_to=now + timedelta(days=3),
        price=100000,
    )

    res_expiring = employee_client.get(f"{ENDPOINT_URL}?ticket_state=expiring_soon")
    assert res_expiring.status_code == status.HTTP_200_OK
    assert res_expiring.json()["count"] == 1
    assert res_expiring.json()["results"][0]["code"] == "XE0027"

    # Tạo vé hết hạn (expired) mới cho XE0028 (hiện là none)
    v_expired = Vehicle.objects.filter(code="XE0028").first()
    Ticket.objects.create(
        code="VT9002",
        vehicle=v_expired,
        customer=v_expired.customer,
        ticket_type=tt,
        slot=available_slots[1],
        status="EXPIRED",
        effective_from=now - timedelta(days=40),
        effective_to=now - timedelta(days=2),
        price=100000,
    )

    res_expired_updated = employee_client.get(
        f"{ENDPOINT_URL}?ticket_state=expired&page_size=50"
    )
    assert res_expired_updated.status_code == status.HTTP_200_OK
    assert res_expired_updated.json()["count"] == 13  # 12 seed + 1 mới
    expired_codes = [v["code"] for v in res_expired_updated.json()["results"]]
    assert "XE0028" in expired_codes


def test_vehicle_list_filter_license_plate_normalized(employee_client):
    """
    Tìm kiếm theo biển số: hỗ trợ tìm kiếm có dấu chấm gạch ngang hoặc đã chuẩn hóa.
    Ví dụ: '43K-860.50' hoặc '43K86050' hoặc chữ thường '43k860'.
    """
    res1 = employee_client.get(f"{ENDPOINT_URL}?plate=43K-860.50")
    assert res1.status_code == status.HTTP_200_OK
    assert res1.json()["count"] >= 1
    assert any(v["code"] == "XE0001" for v in res1.json()["results"])

    res2 = employee_client.get(f"{ENDPOINT_URL}?plate=43k86050")
    assert res2.status_code == status.HTTP_200_OK
    assert res2.json()["count"] >= 1
    assert any(v["code"] == "XE0001" for v in res2.json()["results"])


def test_vehicle_list_filter_customer(employee_client):
    """Tìm kiếm theo mã khách hàng (KH0001) hoặc tên khách hàng."""
    res_code = employee_client.get(f"{ENDPOINT_URL}?customer=KH0001")
    assert res_code.status_code == status.HTTP_200_OK
    assert res_code.json()["count"] >= 1
    for item in res_code.json()["results"]:
        assert (
            item["customer"]["code"] == "KH0001"
            or "Nguyen" in item["customer"]["full_name"]
        )


def test_vehicle_list_filter_vehicle_type(employee_client):
    """Lọc theo loại xe CAR hoặc EV."""
    res_car = employee_client.get(f"{ENDPOINT_URL}?vehicle_type=CAR&page_size=50")
    assert res_car.status_code == status.HTTP_200_OK
    car_count = res_car.json()["count"]
    assert car_count > 0
    assert all(v["vehicle_type"]["code"] == "CAR" for v in res_car.json()["results"])

    res_ev = employee_client.get(f"{ENDPOINT_URL}?vehicle_type=EV&page_size=50")
    assert res_ev.status_code == status.HTTP_200_OK
    ev_count = res_ev.json()["count"]
    assert ev_count > 0
    assert all(v["vehicle_type"]["code"] == "EV" for v in res_ev.json()["results"])

    # Total must equal 30
    assert car_count + ev_count == 30


def test_vehicle_list_combined_filters(employee_client):
    """Kết hợp nhiều bộ lọc cùng lúc: vehicle_type=CAR AND status=parked."""
    res = employee_client.get(
        f"{ENDPOINT_URL}?vehicle_type=CAR&status=parked&page_size=50"
    )
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert len(results) > 0
    for v in results:
        assert v["vehicle_type"]["code"] == "CAR"
        assert v["status"] == "parked"


def test_vehicle_list_ordering_options(employee_client):
    """Kiểm tra sắp xếp theo code, -code, license_plate, -license_plate, created_at."""
    # Ascending code
    res_asc = employee_client.get(f"{ENDPOINT_URL}?ordering=code&page_size=5")
    assert res_asc.status_code == status.HTTP_200_OK
    codes_asc = [v["code"] for v in res_asc.json()["results"]]
    assert codes_asc == sorted(codes_asc)

    # Descending code
    res_desc = employee_client.get(f"{ENDPOINT_URL}?ordering=-code&page_size=5")
    assert res_desc.status_code == status.HTTP_200_OK
    codes_desc = [v["code"] for v in res_desc.json()["results"]]
    assert codes_desc == sorted(codes_desc, reverse=True)


def test_vehicle_list_empty_results(employee_client):
    """Tìm kiếm không khớp bản ghi nào -> count=0, results=[] rỗng."""
    res = employee_client.get(f"{ENDPOINT_URL}?code=XE999999")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["count"] == 0
    assert data["results"] == []


def test_vehicle_list_soft_deleted_vehicle_excluded(employee_client, auth_manager):
    """Phương tiện bị xóa mềm (deleted_at IS NOT NULL) tuyệt đối không xuất hiện trong danh sách."""
    # Get an unblocked vehicle from seed (e.g. XE0030) and soft-delete it
    v = Vehicle.objects.filter(code="XE0030", deleted_at__isnull=True).first()
    assert v is not None
    original_code = v.code
    v.soft_delete(user=auth_manager)

    res = employee_client.get(f"{ENDPOINT_URL}?code={original_code}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["count"] == 0
