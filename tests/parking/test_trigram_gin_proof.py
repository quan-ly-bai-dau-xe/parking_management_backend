"""
Performance and verification proof test for Trigram GIN Indexing (TL-41).
Executes EXPLAIN (ANALYZE, BUFFERS) over >= 50,000 synthetic rows on PostgreSQL.
Proves Bitmap Index Scan on idx_proof_full_name_trgm and idx_proof_plate_trgm.
Cleans up throwaway unlogged table completely in finally block.
"""

import pytest
from django.db import connection

pytestmark = pytest.mark.django_db(transaction=True)


def test_trigram_gin_index_50k_rows_explain_proof():
    """
    Thực nghiệm chứng minh tính hiệu quả vượt bậc của chỉ mục Trigram GIN (TL-41):
    1. Tạo bảng UNLOGGED tạm thời độc lập (throwaway table).
    2. Nạp đúng 50,000 bản ghi dữ liệu tiếng Việt mô phỏng qua generate_series (< 0.5s).
    3. Đánh chỉ mục GIN với gin_trgm_ops cho full_name và license_plate_norm.
    4. Chạy EXPLAIN (ANALYZE, BUFFERS) với Direct ILIKE để chứng minh Bitmap Index Scan.
    5. Chạy EXPLAIN (ANALYZE, BUFFERS) với UPPER(...) LIKE UPPER(...) để chứng minh cạm bẫy Seq Scan của Django icontains.
    6. Dọn dẹp sạch sẽ bằng DROP TABLE CASCADE trong khối finally.
    """
    table_name = "throwaway_proof_customer_vehicle"

    with connection.cursor() as cursor:
        cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
        try:
            # 1. Tạo bảng UNLOGGED
            cursor.execute(
                f"""
                CREATE UNLOGGED TABLE {table_name} (
                    id BIGSERIAL PRIMARY KEY,
                    full_name VARCHAR(100) NOT NULL,
                    license_plate VARCHAR(20) NOT NULL,
                    license_plate_norm VARCHAR(20) NOT NULL,
                    deleted_at TIMESTAMPTZ NULL
                );
            """
            )

            # 2. Nạp >= 50,000 dòng dữ liệu mô phỏng tiếng Việt chân thực thuần SQL
            cursor.execute(
                f"""
                INSERT INTO {table_name} (full_name, license_plate, license_plate_norm)
                SELECT
                    (ARRAY['Nguyễn', 'Trần', 'Lê', 'Phạm', 'Hoàng', 'Huỳnh', 'Phan', 'Vũ'])[1 + (i % 8)] || ' ' ||
                    (ARRAY['Văn', 'Thị', 'Hữu', 'Đức', 'Minh', 'Thành'])[1 + ((i / 8) % 6)] || ' ' ||
                    (ARRAY['An', 'Bình', 'Hương', 'Linh', 'Dũng', 'Khánh', 'Sơn', 'Tâm'])[1 + ((i / 48) % 8)],
                    '51K-' || lpad((i % 1000)::text, 3, '0') || '.' || lpad(((i / 1000) % 100)::text, 2, '0'),
                    '51K' || lpad((i % 1000)::text, 3, '0') || lpad(((i / 1000) % 100)::text, 2, '0')
                FROM generate_series(1, 50000) AS i;
            """
            )

            # Xác nhận số lượng bản ghi đã sinh
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            row_count = cursor.fetchone()[0]
            assert row_count >= 50000, f"Dữ liệu sinh chưa đủ 50,000 dòng: {row_count}"

            # 3. Tạo 2 Trigram GIN indexes theo đúng quy chuẩn TL-41
            cursor.execute(
                f"""
                CREATE INDEX idx_proof_full_name_trgm ON {table_name}
                USING gin (full_name gin_trgm_ops) WHERE deleted_at IS NULL;
            """
            )
            cursor.execute(
                f"""
                CREATE INDEX idx_proof_plate_trgm ON {table_name}
                USING gin (license_plate_norm gin_trgm_ops) WHERE deleted_at IS NULL;
            """
            )
            cursor.execute(f"VACUUM ANALYZE {table_name};")

            # 4. EXPLAIN ANALYZE tìm theo tên với Direct ILIKE -> Bitmap Index Scan
            cursor.execute(
                f"""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT * FROM {table_name}
                WHERE deleted_at IS NULL AND full_name ILIKE '%Thị Hương%';
            """
            )
            name_plan_lines = [row[0] for row in cursor.fetchall()]
            name_plan_text = "\n".join(name_plan_lines)

            assert "Bitmap Index Scan on idx_proof_full_name_trgm" in name_plan_text, (
                f"Không kích hoạt Bitmap Index Scan cho full_name:\n{name_plan_text}"
            )
            assert "Bitmap Heap Scan" in name_plan_text

            # 5. EXPLAIN ANALYZE tìm theo biển số với Direct ILIKE -> Bitmap Index Scan
            cursor.execute(
                f"""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT * FROM {table_name}
                WHERE deleted_at IS NULL AND license_plate_norm ILIKE '%51K992%';
            """
            )
            plate_plan_lines = [row[0] for row in cursor.fetchall()]
            plate_plan_text = "\n".join(plate_plan_lines)

            assert "Bitmap Index Scan on idx_proof_plate_trgm" in plate_plan_text, (
                f"Không kích hoạt Bitmap Index Scan cho license_plate_norm:\n{plate_plan_text}"
            )
            assert "Bitmap Heap Scan" in plate_plan_text

            # 6. Chứng minh cạm bẫy: Django mặc định icontains với UPPER(...) bị fallback Seq Scan
            cursor.execute(
                f"""
                EXPLAIN (ANALYZE, BUFFERS)
                SELECT * FROM {table_name}
                WHERE deleted_at IS NULL AND UPPER(full_name::text) LIKE UPPER('%Thị Hương%');
            """
            )
            django_plan_lines = [row[0] for row in cursor.fetchall()]
            django_plan_text = "\n".join(django_plan_lines)

            assert "Seq Scan" in django_plan_text
            assert "idx_proof_full_name_trgm" not in django_plan_text

        finally:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE;")
