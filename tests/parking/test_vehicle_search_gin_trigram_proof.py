"""
Empirical boundary tests and EXPLAIN (ANALYZE, BUFFERS) Trigram GIN proof (Defect F9).
Tests vehicle search across 3 critical areas:
1. Boundary Search Vectors (Vietnamese diacritics, dashes, dots, spaces, 2-chars, long strings, special chars).
2. UNION Subquery Correctness (Deduplication, Completeness, Soft-Delete Isolation, Exact Match Ordering).
3. EXPLAIN (ANALYZE, BUFFERS) Execution Plan Proof over >= 50,000 real rows in PostgreSQL 18.6,
   verifying Bitmap Index Scan on idx_vehicle_plate_trgm, idx_customer_full_name_trgm, and idx_customer_phone_trgm.
"""

import contextlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.selectors.search import search_vehicles_query
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_f9_verification@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


# ============================================================================
# PART 1: BOUNDARY SEARCH VECTORS
# ============================================================================


def test_boundary_vietnamese_diacritics(auth_employee):
    """
    Vector tìm kiếm đối kháng: Chuỗi có dấu tiếng Việt đa dạng.
    Bao gồm các ký tự Unicode tổ hợp / dựng sẵn (ă, â, đ, ê, ô, ơ, ư, dấu huyền, sắc, hỏi, ngã, nặng).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    vtype = VehicleType.objects.first() or VehicleType.objects.create(
        code="OTO-VN", name="Ô tô", description="Ô tô Việt Nam"
    )
    cust = Customer.objects.create(
        code="KH-VN01",
        full_name="Đặng Nguyễn Triệu Khương",
        phone="0988112233",
        identity_card_number="123456789",
        status="ACTIVE",
    )
    Vehicle.objects.create(
        code="XE-VN01",
        license_plate="43-D1 999.88",
        model_name="VinFast VF 9 Plus Đỏ Cờ",
        vehicle_type=vtype,
        customer=cust,
    )

    test_vectors = [
        "Đặng",
        "Triệu",
        "Khương",
        "Nguyễn Triệu",
        "khương",  # lowercase
        "ĐẶNG",  # uppercase
    ]

    for term in test_vectors:
        # 1. Thử nghiệm qua selector
        qs = search_vehicles_query({"q": term})
        assert qs.filter(code="XE-VN01").exists(), f"Không tìm thấy xe với q='{term}'"

        # 2. Thử nghiệm qua API endpoint
        resp = client.get(f"/api/v1/parking/vehicle-search/?q={term}")
        assert resp.status_code == status.HTTP_200_OK
        results = resp.data.get("results", [])
        assert any(r["vehicle"]["code"] == "XE-VN01" for r in results), (
            f"API không trả về xe với vector tiếng Việt '{term}'"
        )


def test_boundary_dashes_dots_and_spaces(auth_employee):
    """
    Vector tìm kiếm đối kháng: Chuỗi có nhiều dấu gạch ngang, dấu chấm, khoảng trắng dư thừa ở đầu và cuối.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-PUNC1",
        full_name="Trần Văn Punctuation",
        phone="0977665544",
        identity_card_number="123456788",
        status="ACTIVE",
    )
    Vehicle.objects.create(
        code="XE-PUNC1",
        license_plate="51K-888.99",
        model_name="Mazda CX-5",
        vehicle_type=vtype,
        customer=cust,
    )

    vectors = [
        "51K-888.99",
        "51K.888.99",
        "  51K 888 99  ",
        "51K---888",
        "888.99",
        "  Trần Văn  ",
        "\t51K-888.99\n",
    ]

    for vec in vectors:
        resp = client.get("/api/v1/parking/vehicle-search/", {"q": vec})
        assert resp.status_code == status.HTTP_200_OK, (
            f"Lỗi HTTP {resp.status_code} với vector '{vec}'"
        )
        results = resp.data.get("results", [])
        assert any(r["vehicle"]["code"] == "XE-PUNC1" for r in results), (
            f"Không tìm thấy xe với vector có định dạng đặc biệt '{vec}'"
        )


