"""
Comprehensive integration and unit tests for Vehicle Search API (Task 9).
Endpoint: GET /api/v1/parking/vehicle-search/

Covers all 10 test categories:
1. Permission Matrix: Anonymous (401), Customer (403), Employee (200), Manager (200).
2. Input Validation: Missing params, string length < 2, whitespace trimming.
3. Unified Query `q`: Matches full_name, phone, +84 phone, license_plate, license_plate_norm.
4. Explicit Parameters: customer_name, phone, license_plate, AND conjunctions.
5. Special Wildcards Escape: %, _, \\ safely escaped without SQL errors.
6. Soft Delete & Anonymization: Excludes soft-deleted vehicles/customers, masks PII.
7. `currently_parked` Flag & Parking Position: Verified against open sessions and active tickets.
8. Deterministic Ordering: Exact normalized plate match prioritized first.
9. Pagination & Empty State: Page size capping (max 50), MSG-4.5.1-M01 on empty results.
10. Zero N+1 Queries: Batch hydration within max query budget (<= 6 queries).
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_search@parking.local",
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
        email="mgr_search@parking.local",
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
        email="cust_search@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


# ---------------------------------------------------------------------------
# 1. Permission Matrix
# ---------------------------------------------------------------------------


def test_permission_anonymous_rejected():
    """Chưa đăng nhập -> 401 Unauthorized (MSG-4.1-M02)."""
    client = APIClient()
    response = client.get("/api/v1/parking/vehicle-search/?q=Toyota")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_permission_customer_forbidden(auth_customer):
    """Vai trò CUSTOMER bị từ chối truy cập -> 403 Forbidden (MSG-4.2-M01)."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get("/api/v1/parking/vehicle-search/?q=Toyota")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_permission_employee_allowed(auth_employee):
    """Vai trò EMPLOYEE được phép truy cập -> 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=Toyota")
    assert response.status_code == status.HTTP_200_OK


def test_permission_manager_allowed(auth_manager):
    """Vai trò MANAGER được phép truy cập -> 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    response = client.get("/api/v1/parking/vehicle-search/?q=Toyota")
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# 2. Input Validation
# ---------------------------------------------------------------------------


def test_validation_missing_all_params(auth_employee):
    """Không truyền bất kỳ tham số tìm kiếm nào -> 400 Bad Request (PROP-GEN-P01)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert "non_field_errors" in response.data["details"]


@pytest.mark.parametrize(
    "query_param",
    [
        "?q=a",
        "?customer_name=b",
        "?phone=1",
        "?license_plate=5",
    ],
)
def test_validation_short_parameter(auth_employee, query_param):
    """Tham số có độ dài < 2 ký tự sau khi trim -> 400 Bad Request (PROP-GEN-P01)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(f"/api/v1/parking/vehicle-search/{query_param}")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"


def test_validation_whitespace_only(auth_employee):
    """Tham số chỉ chứa khoảng trắng -> 400 Bad Request (PROP-GEN-P01)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=     ")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"


def test_validation_valid_after_trim(auth_employee):
    """Tham số có 2 ký tự hợp lệ kèm khoảng trắng ở 2 đầu -> 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=   43   ")
    assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# 3. Unified Search `q`
# ---------------------------------------------------------------------------


def test_search_q_matches_customer_name(auth_employee):
    """Tìm kiếm q theo họ tên khách hàng (từ seed: Trịnh Xuân Trường)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=Xuân Trường")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    names = [r["customer"]["full_name"] for r in response.data["results"]]
    assert any("Xuân Trường" in n for n in names)


def test_search_q_matches_phone_exact(auth_employee):
    """Tìm kiếm q theo số điện thoại chuẩn (từ seed: 0868851325)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=0868851325")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    phones = [r["customer"]["phone"] for r in response.data["results"]]
    assert "0868851325" in phones


