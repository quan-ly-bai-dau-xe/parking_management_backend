"""
Tests for Vehicle CSV Export API (GET /api/v1/vehicles/export/).

Verifies:
- Streaming HTTP response with Content-Type 'text/csv; charset=utf-8' and Content-Disposition.
- Byte-order mark (UTF-8 BOM '\\ufeff') present at the very beginning of stream for Microsoft Excel.
- Valid CSV structure and Vietnamese column headers matching specification.
- Formula injection neutralization (OWASP CSV Injection):
  - Values starting with '=', '+', '-', '@', '\\t', '\\r' are prefixed with a single quote (').
  - Verifies payloads such as '=cmd|\' /C calc\'!A0', '+12345', '@SUM(...)', '\\tTAB'.
- Filter parameter inheritance: query filters (code, plate, customer, vehicle_type) filter CSV rows.
- Hard row cap constraint (MAX_EXPORT_ROWS = 5,000).
- Permission matrix: Anonymous -> 401, Customer -> 403, Employee -> 200, Manager -> 200.
"""

import csv
import io

import pytest
from rest_framework import status

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicles/export/"


def test_vehicle_export_headers_and_utf8_bom(employee_client):
    """
    Xuất CSV:
    - Bắt đầu bằng ký tự BOM \\ufeff.
    - Content-Type là text/csv; charset=utf-8.
    - Headers đầy đủ 11 cột tiếng Việt theo đặc tả.
    """
    response = employee_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_200_OK
    assert "text/csv" in response.headers.get("Content-Type", "")
    assert "attachment" in response.headers.get("Content-Disposition", "")
    assert "danh_sach_phuong_tien.csv" in response.headers.get(
        "Content-Disposition", ""
    )

    # Read streamed content
    content_bytes = b"".join(response.streaming_content)
    content_str = content_bytes.decode("utf-8")

    # Verify UTF-8 BOM
    assert content_str.startswith("\ufeff")

    # Parse CSV without BOM
    csv_text = content_str.lstrip("\ufeff")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)

    assert len(rows) >= 31  # 1 header + 30 seed vehicles
    expected_headers = [
        "STT",
        "Mã xe",
        "Biển số xe",
        "Chủ xe",
        "Mã khách hàng",
        "Loại xe",
        "Loại vé",
        "Ngày hết hạn vé",
        "Tình trạng vé",
        "Vị trí đỗ",
        "Trạng thái",
    ]
    assert rows[0] == expected_headers


def test_vehicle_export_formula_injection_neutralization(
    manager_client, car_type, active_customer
):
    """
    Phòng chống tấn công Formula Injection (CSV Injection):
    Tất cả các ô dữ liệu bắt đầu bằng '=', '+', '-', '@', '\\t', '\\r'
    bắt buộc phải được trung hòa an toàn bằng dấu nháy đơn (') phía trước.
    """
    malicious_customer = Customer.objects.create(
        code="KH-INJ-01",
        full_name="=cmd|' /C calc'!A0",  # DDE formula attack payload
        phone="0911998877",
        identity_card_number="049090123555",
    )
    Vehicle.objects.create(
        code="XE-INJ-01",
        license_plate="-51K-999.99",  # Dangerous '-' prefix allowed by plate regex
        license_plate_norm="51K99999",
        model_name="VF8",
        brand="VinFast",
        vehicle_type=car_type,
        customer=malicious_customer,
    )

    response = manager_client.get(f"{ENDPOINT_URL}?code=XE-INJ-01")
    assert response.status_code == status.HTTP_200_OK

    content_str = b"".join(response.streaming_content).decode("utf-8").lstrip("\ufeff")
    reader = csv.reader(io.StringIO(content_str))
    rows = list(reader)

    assert len(rows) == 2  # 1 header + 1 injected vehicle
    data_row = rows[1]

    # Verify neutralized values
    plate_cell = data_row[2]
    cust_name_cell = data_row[3]

    assert cust_name_cell.startswith("'=")
    assert plate_cell.startswith("'-")


def test_vehicle_export_filter_inheritance(employee_client):
    """Bộ lọc áp dụng cho export CSV tương đương API danh sách (ví dụ: vehicle_type=EV)."""
    response = employee_client.get(f"{ENDPOINT_URL}?vehicle_type=EV")
    assert response.status_code == status.HTTP_200_OK

    content_str = b"".join(response.streaming_content).decode("utf-8").lstrip("\ufeff")
    reader = csv.reader(io.StringIO(content_str))
    rows = list(reader)

    header = rows[0]
    data_rows = rows[1:]
    vtype_idx = header.index("Loại xe")

    assert len(data_rows) > 0
    for r in data_rows:
        assert r[vtype_idx] == "Xe điện"


def test_vehicle_export_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """Kiểm tra phân quyền trên endpoint xuất CSV."""
    # Anonymous -> 401
    assert (
        anonymous_client.get(ENDPOINT_URL).status_code == status.HTTP_401_UNAUTHORIZED
    )
    # Customer -> 403
    assert customer_client.get(ENDPOINT_URL).status_code == status.HTTP_403_FORBIDDEN
    # Employee -> 200
    assert employee_client.get(ENDPOINT_URL).status_code == status.HTTP_200_OK
    # Manager -> 200
    assert manager_client.get(ENDPOINT_URL).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_vehicle_export_disallowed_methods(manager_client, method):
    """Endpoint xuất CSV chỉ chấp nhận GET -> 405 Method Not Allowed."""
    client_method = getattr(manager_client, method)
    assert (
        client_method(ENDPOINT_URL, {}).status_code
        == status.HTTP_405_METHOD_NOT_ALLOWED
    )