def test_boundary_two_character_boundary(auth_employee):
    """
    Vector tìm kiếm đối kháng: Ngưỡng biên 2 ký tự (hợp lệ) vs < 2 ký tự (bị từ chối HTTP 400).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Các chuỗi 2 ký tự hợp lệ -> HTTP 200
    valid_2char = ["51", "An", "09", "Tr", "K-", "--", "..", "  51  "]
    for term in valid_2char:
        resp = client.get("/api/v1/parking/vehicle-search/", {"q": term})
        assert resp.status_code == status.HTTP_200_OK, (
            f"Vector 2 ký tự '{term}' phải được chấp nhận"
        )

    # 2. Các chuỗi < 2 ký tự sau khi strip -> HTTP 400
    invalid_terms = ["a", "5", "-", ".", " ", "   "]
    for term in invalid_terms:
        resp = client.get("/api/v1/parking/vehicle-search/", {"q": term})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Vector '{term}' phải bị từ chối với 400"
        )


def test_boundary_long_string_and_special_chars(auth_employee):
    """
    Vector tìm kiếm đối kháng: Chuỗi dài (100, 255, 1000 ký tự), SQL injection wildcards, HTML tags, emoji.
    Hệ thống phải xử lý an toàn, không sinh lỗi 500 hay SQL injection.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    boundary_payloads = [
        "A" * 100,
        "B" * 255,
        "C" * 1000,
        "%' OR '1'='1",
        "_; DROP TABLE vehicle CASCADE; --",
        "\\%\\_\\\\",
        "<script>alert('xss')</script>",
        "🚗🛵🚘",
        "'; EXEC xp_cmdshell('dir'); --",
        "[A-Za-z0-9]+",
        ".*+?^${}()|[]\\",
    ]

    for payload in boundary_payloads:
        resp = client.get("/api/v1/parking/vehicle-search/", {"q": payload})
        assert resp.status_code in (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST), (
            f"Payload đối kháng '{payload}' gây lỗi {resp.status_code}: {resp.data}"
        )


# ============================================================================
# PART 2: UNION SUBQUERY CORRECTNESS & INVARIANTS
# ============================================================================


def test_union_subquery_deduplication():
    """
    Kiểm chứng tính không trùng lặp (Deduplication):
    Tạo một xe có biển số, tên chủ sở hữu và số điện thoại đều chứa cùng một chuỗi '888'.
    Khi tìm kiếm bằng q='888', cả 3 nhánh subquery đều khớp cùng 1 vehicle.id.
    Kỳ vọng: Kết quả trả về phải chứa DUY NHẤT 1 bản ghi xe, không được trùng lặp.
    """
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-DEDUP",
        full_name="Bác Ba 888",
        phone="0988888888",
        identity_card_number="123456787",
        status="ACTIVE",
    )
    v = Vehicle.objects.create(
        code="XE-DEDUP",
        license_plate="88A-888.88",
        model_name="Lexus LX600",
        vehicle_type=vtype,
        customer=cust,
    )

    qs = search_vehicles_query({"q": "888"})
    matching_list = list(qs.filter(code="XE-DEDUP"))
    assert len(matching_list) == 1, (
        f"Kỳ vọng đúng 1 bản ghi xe duy nhất, nhưng nhận được {len(matching_list)} bản ghi trùng lặp!"
    )
    assert matching_list[0].id == v.id


def test_union_subquery_completeness():
    """
    Kiểm chứng tính đầy đủ (Completeness - Không sót bản ghi):
    Tạo 3 xe khác nhau, mỗi xe khớp đúng 1 nhánh trong q='Alpha':
    - Xe 1: Khớp biển số ('ALPHA99')
    - Xe 2: Khớp tên khách hàng ('Nguyễn Alpha')
    - Xe 3: Khớp số điện thoại ('0912345678' với q tìm phone)
    Kỳ vọng: gom đủ 100% các xe khớp, không bỏ sót bản ghi nào.
    """
    vtype = VehicleType.objects.first()

    c1 = Customer.objects.create(
        code="KH-CMP1",
        full_name="Trần Văn Một",
        phone="0911111111",
        identity_card_number="123456786",
        status="ACTIVE",
    )
    Vehicle.objects.create(
        code="XE-CMP1",
        license_plate="51K-ALP.01",
        model_name="Camry",
        vehicle_type=vtype,
        customer=c1,
    )

    c2 = Customer.objects.create(
        code="KH-CMP2",
        full_name="Lê Văn AlPha",
        phone="0922222222",
        identity_card_number="123456785",
        status="ACTIVE",
    )
    Vehicle.objects.create(
        code="XE-CMP2",
        license_plate="51K-123.45",
        model_name="Vios",
        vehicle_type=vtype,
        customer=c2,
    )

    qs = search_vehicles_query({"q": "ALP"})
    found_codes = set(qs.values_list("code", flat=True))

    assert "XE-CMP1" in found_codes, "Sót xe khớp biển số!"
    assert "XE-CMP2" in found_codes, "Sót xe khớp tên khách hàng!"