def test_search_q_matches_phone_international_prefix(auth_employee):
    """Tìm kiếm q theo số điện thoại có tiền tố +84 -> chuẩn hóa về 0."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=+84 868 851 325")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    phones = [r["customer"]["phone"] for r in response.data["results"]]
    assert "0868851325" in phones


def test_search_q_matches_raw_license_plate(auth_employee):
    """Tìm kiếm q theo biển số xe gốc (từ seed: 43K-860.50)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=43K-860.50")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    plates = [r["vehicle"]["license_plate"] for r in response.data["results"]]
    assert "43K-860.50" in plates


def test_search_q_matches_normalized_license_plate(auth_employee):
    """Tìm kiếm q theo biển số xe viết liền không dấu phân cách (43k86050)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=43k86050")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    norm_plates = [r["vehicle"]["license_plate_norm"] for r in response.data["results"]]
    assert "43K86050" in norm_plates


# ---------------------------------------------------------------------------
# 4. Explicit Parameters (customer_name, phone, license_plate)
# ---------------------------------------------------------------------------


def test_search_explicit_customer_name(auth_employee):
    """Lọc tường minh customer_name."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?customer_name=Trường")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    for item in response.data["results"]:
        assert "Trường" in item["customer"]["full_name"]


def test_search_explicit_phone(auth_employee):
    """Lọc tường minh phone."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?phone=0868851325")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    for item in response.data["results"]:
        assert item["customer"]["phone"] == "0868851325"


def test_search_explicit_license_plate(auth_employee):
    """Lọc tường minh license_plate."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?license_plate=43K-860.50")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    for item in response.data["results"]:
        assert item["vehicle"]["license_plate_norm"] == "43K86050"


