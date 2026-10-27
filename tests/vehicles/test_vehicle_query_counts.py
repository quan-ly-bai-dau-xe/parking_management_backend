"""
Query Count & Zero N+1 Performance Regression Tests.

Enforces upper-bound database query count limits per round specification:
- List API (GET /api/v1/vehicles/): <= 3 queries (asserted zero N+1, measured exactly 2).
- Detail API (GET /api/v1/vehicles/{id}/): <= 5 queries (asserted zero N+1, measured exactly 4).
- Summary API (GET /api/v1/vehicles/summary/): <= 2 queries (asserted zero N+1, measured exactly 1).
- Export API (GET /api/v1/vehicles/export/): <= 2 queries (asserted zero N+1, measured exactly 1).

Also verifies strict O(1) query scaling:
- Query count for 5 rows vs 20 rows in the list API must be strictly identical.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status

from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


def test_vehicle_list_query_count_upper_bound_and_no_n_plus_one(employee_client):
    """
    GET /api/v1/vehicles/ phải thực thi <= 3 câu truy vấn (1 COUNT + 1 SELECT data).
    Khi tăng page_size từ 5 lên 20, số lượng câu truy vấn không đổi (Zero N+1 guarantee).
    """
    # 1. Đo lường page_size = 5
    with CaptureQueriesContext(connection) as ctx_5:
        res_5 = employee_client.get("/api/v1/vehicles/?page=1&page_size=5")
    assert res_5.status_code == status.HTTP_200_OK
    queries_5 = len(ctx_5.captured_queries)
    assert queries_5 <= 3, f"List API query count ({queries_5}) exceeded upper bound 3"
    assert queries_5 == 2

    # 2. Đo lường page_size = 20
    with CaptureQueriesContext(connection) as ctx_20:
        res_20 = employee_client.get("/api/v1/vehicles/?page=1&page_size=20")
    assert res_20.status_code == status.HTTP_200_OK
    queries_20 = len(ctx_20.captured_queries)
    assert queries_20 <= 3, (
        f"List API query count ({queries_20}) exceeded upper bound 3"
    )
    assert queries_20 == 2

    # 3. Khẳng định số truy vấn hoàn toàn không phụ thuộc vào số lượng hàng trả về (O(1))
    assert queries_5 == queries_20, (
        f"N+1 regression detected: {queries_5} queries for 5 rows vs {queries_20} queries for 20 rows"
    )


def test_vehicle_detail_query_count_upper_bound(employee_client):
    """
    GET /api/v1/vehicles/{id}/ phải thực thi <= 5 câu truy vấn
    (1 xe + quan hệ, 1 đếm xe chủ sở hữu, 1 phiên đỗ mở, 1 vé mới nhất).
    """
    v1 = Vehicle.objects.get(code="XE0001")
    with CaptureQueriesContext(connection) as ctx:
        res = employee_client.get(f"/api/v1/vehicles/{v1.id}/")
    assert res.status_code == status.HTTP_200_OK
    query_count = len(ctx.captured_queries)
    assert query_count <= 5, (
        f"Detail API query count ({query_count}) exceeded upper bound 5"
    )
    assert query_count == 4


def test_vehicle_summary_query_count_upper_bound(employee_client):
    """GET /api/v1/vehicles/summary/ phải thực thi <= 2 câu truy vấn (chính xác 1 aggregate)."""
    with CaptureQueriesContext(connection) as ctx:
        res = employee_client.get("/api/v1/vehicles/summary/")
    assert res.status_code == status.HTTP_200_OK
    query_count = len(ctx.captured_queries)
    assert query_count <= 2, (
        f"Summary API query count ({query_count}) exceeded upper bound 2"
    )
    assert query_count == 1


def test_vehicle_export_query_count_upper_bound(employee_client):
    """
    GET /api/v1/vehicles/export/ phải thực thi <= 2 câu truy vấn
    (chính xác 1 query stream toàn bộ dữ liệu kèm quan hệ).
    """
    with CaptureQueriesContext(connection) as ctx:
        res = employee_client.get("/api/v1/vehicles/export/")
        assert res.status_code == status.HTTP_200_OK
        # Consume full streaming response to trigger all generator queries
        _ = b"".join(res.streaming_content)
    query_count = len(ctx.captured_queries)
    assert query_count <= 2, (
        f"Export API query count ({query_count}) exceeded upper bound 2"
    )
    assert query_count == 1