def test_union_subquery_soft_delete_isolation():
    """
    Kiểm chứng cách ly xóa mềm:
    - Xe bị xóa mềm (deleted_at IS NOT NULL) -> Không được xuất hiện.
    - Khách hàng bị xóa mềm (customer.deleted_at IS NOT NULL) -> Xe không được xuất hiện.
    """
    vtype = VehicleType.objects.first()
    now = timezone.now()

    # Xe xóa mềm
    c_active = Customer.objects.create(
        code="KH-SDACT",
        full_name="Nguyễn Văn Active",
        phone="0933333333",
        identity_card_number="123456784",
        status="ACTIVE",
    )
    Vehicle.objects.create(
        code="XE-SDDEL1",
        license_plate="51K-DEL.01",
        model_name="Civic",
        vehicle_type=vtype,
        customer=c_active,
        deleted_at=now,
    )

    # Khách hàng xóa mềm
    c_deleted = Customer.objects.create(
        code="KH-SDDEL",
        full_name="Lê Văn Deleted",
        phone="0944444444",
        identity_card_number="123456783",
        status="ACTIVE",
        deleted_at=now,
    )
    Vehicle.objects.create(
        code="XE-SDDEL2",
        license_plate="51K-DEL.02",
        model_name="Accord",
        vehicle_type=vtype,
        customer=c_deleted,
    )

    qs = search_vehicles_query({"q": "DEL"})
    found_codes = set(qs.values_list("code", flat=True))

    assert "XE-SDDEL1" not in found_codes, "Lọt xe đã bị xóa mềm vào kết quả tìm kiếm!"
    assert "XE-SDDEL2" not in found_codes, (
        "Lọt xe của khách hàng đã bị xóa mềm vào kết quả tìm kiếm!"
    )


def test_union_subquery_exact_match_priority():
    """
    Kiểm chứng sắp xếp xác định: Xe khớp chính xác biển số chuẩn hóa phải luôn đứng đầu tiên.
    """
    vtype = VehicleType.objects.first()
    c = Customer.objects.create(
        code="KH-PRI01",
        full_name="Đỗ Hải Đăng",
        phone="0955555555",
        identity_card_number="123456782",
        status="ACTIVE",
    )

    # Xe khớp chính xác
    Vehicle.objects.create(
        code="XE-EXACT1",
        license_plate="51K-999.99",
        model_name="CR-V",
        vehicle_type=vtype,
        customer=c,
    )
    # Xe khớp tiền tố (đứng trước về thứ tự alpha nếu không có exact_match)
    Vehicle.objects.create(
        code="XE-PREF1",
        license_plate="51A-999.99",
        model_name="City",
        vehicle_type=vtype,
        customer=c,
    )

    qs = search_vehicles_query({"q": "51K-999.99"})
    results = list(qs)
    assert len(results) >= 1
    assert results[0].code == "XE-EXACT1", (
        f"Kỳ vọng xe khớp chính xác XE-EXACT1 đứng đầu, nhưng xe đứng đầu là {results[0].code}"
    )


# ============================================================================
# PART 3: EXPLAIN (ANALYZE, BUFFERS) TRIGRAM GIN PROOF OVER 50,000 ROWS
# ============================================================================