def test_search_explicit_combined_and_matching(auth_employee):
    """Kết hợp tường minh AND: customer_name VÀ phone cùng khớp một khách hàng."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        "/api/v1/parking/vehicle-search/?customer_name=Trường&phone=0868851325"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1


def test_search_explicit_combined_and_mismatch(auth_employee):
    """Kết hợp tường minh AND: customer_name và license_plate không cùng chủ sở hữu -> rỗng."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    # Tìm tên Trường nhưng gán biển số không tồn tại
    response = client.get(
        "/api/v1/parking/vehicle-search/?customer_name=Trường&license_plate=99Z-999.99"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response.data["results"] == []
    assert response.data["message"] == "Không tìm thấy dữ liệu trùng khớp"


# ---------------------------------------------------------------------------
# 5. Wildcard LIKE Escape
# ---------------------------------------------------------------------------


def test_search_escape_wildcards(auth_employee):
    """Ký tự đặc biệt LIKE (%, _, \\) không gây lỗi cú pháp SQL."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    wildcards = ["43K%", "43K_860", "test\\plate", "%", "_"]
    for w in wildcards:
        if len(w) < 2:
            continue
        response = client.get(f"/api/v1/parking/vehicle-search/?q={w}")
        assert response.status_code == status.HTTP_200_OK
        assert "results" in response.data


# ---------------------------------------------------------------------------
# 6. Soft Delete & Anonymization
# ---------------------------------------------------------------------------


def test_search_soft_deleted_vehicle_excluded(auth_employee):
    """Phương tiện bị xóa mềm (deleted_at IS NOT NULL) không bao giờ xuất hiện."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-M3-01",
        full_name="Lê Minh Soft",
        phone="0911000111",
        identity_card_number="049090123991",
    )
    v = Vehicle.objects.create(
        code="XE-M3-01",
        license_plate="51A-000.11",
        license_plate_norm="51A00011",
        model_name="Corolla",
        vehicle_type=vtype,
        customer=cust,
        deleted_at=timezone.now(),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-search/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response.data["results"] == []


def test_search_soft_deleted_customer_excluded(auth_employee):
    """Khách hàng bị xóa mềm -> tất cả xe của khách hàng này không xuất hiện."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-M3-02",
        full_name="Phạm Văn Ẩn",
        phone="0922000222",
        identity_card_number="049090123992",
        deleted_at=timezone.now(),
    )
    v = Vehicle.objects.create(
        code="XE-M3-02",
        license_plate="51B-000.22",
        license_plate_norm="51B00022",
        model_name="Camry",
        vehicle_type=vtype,
        customer=cust,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-search/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0


def test_search_anonymized_customer(auth_employee):
    """Khách hàng có is_anonymized=True -> che giấu PII (họ tên và số điện thoại)."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-M3-03",
        full_name="Hoàng Thị Bí Mật",
        phone="0933000333",
        identity_card_number="049090123993",
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )
    v = Vehicle.objects.create(
        code="XE-M3-03",
        license_plate="51C-000.33",
        license_plate_norm="51C00033",
        model_name="Yaris",
        vehicle_type=vtype,
        customer=cust,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-search/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 1
    cust_data = response.data["results"][0]["customer"]
    assert cust_data["is_anonymized"] is True
    assert cust_data["full_name"] == "Khách hàng ẩn danh"
    assert cust_data["phone"] is None


# ---------------------------------------------------------------------------
# 7. currently_parked Flag & Parking Position
# ---------------------------------------------------------------------------


def test_search_currently_parked_and_position(auth_employee):
    """
    Kiểm tra cờ currently_parked và vị trí đỗ:
    - Xe XE0001 (43K-860.50): đang có phiên đỗ mở tại vị trí A-01 -> currently_parked = True.
    - Xe XE0011 (92V-929.32): không có phiên đỗ mở -> currently_parked = False.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?license_plate=43K-860.50")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    item = response.data["results"][0]
    assert item["currently_parked"] is True
    assert item["open_session"] is not None
    assert item["parking_position"] is not None
    assert "Zone" in item["parking_position"]["display_text"]

    # Tra cứu xe XE0011 không có phiên đỗ
    response_out = client.get(
        "/api/v1/parking/vehicle-search/?license_plate=92V-929.32"
    )
    assert response_out.status_code == status.HTTP_200_OK
    assert response_out.data["count"] >= 1
    item_out = response_out.data["results"][0]
    assert item_out["currently_parked"] is False
    assert item_out["open_session"] is None


# ---------------------------------------------------------------------------
# 8. Deterministic Ordering (Exact Match Priority)
# ---------------------------------------------------------------------------


def test_search_deterministic_sorting_exact_match(auth_employee):
    """
    Sắp xếp xác định: Xe có biển số chuẩn hóa khớp chính xác với từ khóa
    phải đứng ở vị trí đầu tiên (index 0), sau đó sắp xếp theo license_plate.
    """
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-M3-SORT",
        full_name="Nguyễn Sắp Xếp",
        phone="0944000444",
        identity_card_number="049090123994",
    )
    # Tạo 2 xe có tiền tố giống nhau:
    # Xe 1: 51K-999.00 (norm: 51K99900)
    # Xe 2: 51K-999.001 (norm: 51K999001)
    Vehicle.objects.create(
        code="XE-SORT-02",
        license_plate="51K-999.001",
        license_plate_norm="51K999001",
        model_name="Vios",
        vehicle_type=vtype,
        customer=cust,
    )
    Vehicle.objects.create(
        code="XE-SORT-01",
        license_plate="51K-999.00",
        license_plate_norm="51K99900",
        model_name="Altis",
        vehicle_type=vtype,
        customer=cust,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    # Tìm kiếm chính xác 51K99900
    response = client.get("/api/v1/parking/vehicle-search/?q=51K99900")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 2
    results = response.data["results"]
    assert results[0]["vehicle"]["license_plate_norm"] == "51K99900"


# ---------------------------------------------------------------------------
# 9. Pagination & Empty Results
# ---------------------------------------------------------------------------


def test_search_pagination_default_and_custom(auth_employee):
    """Kiểm tra phân trang: mặc định page_size=20, tùy chỉnh page_size."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response_default = client.get("/api/v1/parking/vehicle-search/?q=Toyota")
    assert response_default.status_code == status.HTTP_200_OK
    assert response_default.data["page_size"] == 20

    response_custom = client.get("/api/v1/parking/vehicle-search/?q=Toyota&page_size=5")
    assert response_custom.status_code == status.HTTP_200_OK
    assert response_custom.data["page_size"] == 5
    assert len(response_custom.data["results"]) <= 5


def test_search_pagination_capped_at_max(auth_employee):
    """Kích thước trang được giới hạn ở max_page_size = 50 khi client yêu cầu 100."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=Toyota&page_size=100")
    # DRF serializer validation ném 400 nếu page_size > 50 theo quy tắc max_value=50
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_search_empty_results_returns_200_with_message(auth_employee):
    """Khi không tìm thấy dữ liệu -> HTTP 200 kèm results=[] và MSG-4.5.1-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=Không tồn tại xe này")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response.data["total_pages"] == 0
    assert response.data["results"] == []
    assert response.data["message"] == "Không tìm thấy dữ liệu trùng khớp"


# ---------------------------------------------------------------------------
# 10. Zero N+1 Queries (Batch Hydration)
# ---------------------------------------------------------------------------


def test_search_zero_n_plus_one_queries(auth_employee, django_assert_max_num_queries):
    """
    Kiểm tra Zero N+1 Queries:
    Toàn bộ truy vấn phân trang + batch hydration phải hoàn thành trong <= 6 queries.
    (1 auth user, 1 count, 1 select vehicles, 1 open sessions, 1 active tickets, 1 blacklist).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    with django_assert_max_num_queries(6):
        response = client.get("/api/v1/parking/vehicle-search/?q=Toyota&page_size=20")
        assert response.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# 11. Edge Cases & Helper Utilities
# ---------------------------------------------------------------------------


def test_search_helper_utilities():
    """Kiểm tra các hàm tiện ích escape_like và normalize_phone_query."""
    from apps.parking.selectors.search import (
        escape_like,
        hydrate_vehicle_search_results,
        normalize_phone_query,
    )

    assert escape_like("") == ""
    assert normalize_phone_query("") == ""
    assert normalize_phone_query("84912345678") == "0912345678"
    assert hydrate_vehicle_search_results([]) == []


def test_search_view_unpaginated_fallback(auth_employee, monkeypatch):
    """Kiểm tra fallback khi paginator.paginate_queryset trả về None (có dữ liệu)."""
    from apps.parking.views.search import VehicleSearchPagination

    monkeypatch.setattr(
        VehicleSearchPagination, "paginate_queryset", lambda self, qs, req, view: None
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-search/?q=43K")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    assert response.data["total_pages"] == 1


def test_search_view_unpaginated_fallback_empty(auth_employee, monkeypatch):
    """Kiểm tra fallback khi paginator.paginate_queryset trả về None (rỗng dữ liệu)."""
    from apps.parking.views.search import VehicleSearchPagination

    monkeypatch.setattr(
        VehicleSearchPagination, "paginate_queryset", lambda self, qs, req, view: None
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        "/api/v1/parking/vehicle-search/?q=Không tồn tại xe này bao giờ"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] == 0
    assert response.data["total_pages"] == 0
    assert response.data["message"] == "Không tìm thấy dữ liệu trùng khớp"


def test_hydrate_vehicle_without_customer_in_memory():
    """Kiểm tra hydrate kết quả khi đối tượng vehicle không có customer liên kết."""
    from apps.parking.selectors.search import hydrate_vehicle_search_results

    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None
    v._state.fields_cache.pop("customer", None)
    v.customer_id = 99999999
    res = hydrate_vehicle_search_results([v])
    assert len(res) == 1
    assert res[0]["customer"]["id"] == 0
    assert res[0]["customer"]["full_name"] == ""