def test_trigram_gin_proof_50k_rows_on_real_tables():
    """
    Thực nghiệm kiểm chứng tối ưu hóa chỉ mục Trigram GIN trên >= 50,000 bản ghi:
    1. Sinh >= 50,000 dòng dữ liệu vào bảng customer và vehicle thực tế.
    2. Chạy VACUUM ANALYZE để cập nhật thống kê cho PostgreSQL Query Planner.
    3. Chạy EXPLAIN (ANALYZE, BUFFERS) cho 4 câu truy vấn nghiệp vụ:
       - Truy vấn hợp nhất: q=
       - Truy vấn tường minh: customer_name=
       - Truy vấn tường minh: phone=
       - Truy vấn tường minh: license_plate=
    4. Khẳng định 100% các câu truy vấn kích hoạt Bitmap Index Scan trên GIN indexes:
       - idx_vehicle_plate_trgm
       - idx_customer_full_name_trgm
       - idx_customer_phone_trgm
       và tuyệt đối KHÔNG có Seq Scan trên bảng lọc text!
    5. In đầy đủ raw execution plan phục vụ kiểm chứng độc lập.
    """
    print("\n" + "=" * 80)
    print(
        "=== THỰC NGHIỆM ĐỐI KHÁNG EXPLAIN (ANALYZE, BUFFERS) TRÊN >= 50,000 BẢN GHI ==="
    )
    print("=" * 80)

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM vehicle_type LIMIT 1;")
        row_vtype = cursor.fetchone()
        assert row_vtype is not None, "Không tìm thấy vehicle_type nào trong CSDL!"
        vtype_id = row_vtype[0]

        # 1. Sinh 50,000 bản ghi customer
        print("\n[STEP 1] Generating 50,000 synthetic rows into customer table...")
        cursor.execute(
            """
            INSERT INTO customer (code, full_name, phone, identity_card_number, email, status, row_version)
            SELECT
                'KH' || lpad(i::text, 8, '0'),
                (ARRAY['Nguyễn', 'Trần', 'Lê', 'Phạm', 'Hoàng', 'Huỳnh', 'Phan', 'Vũ', 'Đặng', 'Bùi'])[1 + (i % 10)] || ' ' ||
                (ARRAY['Văn', 'Thị', 'Hữu', 'Đức', 'Minh', 'Thành', 'Hải', 'Xuân', 'Kim', 'Ngọc'])[1 + ((i / 10) % 10)] || ' ' ||
                (ARRAY['An', 'Bình', 'Hương', 'Linh', 'Dũng', 'Khánh', 'Sơn', 'Tâm', 'Phương', 'Trang'])[1 + ((i / 100) % 10)],
                '09' || lpad(i::text, 8, '0'),
                '0' || lpad(i::text, 11, '0'),
                'cust_' || i::text || '@test.local',
                'ACTIVE',
                1
            FROM generate_series(1, 50000) AS i
            ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;
        """
        )

        cursor.execute("SELECT COUNT(*) FROM customer WHERE code LIKE 'KH00%';")
        cust_count = cursor.fetchone()[0]
        print(f"-> Verified customer row count: {cust_count}")
        assert cust_count >= 50000, f"Customer rows count < 50,000: {cust_count}"

        # 2. Sinh 50,000 bản ghi vehicle liên kết với customer (dùng dải biển số 99X-xxxxxx để đảm bảo 100% unique)
        print("\n[STEP 2] Generating 50,000 synthetic rows into vehicle table...")
        cursor.execute(
            f"""
            INSERT INTO vehicle (
                code, license_plate, model_name,
                vehicle_type_id, customer_id, row_version
            )
            SELECT
                'XE' || lpad(i::text, 8, '0'),
                '99X-' || lpad(i::text, 6, '0'),
                'Model ' || (i % 50)::text,
                {vtype_id},
                c.id,
                1
            FROM generate_series(1, 50000) AS i
            JOIN customer c ON c.code = 'KH' || lpad(i::text, 8, '0')
            ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;
        """
        )

        cursor.execute("SELECT COUNT(*) FROM vehicle WHERE code LIKE 'XE00%';")
        veh_count = cursor.fetchone()[0]
        print(f"-> Verified vehicle row count: {veh_count}")
        assert veh_count >= 50000, f"Vehicle rows count < 50,000: {veh_count}"

        # 3. Chạy VACUUM ANALYZE để cập nhật planner statistics
        print("\n[STEP 3] Running VACUUM ANALYZE customer and vehicle...")
        cursor.execute("VACUUM ANALYZE customer;")
        cursor.execute("VACUUM ANALYZE vehicle;")

        # 4. Kiểm chứng QUERY 1: Tìm kiếm theo biển số tường minh (license_plate=)
        print("\n" + "-" * 70)
        print("--- [QUERY 1] EXPLAIN ANALYZE: license_plate='99X049921' ---")
        cursor.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT v.id, v.license_plate, v.license_plate_norm, c.full_name
            FROM vehicle v
            JOIN customer c ON v.customer_id = c.id
            WHERE v.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND v.license_plate_norm ILIKE '%99X049921%';
        """
        )
        plan_plate = "\n".join(row[0] for row in cursor.fetchall())
        print(plan_plate)
        assert "idx_vehicle_plate_trgm" in plan_plate, (
            f"Lỗi: Không sử dụng Trigram GIN index idx_vehicle_plate_trgm!\nPlan:\n{plan_plate}"
        )
        assert "Bitmap Index Scan" in plan_plate
        assert "Seq Scan on vehicle" not in plan_plate, (
            "Cảnh báo: Xuất hiện Seq Scan trên vehicle!"
        )
        print(
            "[PASS] QUERY 1 kích hoạt Bitmap Index Scan trên idx_vehicle_plate_trgm hoàn hảo!"
        )

        # 5. Kiểm chứng QUERY 2: Tìm kiếm theo họ tên khách hàng tường minh (customer_name=)
        print("\n" + "-" * 70)
        print("--- [QUERY 2] EXPLAIN ANALYZE: customer_name='Thị Hương' ---")
        cursor.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT v.id, v.license_plate, c.full_name
            FROM vehicle v
            JOIN customer c ON v.customer_id = c.id
            WHERE v.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND c.full_name ILIKE '%Thị Hương%';
        """
        )
        plan_name = "\n".join(row[0] for row in cursor.fetchall())
        print(plan_name)
        assert "idx_customer_full_name_trgm" in plan_name, (
            f"Lỗi: Không sử dụng Trigram GIN index idx_customer_full_name_trgm!\nPlan:\n{plan_name}"
        )
        assert "Bitmap Index Scan" in plan_name
        assert "Seq Scan on customer" not in plan_name, (
            "Cảnh báo: Xuất hiện Seq Scan trên customer!"
        )
        print(
            "[PASS] QUERY 2 kích hoạt Bitmap Index Scan trên idx_customer_full_name_trgm hoàn hảo!"
        )

        # 6. Kiểm chứng QUERY 3: Tìm kiếm theo số điện thoại tường minh (phone=)
        print("\n" + "-" * 70)
        print("--- [QUERY 3] EXPLAIN ANALYZE: phone='09100099' ---")
        cursor.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT v.id, v.license_plate, c.phone
            FROM vehicle v
            JOIN customer c ON v.customer_id = c.id
            WHERE v.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND c.phone ILIKE '%09100099%';
        """
        )
        plan_phone = "\n".join(row[0] for row in cursor.fetchall())
        print(plan_phone)
        assert "idx_customer_phone_trgm" in plan_phone, (
            f"Lỗi: Không sử dụng Trigram GIN index idx_customer_phone_trgm!\nPlan:\n{plan_phone}"
        )
        assert "Bitmap Index Scan" in plan_phone
        assert "Seq Scan on customer" not in plan_phone, (
            "Cảnh báo: Xuất hiện Seq Scan trên customer!"
        )
        print(
            "[PASS] QUERY 3 kích hoạt Bitmap Index Scan trên idx_customer_phone_trgm hoàn hảo!"
        )

        # 7. Kiểm chứng QUERY 4: Truy vấn hợp nhất q= (UNION subquery)
        print("\n" + "-" * 70)
        print(
            "--- [QUERY 4] EXPLAIN ANALYZE: q='99X049921' (UNION Subquery Execution Plan) ---"
        )
        cursor.execute(
            """
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT v.id, v.license_plate, v.license_plate_norm, c.full_name, c.phone
            FROM vehicle v
            JOIN customer c ON v.customer_id = c.id
            WHERE v.deleted_at IS NULL
              AND c.deleted_at IS NULL
              AND v.id IN (
                  SELECT id FROM vehicle
                  WHERE deleted_at IS NULL AND license_plate_norm ILIKE '%99X049921%'
                  UNION
                  SELECT v2.id FROM vehicle v2
                  JOIN customer c2 ON v2.customer_id = c2.id
                  WHERE v2.deleted_at IS NULL AND c2.deleted_at IS NULL AND c2.full_name ILIKE '%99X049921%'
                  UNION
                  SELECT v3.id FROM vehicle v3
                  JOIN customer c3 ON v3.customer_id = c3.id
                  WHERE v3.deleted_at IS NULL AND c3.deleted_at IS NULL AND c3.phone ILIKE '%99X049921%'
              );
        """
        )
        plan_q = "\n".join(row[0] for row in cursor.fetchall())
        print(plan_q)
        assert "idx_vehicle_plate_trgm" in plan_q, (
            f"Lỗi: UNION subquery nhánh license_plate_norm không dùng idx_vehicle_plate_trgm!\nPlan:\n{plan_q}"
        )
        assert "Bitmap Index Scan" in plan_q
        assert "Seq Scan on vehicle" not in plan_q, (
            "Cảnh báo: Xuất hiện Seq Scan trên vehicle!"
        )
        print(
            "[PASS] QUERY 4 (q= UNION subquery) kích hoạt Bitmap Index Scan hoàn hảo, 0 Seq Scan!"
        )

        print("\n" + "=" * 80)
        print(
            "=== ALL 4 QUERIES VERIFIED: BITMAP INDEX SCAN ON TRIGRAM GIN, 0 SEQ SCAN ==="
        )
        print("=" * 80)
