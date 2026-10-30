-- ============================================================================
-- Car Parking Lot Management System Backend
-- Enterprise Reference & Sample Operational Seed Script (Schema v2 — Frontend-First)
-- Target PostgreSQL Version: PostgreSQL 18.6
-- File: db/02-seed.sql
-- Execution standard: psql -v ON_ERROR_STOP=1 -f db/02-seed.sql
-- Non-destructive & Idempotent: Pure insertion script (ADR-0003 & Rule 05).
--   Running this file a second time produces zero errors and changes zero row counts.
-- Structure:
--   - PART 1: Reference Lookup Data (required in all environments; TL-02..TL-20).
--   - PART 2: Sample Operational Data (removable block for development/QA/demo;
--     synthetic personal data generated from fixed PRNG seed 20261017, RFC 2606
--     example domains only, and Django '!' unusable password hashes).
-- ============================================================================

BEGIN;

SET client_encoding = 'UTF8';

-- ============================================================================
-- PART 1: REFERENCE & LOOKUP DATA (REQUIRED IN PRODUCTION)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1.1. EMPLOYEE POSITIONS CATALOG (POSITION LOOKUP — TL-11)
-- ----------------------------------------------------------------------------
INSERT INTO position (code, name, description)
VALUES
    ('QL', 'Quản lý', 'Facility and operations manager ("Quản lý" on Quản lý nhân viên - Smart mobility.png, TL-11)'),
    ('NVVH', 'Nhân viên vận hành', 'Parking lot operations staff ("Nhân viên vận hành" on Quản lý nhân viên - Smart mobility.png, TL-11)'),
    ('NVTN', 'Nhân viên thu ngân', 'Parking lot cashier staff ("Nhân viên thu ngân" on Quản lý nhân viên - Smart mobility.png, TL-11)'),
    ('KTV', 'Kỹ thuật viên', 'Parking facility and equipment technician ("Kỹ thuật viên" on Quản lý nhân viên - Smart mobility.png, TL-11)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 1.2. VEHICLE TYPES CATALOG (CARS ONLY — TL-09, TL-20)
-- ----------------------------------------------------------------------------
INSERT INTO vehicle_type (code, name, description)
VALUES
    ('CAR', 'Ô tô', 'Standard passenger automobile ("Ô tô" on Quản lý xe — Smart Mobility.png, TL-09, TL-20)'),
    ('EV', 'Xe điện', 'Electric passenger automobile ("Xe điện" / ô tô điện on Quản lý xe — Smart Mobility.png, TL-09, TL-20)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 1.3. TICKET TARIFF TYPES CATALOG (TICKET TYPE LOOKUP — TL-10, TL-22)
-- ----------------------------------------------------------------------------
INSERT INTO ticket_type (code, name, duration_days, default_price, description)
VALUES
    ('DAILY', 'Vé ngày', 1, 50000.00, 'Daily parking ticket at 50,000 VND ("Vé ngày", "50.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('MONTHLY', 'Vé tháng', 30, 500000.00, 'Monthly parking ticket at 500,000 VND ("Vé tháng", "500.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('QUARTERLY', 'Vé quý', 90, 1200000.00, 'Quarterly parking ticket at 1,200,000 VND ("Vé quý", "1.200.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('YEARLY', 'Vé năm', 365, 4800000.00, 'Annual parking ticket ("Vé năm" on Quản lý vé — Smart Mobility.png; decided default 4,800,000 VND per OQ-79, TL-10, TL-22)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 1.4. ADMINISTRATIVE BOUNDARY CATALOG (TL-11, TL-15, OQ-50)
-- ----------------------------------------------------------------------------
INSERT INTO administrative_province (code, name)
VALUES
    ('49', 'Tỉnh Quảng Nam'),
    ('48', 'Thành phố Đà Nẵng')
ON CONFLICT (code) DO NOTHING;

INSERT INTO administrative_district (province_id, code, name)
SELECT p.id, d.code, d.name
FROM (
    VALUES
        ('49', 'DB', 'Thị xã Điện Bàn'),
        ('48', 'HC', 'Quận Hải Châu')
) AS d(p_code, code, name)
JOIN administrative_province p ON p.code = d.p_code
ON CONFLICT (code) DO NOTHING;

INSERT INTO administrative_ward (district_id, code, name)
SELECT dist.id, w.code, w.name
FROM (
    VALUES
        ('DB', 'DN', 'Phường Điện Ngọc'),
        ('HC', 'TT', 'Phường Thạch Thang')
) AS w(d_code, code, name)
JOIN administrative_district dist ON dist.code = w.d_code
ON CONFLICT (code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 1.5. DEFAULT PARKING LOT FACILITY (TL-02)
-- ----------------------------------------------------------------------------
INSERT INTO parking_lot (code, name, address, is_active)
VALUES (
    'SMART_MOBILITY',
    'Bãi xe Smart Mobility',
    'Số 02 Nguyễn Văn Linh, Phường Thạch Thang, Quận Hải Châu, Thành phố Đà Nẵng',
    TRUE
)
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;


-- ============================================================================
-- PART 2: SAMPLE OPERATIONAL DATA (REMOVABLE BLOCK — BEGIN)
-- To deploy only reference data in production, remove from this banner down to
-- the matching "PART 2: SAMPLE OPERATIONAL DATA (REMOVABLE BLOCK — END)" banner
-- right before COMMIT. All personal data below is 100% synthetic (PRNG seed
-- 20261017, RFC 2606 example domains, Django '!' unusable password hashes).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1. PARKING FLOORS (3 FLOORS: Tầng B1, Tầng B2, Tầng F1 — TL-02)
-- ----------------------------------------------------------------------------
INSERT INTO parking_floor (lot_id, code, name, sort_order)
SELECT pl.id, f.code, f.name, f.sort_order
FROM (
    VALUES
        ('B1', 'Tầng B1', 1),
        ('B2', 'Tầng B2', 2),
        ('F1', 'Tầng F1', 3)
) AS f(code, name, sort_order)
CROSS JOIN parking_lot pl
WHERE pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
ON CONFLICT (lot_id, code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.2. PARKING ZONES (3 ZONES PER FLOOR: Khu A, Khu B, Khu C = 9 ZONES — TL-02)
-- ----------------------------------------------------------------------------
INSERT INTO parking_zone (floor_id, code, name, description)
SELECT pf.id, z.code, z.name, z.description
FROM (
    VALUES
        ('B1', 'A', 'Khu A', 'Dãy ô tô tiêu chuẩn Tầng B1 (A-01 .. A-20)'),
        ('B1', 'B', 'Khu B', 'Dãy ô tô ưu tiên và tiêu chuẩn Tầng B1 (B-01 .. B-15)'),
        ('B1', 'C', 'Khu C', 'Dãy trạm sạc ô tô điện và tiêu chuẩn Tầng B1 (C-01 .. C-15)'),
        ('B2', 'A', 'Khu A', 'Dãy ô tô tiêu chuẩn Tầng B2 (A-01 .. A-20)'),
        ('B2', 'B', 'Khu B', 'Dãy ô tô ưu tiên và tiêu chuẩn Tầng B2 (B-01 .. B-15)'),
        ('B2', 'C', 'Khu C', 'Dãy trạm sạc ô tô điện và tiêu chuẩn Tầng B2 (C-01 .. C-15)'),
        ('F1', 'A', 'Khu A', 'Dãy ô tô tiêu chuẩn Tầng F1 ngoài trời (A-01 .. A-20)'),
        ('F1', 'B', 'Khu B', 'Dãy ô tô ưu tiên và tiêu chuẩn Tầng F1 (B-01 .. B-15)'),
        ('F1', 'C', 'Khu C', 'Dãy trạm sạc ô tô điện và tiêu chuẩn Tầng F1 (C-01 .. C-15)')
) AS z(floor_code, code, name, description)
JOIN parking_floor pf ON pf.code = z.floor_code AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
ON CONFLICT (floor_id, code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.3. PARKING SLOTS (150 SLOTS TOTAL: 50 PER FLOOR — TL-02, TL-03)
--   - Khu A: A-01..A-20 (20 STANDARD slots per floor; B1/A-08 is MAINTENANCE)
--   - Khu B: B-01..B-08 PRIORITY + B-09..B-15 STANDARD (15 slots per floor)
--   - Khu C: C-01..C-08 EV_CHARGING + C-09..C-15 STANDARD (15 slots per floor; B2/C-08 is MAINTENANCE)
-- ----------------------------------------------------------------------------
INSERT INTO parking_slot (zone_id, code, slot_kind, status, map_row, map_col, width, length, height, notes)
SELECT
    pz.id,
    s.slot_code,
    s.slot_kind,
    s.init_status,
    s.map_row,
    s.map_col,
    s.width,
    s.length,
    s.height,
    s.notes
FROM (
    VALUES
        ('B1', 'A', 'A-01', 'STANDARD', 'AVAILABLE', 1, 1, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-02', 'STANDARD', 'AVAILABLE', 1, 2, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-03', 'STANDARD', 'AVAILABLE', 1, 3, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-04', 'STANDARD', 'AVAILABLE', 1, 4, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-05', 'STANDARD', 'AVAILABLE', 1, 5, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-06', 'STANDARD', 'AVAILABLE', 1, 6, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-07', 'STANDARD', 'AVAILABLE', 1, 7, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-08', 'STANDARD', 'MAINTENANCE', 1, 8, 2.50, 5.00, 2.20, 'Đang bảo trì cảm biến siêu âm tại ô A-08'),
        ('B1', 'A', 'A-09', 'STANDARD', 'AVAILABLE', 1, 9, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-10', 'STANDARD', 'AVAILABLE', 1, 10, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-11', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-12', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-13', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-14', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-15', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-16', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-17', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-18', 'STANDARD', 'AVAILABLE', 2, 8, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-19', 'STANDARD', 'AVAILABLE', 2, 9, 2.50, 5.00, 2.20, NULL),
        ('B1', 'A', 'A-20', 'STANDARD', 'AVAILABLE', 2, 10, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-01', 'PRIORITY', 'AVAILABLE', 1, 1, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('B1', 'B', 'B-02', 'PRIORITY', 'AVAILABLE', 1, 2, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('B1', 'B', 'B-03', 'PRIORITY', 'AVAILABLE', 1, 3, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-04', 'PRIORITY', 'AVAILABLE', 1, 4, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-05', 'PRIORITY', 'AVAILABLE', 1, 5, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-06', 'PRIORITY', 'AVAILABLE', 1, 6, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-07', 'PRIORITY', 'AVAILABLE', 1, 7, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-08', 'PRIORITY', 'AVAILABLE', 1, 8, 2.80, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('B1', 'B', 'B-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('B1', 'C', 'C-01', 'EV_CHARGING', 'AVAILABLE', 1, 1, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('B1', 'C', 'C-02', 'EV_CHARGING', 'AVAILABLE', 1, 2, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('B1', 'C', 'C-03', 'EV_CHARGING', 'AVAILABLE', 1, 3, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-04', 'EV_CHARGING', 'AVAILABLE', 1, 4, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-05', 'EV_CHARGING', 'AVAILABLE', 1, 5, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-06', 'EV_CHARGING', 'AVAILABLE', 1, 6, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-07', 'EV_CHARGING', 'AVAILABLE', 1, 7, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-08', 'EV_CHARGING', 'AVAILABLE', 1, 8, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.60, 5.20, 2.20, NULL),
        ('B1', 'C', 'C-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.60, 5.20, 2.20, NULL),
        ('B2', 'A', 'A-01', 'STANDARD', 'AVAILABLE', 1, 1, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-02', 'STANDARD', 'AVAILABLE', 1, 2, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-03', 'STANDARD', 'AVAILABLE', 1, 3, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-04', 'STANDARD', 'AVAILABLE', 1, 4, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-05', 'STANDARD', 'AVAILABLE', 1, 5, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-06', 'STANDARD', 'AVAILABLE', 1, 6, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-07', 'STANDARD', 'AVAILABLE', 1, 7, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-08', 'STANDARD', 'AVAILABLE', 1, 8, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-09', 'STANDARD', 'AVAILABLE', 1, 9, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-10', 'STANDARD', 'AVAILABLE', 1, 10, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-11', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-12', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-13', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-14', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-15', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-16', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-17', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-18', 'STANDARD', 'AVAILABLE', 2, 8, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-19', 'STANDARD', 'AVAILABLE', 2, 9, 2.50, 5.00, 2.20, NULL),
        ('B2', 'A', 'A-20', 'STANDARD', 'AVAILABLE', 2, 10, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-01', 'PRIORITY', 'AVAILABLE', 1, 1, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('B2', 'B', 'B-02', 'PRIORITY', 'AVAILABLE', 1, 2, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('B2', 'B', 'B-03', 'PRIORITY', 'AVAILABLE', 1, 3, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-04', 'PRIORITY', 'AVAILABLE', 1, 4, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-05', 'PRIORITY', 'AVAILABLE', 1, 5, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-06', 'PRIORITY', 'AVAILABLE', 1, 6, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-07', 'PRIORITY', 'AVAILABLE', 1, 7, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-08', 'PRIORITY', 'AVAILABLE', 1, 8, 2.80, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('B2', 'B', 'B-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('B2', 'C', 'C-01', 'EV_CHARGING', 'AVAILABLE', 1, 1, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('B2', 'C', 'C-02', 'EV_CHARGING', 'AVAILABLE', 1, 2, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('B2', 'C', 'C-03', 'EV_CHARGING', 'AVAILABLE', 1, 3, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-04', 'EV_CHARGING', 'AVAILABLE', 1, 4, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-05', 'EV_CHARGING', 'AVAILABLE', 1, 5, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-06', 'EV_CHARGING', 'AVAILABLE', 1, 6, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-07', 'EV_CHARGING', 'AVAILABLE', 1, 7, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-08', 'EV_CHARGING', 'MAINTENANCE', 1, 8, 2.60, 5.20, 2.20, 'Bảo trì trụ sạc điện AC 22kW định kỳ'),
        ('B2', 'C', 'C-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.60, 5.20, 2.20, NULL),
        ('B2', 'C', 'C-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.60, 5.20, 2.20, NULL),
        ('F1', 'A', 'A-01', 'STANDARD', 'AVAILABLE', 1, 1, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-02', 'STANDARD', 'AVAILABLE', 1, 2, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-03', 'STANDARD', 'AVAILABLE', 1, 3, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-04', 'STANDARD', 'AVAILABLE', 1, 4, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-05', 'STANDARD', 'AVAILABLE', 1, 5, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-06', 'STANDARD', 'AVAILABLE', 1, 6, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-07', 'STANDARD', 'AVAILABLE', 1, 7, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-08', 'STANDARD', 'AVAILABLE', 1, 8, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-09', 'STANDARD', 'AVAILABLE', 1, 9, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-10', 'STANDARD', 'AVAILABLE', 1, 10, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-11', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-12', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-13', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-14', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-15', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-16', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-17', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-18', 'STANDARD', 'AVAILABLE', 2, 8, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-19', 'STANDARD', 'AVAILABLE', 2, 9, 2.50, 5.00, 2.20, NULL),
        ('F1', 'A', 'A-20', 'STANDARD', 'AVAILABLE', 2, 10, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-01', 'PRIORITY', 'AVAILABLE', 1, 1, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('F1', 'B', 'B-02', 'PRIORITY', 'AVAILABLE', 1, 2, 2.80, 5.00, 2.20, 'Ô đỗ xe ưu tiên gần lối vào thang máy'),
        ('F1', 'B', 'B-03', 'PRIORITY', 'AVAILABLE', 1, 3, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-04', 'PRIORITY', 'AVAILABLE', 1, 4, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-05', 'PRIORITY', 'AVAILABLE', 1, 5, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-06', 'PRIORITY', 'AVAILABLE', 1, 6, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-07', 'PRIORITY', 'AVAILABLE', 1, 7, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-08', 'PRIORITY', 'AVAILABLE', 1, 8, 2.80, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.50, 5.00, 2.20, NULL),
        ('F1', 'B', 'B-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.50, 5.00, 2.20, NULL),
        ('F1', 'C', 'C-01', 'EV_CHARGING', 'AVAILABLE', 1, 1, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('F1', 'C', 'C-02', 'EV_CHARGING', 'AVAILABLE', 1, 2, 2.60, 5.20, 2.20, 'Ô đỗ tích hợp trụ sạc nhanh ô tô điện'),
        ('F1', 'C', 'C-03', 'EV_CHARGING', 'AVAILABLE', 1, 3, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-04', 'EV_CHARGING', 'AVAILABLE', 1, 4, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-05', 'EV_CHARGING', 'AVAILABLE', 1, 5, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-06', 'EV_CHARGING', 'AVAILABLE', 1, 6, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-07', 'EV_CHARGING', 'AVAILABLE', 1, 7, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-08', 'EV_CHARGING', 'AVAILABLE', 1, 8, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-09', 'STANDARD', 'AVAILABLE', 2, 1, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-10', 'STANDARD', 'AVAILABLE', 2, 2, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-11', 'STANDARD', 'AVAILABLE', 2, 3, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-12', 'STANDARD', 'AVAILABLE', 2, 4, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-13', 'STANDARD', 'AVAILABLE', 2, 5, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-14', 'STANDARD', 'AVAILABLE', 2, 6, 2.60, 5.20, 2.20, NULL),
        ('F1', 'C', 'C-15', 'STANDARD', 'AVAILABLE', 2, 7, 2.60, 5.20, 2.20, NULL)
) AS s(floor_code, zone_code, slot_code, slot_kind, init_status, map_row, map_col, width, length, height, notes)
JOIN parking_floor pf ON pf.code = s.floor_code AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.code = s.zone_code AND pz.deleted_at IS NULL
ON CONFLICT (zone_id, code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.4. SLOT ALLOWED VEHICLE TYPES (TL-03, TL-20)
--   - All 150 slots allow EV ('Xe điện' / electric car).
--   - All STANDARD and PRIORITY slots (126 slots) also allow CAR ('Ô tô').
-- ----------------------------------------------------------------------------
INSERT INTO slot_allowed_vehicle_type (slot_id, vehicle_type_id)
SELECT ps.id, vt.id
FROM parking_slot ps
JOIN parking_zone pz ON pz.id = ps.zone_id AND pz.deleted_at IS NULL
JOIN parking_floor pf ON pf.id = pz.floor_id AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
JOIN vehicle_type vt ON vt.deleted_at IS NULL
WHERE ps.deleted_at IS NULL
  AND (vt.code = 'EV' OR (vt.code = 'CAR' AND ps.slot_kind IN ('STANDARD', 'PRIORITY')))
ON CONFLICT (slot_id, vehicle_type_id) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.5. PARKING GATES (5 GATES: Cổng vào 1/2, Cổng ra 1/2/3 — TL-06)
-- ----------------------------------------------------------------------------
INSERT INTO parking_gate (lot_id, code, name, direction, camera_status, is_auto_scan, is_active)
SELECT pl.id, g.code, g.name, g.direction, g.camera_status, g.is_auto_scan, g.is_active
FROM (
    VALUES
        ('IN_01',  'Cổng vào 1', 'IN',  'ONLINE',    TRUE,  TRUE),
        ('IN_02',  'Cổng vào 2', 'IN',  'ONLINE',    TRUE,  TRUE),
        ('OUT_01', 'Cổng ra 1',  'OUT', 'LOW_LIGHT', TRUE,  TRUE),
        ('OUT_02', 'Cổng ra 2',  'OUT', 'ONLINE',    TRUE,  TRUE),
        ('OUT_03', 'Cổng ra 3',  'OUT', 'ONLINE',    FALSE, TRUE)
) AS g(code, name, direction, camera_status, is_auto_scan, is_active)
CROSS JOIN parking_lot pl
WHERE pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
ON CONFLICT (lot_id, code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.6. SYSTEM ACCOUNTS (20 ACCOUNTS: 1 MANAGER, 7 EMPLOYEE, 12 CUSTOMER — TL-01, TL-21)
--   All password_hash values use Django's unusable-password prefix '!' + 40
--   deterministic alphanumeric characters (cannot authenticate until reset).
-- ----------------------------------------------------------------------------
INSERT INTO account (email, phone, password_hash, role, is_active, last_login_at)
VALUES
    ('hoang.dinh.khang@example.com', '0880721788', '!llp4Vi0ulafwxv3xktvXAwiXkJ4v8cMts9V8fQaE', 'MANAGER', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('luong.mai.phuong@example.org', '0385211625', '!E6jx193Cyen0LYHbaggJh4BtFEXbRw9shHQiJmOr', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('do.minh.quan@example.net', '0760098704', '!Mw1JDg60wCADMDDhvHGBrfJGvwwByxD1hiWsgFAv', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('truong.ngoc.bich@example.com', '0374179898', '!1pV9O7ooVSRT4k9yPB3uvMesIxfDQdcxASGP9mxM', 'EMPLOYEE', FALSE, '2026-09-10 17:30:00+07'::TIMESTAMPTZ),
    ('vu.quoc.hung@example.org', '0361681236', '!TBtnGqDHNZdZDzKQNdQ4Sw58g6ytwMnsPMgYffnA', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('phan.thanh.thao@example.net', '0356582610', '!3qEhSwoyvkygzqgJI0gx8d32Q71TxPYQ4dNIYdvx', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('ngo.gia.bao@example.com', '0864769738', '!fMRLWGbinmVscfJWo1HmExEK38YUJCByYbj482ja', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('dinh.lan.anh@example.org', '0707739639', '!U5baTmrr7Q0ooo2DacmYGciCUkzsYyATMXxV31e2', 'EMPLOYEE', TRUE, '2026-10-17 07:05:00+07'::TIMESTAMPTZ),
    ('trinh.xuan.truong@example.com', '0868851325', '!EEQ6iA4trd3REvq6SLnQdhLEa3ZuEBp7VMKLZDRm', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('bui.khanh.doan@example.org', '0348083802', '!KO9wxoq4WS0BHsHXAeV8hMqx1QodybQyISzE7wGt', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('lam.hoang.viet@example.net', '0790226163', '!XbdFKsAaL2cXgqa3VFODVpLfA2A8E5UWxfIzdKso', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('doan.tuyet.mai@example.com', '0779009950', '!JGvi7DK0fo1HiO6v6nPzxTpIcM66JOepnjzxnN42', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('ho.trong.nghia@example.org', '0789632200', '!U0K2g0B312E2ontN1052JVAnRTCKjJVVYds9OBM8', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('ta.minh.chau@example.net', '0708960990', '!wEX7lFt7yqMjBHWUc1CK97JrUiwM7xpYOaKT7JpH', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('cao.tien.dung@example.com', '0327855040', '!EcDeO95IZ5MHRJ1fIYDxVgmDdzOE1Pug9KS4FEQs', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('duong.hong.nhung@example.org', '0332790866', '!ZR0oBqmkRna21d97OJ6rjGYK7TyMmENpFLnJ8zUn', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('ha.manh.cuong@example.net', '0861032661', '!FlMLLALLQW4wpka4Ksns1poZvCAFjBhlko9K5svc', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('mai.phuong.thao@example.com', '0781281571', '!UU83ZWiY7FvRxqeX8MbVHDbeKFVCrnE2RW8qjYZw', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('kieu.quoc.tuan@example.org', '0392758924', '!lIF9JTbeoxZFmxSScv5d4XPHYfz9KAnlk2kbAWyy', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ),
    ('chu.kim.oanh@example.net', '0387755825', '!1inni527okEx5nAcUfvwrFeRVKDdIWAttelX3FTa', 'CUSTOMER', TRUE, '2026-10-16 19:20:00+07'::TIMESTAMPTZ)
ON CONFLICT (lower(email)) WHERE deleted_at IS NULL AND email IS NOT NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.7. EMPLOYEES (8 EMPLOYEES: NV001..NV008 ACROSS 4 POSITIONS — TL-11, TL-18, TL-21)
-- ----------------------------------------------------------------------------
INSERT INTO employee (
    code, full_name, date_of_birth, gender, identity_card_number,
    phone, email, address, province_id, district_id, ward_id,
    position_id, account_id, status
)
SELECT
    e.code,
    e.full_name,
    e.dob::DATE,
    e.gender,
    e.cccd,
    e.phone,
    e.email,
    e.address,
    prov.id,
    dist.id,
    w.id,
    pos.id,
    acc.id,
    e.status
FROM (
    VALUES
        ('NV001', 'Hoàng Đình Khang', '1984-03-18', 'Nam', '048084786891', '0880721788', 'hoang.dinh.khang@example.com', 'Số 114 Đường Bạch Đằng', '48', 'HC', 'TT', 'QL', 'hoang.dinh.khang@example.com', 'ACTIVE'),
        ('NV002', 'Lương Thị Mai Phương', '1992-07-24', 'Nữ', '048192172039', '0385211625', 'luong.mai.phuong@example.org', 'Số 48 Đường Trần Phú', '48', 'HC', 'TT', 'NVVH', 'luong.mai.phuong@example.org', 'ACTIVE'),
        ('NV003', 'Đỗ Minh Quân', '1995-11-09', 'Nam', '049095760206', '0760098704', 'do.minh.quan@example.net', 'Số 27 Đường Trần Đại Nghĩa', '49', 'DB', 'DN', 'NVTN', 'do.minh.quan@example.net', 'ACTIVE'),
        ('NV004', 'Trương Ngọc Bích', '1990-05-14', 'Nữ', '048190462631', '0374179898', 'truong.ngoc.bich@example.com', 'Số 85 Đường Nguyễn Chí Thanh', '48', 'HC', 'TT', 'KTV', 'truong.ngoc.bich@example.com', 'INACTIVE'),
        ('NV005', 'Vũ Quốc Hưng', '1988-09-02', 'Nam', '049088571286', '0361681236', 'vu.quoc.hung@example.org', 'Số 63 Đường Lạc Long Quân', '49', 'DB', 'DN', 'NVVH', 'vu.quoc.hung@example.org', 'ACTIVE'),
        ('NV006', 'Phan Thị Thanh Thảo', '1997-01-29', 'Nữ', '048197201097', '0356582610', 'phan.thanh.thao@example.net', 'Số 19 Đường Lý Tự Trọng', '48', 'HC', 'TT', 'NVTN', 'phan.thanh.thao@example.net', 'ACTIVE'),
        ('NV007', 'Ngô Gia Bảo', '1993-12-11', 'Nam', '048093200385', '0864769738', 'ngo.gia.bao@example.com', 'Số 152 Đường Quang Trung', '48', 'HC', 'TT', 'KTV', 'ngo.gia.bao@example.com', 'ACTIVE'),
        ('NV008', 'Đinh Thị Lan Anh', NULL, NULL, NULL, '0707739639', 'dinh.lan.anh@example.org', NULL, NULL, NULL, NULL, 'NVVH', 'dinh.lan.anh@example.org', 'ACTIVE')
) AS e(code, full_name, dob, gender, cccd, phone, email, address, p_code, d_code, w_code, pos_code, acc_email, status)
JOIN position pos ON pos.code = e.pos_code AND pos.deleted_at IS NULL
LEFT JOIN administrative_province prov ON prov.code = e.p_code
LEFT JOIN administrative_district dist ON dist.code = e.d_code
LEFT JOIN administrative_ward w ON w.code = e.w_code
LEFT JOIN account acc ON lower(acc.email) = lower(e.acc_email) AND acc.deleted_at IS NULL
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.8. CUSTOMERS (20 CUSTOMERS: KH0001..KH0020, INCLUDING NULL OPTIONAL FIELDS — TL-08, TL-18, TL-21)
-- ----------------------------------------------------------------------------
INSERT INTO customer (
    code, full_name, date_of_birth, gender, identity_card_number,
    phone, email, address, province_id, district_id, ward_id,
    account_id, status, status_reason
)
SELECT
    c.code,
    c.full_name,
    c.dob::DATE,
    c.gender,
    c.cccd,
    c.phone,
    c.email,
    c.address,
    prov.id,
    dist.id,
    w.id,
    acc.id,
    c.status,
    c.status_reason
FROM (
    VALUES
        ('KH0001', 'Trịnh Xuân Trường', '1979-04-12', 'Nam', '048079995469', '0868851325', 'trinh.xuan.truong@example.com', 'Số 32 Đường Đống Đa', '48', 'HC', 'TT', 'trinh.xuan.truong@example.com', 'ACTIVE', NULL),
        ('KH0002', 'Bùi Thị Khánh Đoan', '1986-08-23', 'Nữ', '048186360599', '0348083802', 'bui.khanh.doan@example.org', 'Số 76 Đường Lê Duẩn', '48', 'HC', 'TT', 'bui.khanh.doan@example.org', 'ACTIVE', NULL),
        ('KH0003', 'Lâm Hoàng Việt', '1991-02-15', 'Nam', '049091369040', '0790226163', 'lam.hoang.viet@example.net', 'Số 41 Đường Võ Như Hưng', '49', 'DB', 'DN', 'lam.hoang.viet@example.net', 'ACTIVE', NULL),
        ('KH0004', 'Đoàn Thị Tuyết Mai', '1983-10-05', 'Nữ', '048183494269', '0779009950', 'doan.tuyet.mai@example.com', 'Số 108 Đường Hải Phòng', '48', 'HC', 'TT', 'doan.tuyet.mai@example.com', 'ACTIVE', NULL),
        ('KH0005', 'Hồ Trọng Nghĩa', '1975-06-19', 'Nam', '049075989608', '0789632200', 'ho.trong.nghia@example.org', 'Số 15 Đường Dũng Sĩ Điện Ngọc', '49', 'DB', 'DN', 'ho.trong.nghia@example.org', 'ACTIVE', NULL),
        ('KH0006', 'Tạ Thị Minh Châu', '1994-12-03', 'Nữ', '048194509247', '0708960990', 'ta.minh.chau@example.net', 'Số 205 Đường Trần Phú', '48', 'HC', 'TT', 'ta.minh.chau@example.net', 'ACTIVE', NULL),
        ('KH0007', 'Cao Tiến Dũng', '1989-01-27', 'Nam', '048089638581', '0327855040', 'cao.tien.dung@example.com', 'Số 54 Đường Bạch Đằng', '48', 'HC', 'TT', 'cao.tien.dung@example.com', 'ACTIVE', NULL),
        ('KH0008', 'Dương Thị Hồng Nhung', '1998-09-14', 'Nữ', '049198020105', '0332790866', 'duong.hong.nhung@example.org', 'Số 88 Đường Trần Đại Nghĩa', '49', 'DB', 'DN', 'duong.hong.nhung@example.org', 'ACTIVE', NULL),
        ('KH0009', 'Hà Mạnh Cường', '1981-07-08', 'Nam', '048081569435', '0861032661', 'ha.manh.cuong@example.net', 'Số 129 Đường Nguyễn Chí Thanh', '48', 'HC', 'TT', 'ha.manh.cuong@example.net', 'ACTIVE', NULL),
        ('KH0010', 'Mai Thị Phương Thảo', '2001-03-21', 'Nữ', '048301592950', '0781281571', 'mai.phuong.thao@example.com', 'Số 67 Đường Lý Tự Trọng', '48', 'HC', 'TT', 'mai.phuong.thao@example.com', 'ACTIVE', NULL),
        ('KH0011', 'Kiều Quốc Tuấn', '1972-11-30', 'Nam', '049072575924', '0392758924', 'kieu.quoc.tuan@example.org', 'Số 92 Đường Lạc Long Quân', '49', 'DB', 'DN', 'kieu.quoc.tuan@example.org', 'ACTIVE', NULL),
        ('KH0012', 'Chu Thị Kim Oanh', '1996-05-17', 'Nữ', '048196926984', '0387755825', 'chu.kim.oanh@example.net', 'Số 14 Đường Quang Trung', '48', 'HC', 'TT', 'chu.kim.oanh@example.net', 'ACTIVE', NULL),
        ('KH0013', 'Tống Văn Hòa', NULL, NULL, '048092433647', '0978224238', NULL, NULL, NULL, NULL, NULL, NULL, 'ACTIVE', NULL),
        ('KH0014', 'Lại Thị Thu Thủy', NULL, NULL, '049193598737', '0375245600', NULL, NULL, NULL, NULL, NULL, NULL, 'ACTIVE', NULL),
        ('KH0015', 'Nghiêm Xuân Bách', NULL, NULL, '048094844842', '0705599160', NULL, NULL, NULL, NULL, NULL, NULL, 'ACTIVE', NULL),
        ('KH0016', 'Từ Thị Ngọc Diệp', NULL, NULL, '049195401225', '0886104084', NULL, NULL, NULL, NULL, NULL, NULL, 'ACTIVE', NULL),
        ('KH0017', 'Quách Đình Phong', '1985-02-09', 'Nam', '048085942100', '0771732321', 'quach.dinh.phong@example.com', 'Số 173 Đường Lê Duẩn', '48', 'HC', 'TT', NULL, 'SUSPENDED', 'Tạm ngừng sử dụng dịch vụ theo yêu cầu chủ xe khi đi công tác dài ngày'),
        ('KH0018', 'Đàm Thị Yến Nhi', '2000-08-11', 'Nữ', '049300512910', '0388194634', 'dam.yen.nhi@example.org', 'Số 39 Đường Võ Như Hưng', '49', 'DB', 'DN', NULL, 'SUSPENDED', 'Tạm ngừng để cập nhật lại giấy chứng nhận đăng ký phương tiện'),
        ('KH0019', 'Lục Văn Khải', '1978-12-25', 'Nam', '048078749185', '0704893550', 'luc.van.khai@example.net', 'Số 45 Đường Đống Đa', '48', 'HC', 'TT', NULL, 'BLACKLISTED', 'Nợ cước phí đỗ xe quá hạn thanh toán hơn 60 ngày'),
        ('KH0020', 'Sơn Thị Bích Hợp', '1993-04-03', 'Nữ', '049193984241', '0766606745', 'son.bich.hop@example.com', 'Số 121 Đường Trần Đại Nghĩa', '49', 'DB', 'DN', NULL, 'BLACKLISTED', 'Vi phạm quy định an toàn giao thông trong khuôn viên bãi đỗ xe')
) AS c(code, full_name, dob, gender, cccd, phone, email, address, p_code, d_code, w_code, acc_email, status, status_reason)
LEFT JOIN administrative_province prov ON prov.code = c.p_code
LEFT JOIN administrative_district dist ON dist.code = c.d_code
LEFT JOIN administrative_ward w ON w.code = c.w_code
LEFT JOIN account acc ON c.acc_email IS NOT NULL AND lower(acc.email) = lower(c.acc_email) AND acc.deleted_at IS NULL
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.9. VEHICLES (30 VEHICLES: XE0001..XE0030 OF TYPES CAR & EV — TL-09, TL-20)
-- ----------------------------------------------------------------------------
INSERT INTO vehicle (
    code, license_plate, model_name, brand, color,
    image_url, notes, vehicle_type_id, customer_id
)
SELECT
    v.code,
    v.license_plate,
    v.model_name,
    v.brand,
    v.color,
    v.image_url,
    v.notes,
    vt.id,
    cust.id
FROM (
    VALUES
        ('XE0001', '43K-860.50', 'Vios 1.5G', 'Toyota', 'Trắng', '/media/vehicles/xe0001.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0001'),
        ('XE0002', '92F-187.13', 'VF 8 Plus', 'VinFast', 'Xanh rêu', '/media/vehicles/xe0002.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'EV', 'KH0002'),
        ('XE0003', '43X-433.53', 'Accent 1.4AT', 'Hyundai', 'Bạc', NULL, 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0003'),
        ('XE0004', '43B-40962', 'CX-5 2.0 Premium', 'Mazda', 'Đỏ', '/media/vehicles/xe0004.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0004'),
        ('XE0005', '92E-750.51', 'VF e34', 'VinFast', 'Trắng', '/media/vehicles/xe0005.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'EV', 'KH0005'),
        ('XE0006', '77K-893.90', 'Seltos 1.4 Turbo', 'Kia', 'Vàng', NULL, 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0006'),
        ('XE0007', '43T-814.62', 'City RS', 'Honda', 'Đen', '/media/vehicles/xe0007.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0007'),
        ('XE0008', '92V-27566', 'VF 5 Plus', 'VinFast', 'Xanh dương', '/media/vehicles/xe0008.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'EV', 'KH0008'),
        ('XE0009', '75E-689.74', 'Ranger Wildtrak', 'Ford', 'Cam', NULL, 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0009'),
        ('XE0010', '43P-613.59', 'Xpander AT', 'Mitsubishi', 'Nâu', '/media/vehicles/xe0010.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0010'),
        ('XE0011', '92V-929.32', 'Camry 2.5Q', 'Toyota', 'Đen', '/media/vehicles/xe0011.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0001'),
        ('XE0012', '75V-56297', 'VF 9 Plus', 'VinFast', 'Trắng', NULL, 'Phương tiện đăng ký gói vé định kỳ', 'EV', 'KH0002'),
        ('XE0013', '43G-357.11', 'Tucson 2.0', 'Hyundai', 'Xám', '/media/vehicles/xe0013.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0003'),
        ('XE0014', '92B-837.72', 'Mazda3 1.5L Luxury', 'Mazda', 'Trắng', '/media/vehicles/xe0014.jpg', 'Phương tiện đăng ký gói vé định kỳ', 'CAR', 'KH0004'),
        ('XE0015', '30H-504.96', 'VF 6 Plus', 'VinFast', 'Xanh rêu', NULL, 'Phương tiện đăng ký gói vé định kỳ', 'EV', 'KH0005'),
        ('XE0016', '43M-14723', 'Carnival 2.2D', 'Kia', 'Đen', '/media/vehicles/xe0016.jpg', NULL, 'CAR', 'KH0006'),
        ('XE0017', '92V-661.69', 'CR-V L', 'Honda', 'Bạc', '/media/vehicles/xe0017.jpg', NULL, 'CAR', 'KH0007'),
        ('XE0018', '76C-752.60', 'VF 7 Plus', 'VinFast', 'Đỏ', NULL, NULL, 'EV', 'KH0008'),
        ('XE0019', '43K-367.67', 'Everest Titanium', 'Ford', 'Đen', '/media/vehicles/xe0019.jpg', NULL, 'CAR', 'KH0009'),
        ('XE0020', '92G-11274', 'Corolla Cross 1.8V', 'Toyota', 'Xám', '/media/vehicles/xe0020.jpg', NULL, 'CAR', 'KH0010'),
        ('XE0021', '76K-438.79', 'Santa Fe 2.5', 'Hyundai', 'Trắng', NULL, NULL, 'CAR', 'KH0011'),
        ('XE0022', '43P-163.22', 'Ioniq 5 Prestige', 'Hyundai', 'Bạc', '/media/vehicles/xe0022.jpg', NULL, 'EV', 'KH0012'),
        ('XE0023', '92N-954.16', 'K3 1.6 Premium', 'Kia', 'Đỏ', '/media/vehicles/xe0023.jpg', NULL, 'CAR', 'KH0013'),
        ('XE0024', '79Y-65161', 'Civic RS', 'Honda', 'Xám', NULL, NULL, 'CAR', 'KH0014'),
        ('XE0025', '43C-276.58', 'VF 8 Eco', 'VinFast', 'Đen', '/media/vehicles/xe0025.jpg', NULL, 'EV', 'KH0015'),
        ('XE0026', '92Y-146.47', 'CX-8 Luxury', 'Mazda', 'Đen', '/media/vehicles/xe0026.jpg', NULL, 'CAR', 'KH0016'),
        ('XE0027', '92P-175.17', 'Creta 1.5', 'Hyundai', 'Trắng', NULL, NULL, 'CAR', 'KH0017'),
        ('XE0028', '43A-57382', 'Atto 3 Dynamic', 'BYD', 'Xanh dương', '/media/vehicles/xe0028.jpg', NULL, 'EV', 'KH0018'),
        ('XE0029', '92E-227.97', 'Veloz Cross', 'Toyota', 'Bạc', '/media/vehicles/xe0029.jpg', NULL, 'CAR', 'KH0019'),
        ('XE0030', '75D-216.14', 'Wuling Mini EV', 'Wuling', 'Vàng', NULL, NULL, 'EV', 'KH0020')
) AS v(code, license_plate, model_name, brand, color, image_url, notes, vtype_code, cust_code)
JOIN vehicle_type vt ON vt.code = v.vtype_code AND vt.deleted_at IS NULL
JOIN customer cust ON cust.code = v.cust_code AND cust.deleted_at IS NULL
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.10. TICKETS (25 TICKETS: VT0001..VT0025 ACROSS 4 TYPES & 4 STATUSES — TL-10)
-- ----------------------------------------------------------------------------
INSERT INTO ticket (
    code, vehicle_id, customer_id, slot_id, ticket_type_id,
    issued_by, price, effective_from, effective_to, status, notes, created_at
)
SELECT
    t.code,
    veh.id,
    veh.customer_id,
    ps.id,
    tt.id,
    emp.id,
    t.price::NUMERIC(12, 2),
    t.effective_from::TIMESTAMPTZ,
    t.effective_to::TIMESTAMPTZ,
    t.status,
    t.notes,
    t.effective_from::TIMESTAMPTZ
FROM (
    VALUES
        ('VT0001', 'XE0001', 'B1', 'A', 'A-01', 'MONTHLY', 'NV003', 500000.00, '2026-04-01 00:00:00+07', '2026-12-01 00:00:00+07', 'ACTIVE', 'Vé tháng ô tô khu A tầng B1'),
        ('VT0002', 'XE0002', 'B1', 'C', 'C-01', 'QUARTERLY', 'NV003', 1200000.00, '2026-04-01 00:00:00+07', '2026-12-31 00:00:00+07', 'ACTIVE', 'Vé quý xe điện kèm sạc khu C tầng B1'),
        ('VT0003', 'XE0003', 'B1', 'A', 'A-02', 'MONTHLY', 'NV006', 500000.00, '2026-04-05 00:00:00+07', '2026-11-25 00:00:00+07', 'ACTIVE', 'Vé tháng khách hàng thường xuyên'),
        ('VT0004', 'XE0004', 'B1', 'A', 'A-03', 'YEARLY', 'NV001', 4800000.00, '2026-04-01 00:00:00+07', '2027-04-01 00:00:00+07', 'ACTIVE', 'Vé năm hợp đồng dài hạn'),
        ('VT0005', 'XE0005', 'B1', 'C', 'C-02', 'MONTHLY', 'NV003', 500000.00, '2026-04-10 00:00:00+07', '2026-11-30 00:00:00+07', 'ACTIVE', 'Vé tháng xe điện VinFast VF e34'),
        ('VT0006', 'XE0006', 'B1', 'A', 'A-04', 'DAILY', 'NV006', 50000.00, '2026-04-15 00:00:00+07', '2026-10-25 00:00:00+07', 'ACTIVE', 'Vé ngắn hạn theo ngày đã gia hạn'),
        ('VT0007', 'XE0007', 'B1', 'A', 'A-05', 'MONTHLY', 'NV003', 500000.00, '2026-04-08 00:00:00+07', '2026-11-20 00:00:00+07', 'ACTIVE', NULL),
        ('VT0008', 'XE0008', 'B1', 'C', 'C-03', 'QUARTERLY', 'NV006', 1200000.00, '2026-04-02 00:00:00+07', '2026-12-15 00:00:00+07', 'ACTIVE', 'Vé quý ô tô điện khu C'),
        ('VT0009', 'XE0009', 'B1', 'B', 'B-01', 'YEARLY', 'NV001', 4800000.00, '2026-04-01 00:00:00+07', '2027-04-01 00:00:00+07', 'ACTIVE', 'Vé năm ô ưu tiên khu B'),
        ('VT0010', 'XE0010', 'B1', 'B', 'B-02', 'MONTHLY', 'NV003', 500000.00, '2026-04-12 00:00:00+07', '2026-11-18 00:00:00+07', 'ACTIVE', NULL),
        ('VT0011', 'XE0011', 'B1', 'A', 'A-06', 'DAILY', 'NV006', 50000.00, '2026-04-16 00:00:00+07', '2026-10-22 00:00:00+07', 'ACTIVE', 'Vé ngày khách đăng ký trước'),
        ('VT0012', 'XE0012', 'B1', 'C', 'C-04', 'YEARLY', 'NV001', 4800000.00, '2026-04-01 00:00:00+07', '2027-04-01 00:00:00+07', 'ACTIVE', 'Vé năm xe điện VF 9 Plus'),
        ('VT0013', 'XE0013', 'B1', 'A', 'A-07', 'MONTHLY', 'NV003', 500000.00, '2026-04-10 00:00:00+07', '2026-10-20 00:00:00+07', 'RENEWING', 'Đang chờ xác nhận gia hạn kỳ tiếp theo'),
        ('VT0014', 'XE0014', 'B1', 'B', 'B-03', 'QUARTERLY', 'NV006', 1200000.00, '2026-04-05 00:00:00+07', '2026-10-21 00:00:00+07', 'RENEWING', 'Chủ xe đăng ký gia hạn sang vé quý mới'),
        ('VT0015', 'XE0015', 'B1', 'B', 'B-04', 'MONTHLY', 'NV003', 500000.00, '2026-04-12 00:00:00+07', '2026-10-23 00:00:00+07', 'RENEWING', 'Đang xử lý thanh toán gia hạn VietQR'),
        ('VT0016', 'XE0016', 'B2', 'A', 'A-03', 'DAILY', 'NV003', 50000.00, '2026-01-10 00:00:00+07', '2026-01-11 00:00:00+07', 'EXPIRED', 'Vé ngày đã hết hạn'),
        ('VT0017', 'XE0017', 'B2', 'A', 'A-04', 'DAILY', 'NV006', 50000.00, '2026-01-18 00:00:00+07', '2026-01-19 00:00:00+07', 'EXPIRED', NULL),
        ('VT0018', 'XE0018', 'B2', 'C', 'C-02', 'MONTHLY', 'NV003', 500000.00, '2026-01-01 00:00:00+07', '2026-01-31 00:00:00+07', 'EXPIRED', 'Vé tháng kỳ tháng 01/2026'),
        ('VT0019', 'XE0019', 'B2', 'A', 'A-05', 'MONTHLY', 'NV006', 500000.00, '2026-02-01 00:00:00+07', '2026-03-03 00:00:00+07', 'EXPIRED', 'Vé tháng kỳ tháng 02/2026'),
        ('VT0020', 'XE0020', 'B2', 'A', 'A-06', 'QUARTERLY', 'NV003', 1200000.00, '2025-12-01 00:00:00+07', '2026-03-01 00:00:00+07', 'EXPIRED', 'Vé quý mùa đông đã hết hạn'),
        ('VT0021', 'XE0021', 'B2', 'A', 'A-07', 'MONTHLY', 'NV006', 500000.00, '2026-02-15 00:00:00+07', '2026-03-17 00:00:00+07', 'EXPIRED', NULL),
        ('VT0022', 'XE0022', 'B2', 'C', 'C-03', 'DAILY', 'NV003', 50000.00, '2026-03-20 00:00:00+07', '2026-03-21 00:00:00+07', 'EXPIRED', NULL),
        ('VT0023', 'XE0023', 'B2', 'A', 'A-08', 'MONTHLY', 'NV003', 500000.00, '2026-02-10 00:00:00+07', '2026-03-12 00:00:00+07', 'CANCELLED', 'Hủy theo yêu cầu khách hàng trước kỳ'),
        ('VT0024', 'XE0024', 'B2', 'A', 'A-09', 'QUARTERLY', 'NV006', 1200000.00, '2026-01-15 00:00:00+07', '2026-04-15 00:00:00+07', 'CANCELLED', 'Hủy và hoàn tiền do đổi phương tiện'),
        ('VT0025', 'XE0025', 'B2', 'C', 'C-04', 'DAILY', 'NV003', 50000.00, '2026-03-05 00:00:00+07', '2026-03-06 00:00:00+07', 'CANCELLED', 'Hủy do nhập nhầm ngày hiệu lực')
) AS t(code, veh_code, floor_code, zone_code, slot_code, tt_code, emp_code, price, effective_from, effective_to, status, notes)
JOIN vehicle veh ON veh.code = t.veh_code AND veh.deleted_at IS NULL
JOIN ticket_type tt ON tt.code = t.tt_code AND tt.deleted_at IS NULL
JOIN employee emp ON emp.code = t.emp_code AND emp.deleted_at IS NULL
JOIN parking_floor pf ON pf.code = t.floor_code AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.code = t.zone_code AND pz.deleted_at IS NULL
JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.code = t.slot_code AND ps.deleted_at IS NULL
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.11. TICKET RENEWALS (5 RENEWALS — TL-10, OQ-58)
-- ----------------------------------------------------------------------------
INSERT INTO ticket_renewal (
    ticket_id, old_slot_id, new_slot_id, old_ticket_type_id, new_ticket_type_id,
    old_price, new_price, old_effective_to, new_effective_to, additional_price,
    notes, renewed_by, created_at
)
SELECT
    tk.id,
    old_ps.id,
    new_ps.id,
    old_tt.id,
    new_tt.id,
    r.old_price::NUMERIC(12, 2),
    r.new_price::NUMERIC(12, 2),
    r.old_eff_to::TIMESTAMPTZ,
    r.new_eff_to::TIMESTAMPTZ,
    r.add_price::NUMERIC(12, 2),
    r.notes,
    emp.id,
    r.created_at::TIMESTAMPTZ
FROM (
    VALUES
        ('VT0001', 'B1', 'A', 'A-01', 'B1', 'A', 'A-01', 'MONTHLY', 'MONTHLY', 500000.00, 500000.00, '2026-11-01 00:00:00+07', '2026-12-01 00:00:00+07', 500000.00, 'Gia hạn thêm 30 ngày giữ nguyên vị trí A-01', 'NV003', '2026-10-01 09:15:00+07'),
        ('VT0002', 'B1', 'C', 'C-01', 'B1', 'C', 'C-01', 'MONTHLY', 'QUARTERLY', 500000.00, 1200000.00, '2026-09-30 00:00:00+07', '2026-12-31 00:00:00+07', 1200000.00, 'Nâng cấp từ vé tháng lên vé quý khu sạc xe điện', 'NV006', '2026-09-28 14:20:00+07'),
        ('VT0003', 'B1', 'A', 'A-02', 'B1', 'A', 'A-02', 'MONTHLY', 'MONTHLY', 500000.00, 500000.00, '2026-10-25 00:00:00+07', '2026-11-25 00:00:00+07', 500000.00, 'Gia hạn định kỳ tháng 11/2026', 'NV003', '2026-10-10 10:05:00+07'),
        ('VT0005', 'B1', 'C', 'C-02', 'B1', 'C', 'C-02', 'MONTHLY', 'MONTHLY', 500000.00, 500000.00, '2026-10-30 00:00:00+07', '2026-11-30 00:00:00+07', 500000.00, 'Gia hạn vé tháng xe điện VF e34', 'NV006', '2026-10-12 16:40:00+07'),
        ('VT0008', 'B1', 'C', 'C-03', 'B1', 'C', 'C-03', 'QUARTERLY', 'QUARTERLY', 1200000.00, 1200000.00, '2026-09-15 00:00:00+07', '2026-12-15 00:00:00+07', 1200000.00, 'Gia hạn vé quý kỳ Q4/2026', 'NV003', '2026-09-14 11:10:00+07')
) AS r(ticket_code, old_fl, old_z, old_sl, new_fl, new_z, new_sl, old_tt_code, new_tt_code, old_price, new_price, old_eff_to, new_eff_to, add_price, notes, emp_code, created_at)
JOIN ticket tk ON tk.code = r.ticket_code AND tk.deleted_at IS NULL
JOIN parking_floor opf ON opf.code = r.old_fl AND opf.deleted_at IS NULL
JOIN parking_zone opz ON opz.floor_id = opf.id AND opz.code = r.old_z AND opz.deleted_at IS NULL
JOIN parking_slot old_ps ON old_ps.zone_id = opz.id AND old_ps.code = r.old_sl AND old_ps.deleted_at IS NULL
JOIN parking_floor npf ON npf.code = r.new_fl AND npf.deleted_at IS NULL
JOIN parking_zone npz ON npz.floor_id = npf.id AND npz.code = r.new_z AND npz.deleted_at IS NULL
JOIN parking_slot new_ps ON new_ps.zone_id = npz.id AND new_ps.code = r.new_sl AND new_ps.deleted_at IS NULL
JOIN ticket_type old_tt ON old_tt.code = r.old_tt_code AND old_tt.deleted_at IS NULL
JOIN ticket_type new_tt ON new_tt.code = r.new_tt_code AND new_tt.deleted_at IS NULL
JOIN employee emp ON emp.code = r.emp_code AND emp.deleted_at IS NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM ticket_renewal tr
    WHERE tr.ticket_id = tk.id
      AND tr.new_effective_to = r.new_eff_to::TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- 2.12. SLOT RESERVATIONS (6 RESERVATIONS: RSV-2026-0001..0006 — TL-04)
-- ----------------------------------------------------------------------------
INSERT INTO slot_reservation (
    code, slot_id, customer_id, vehicle_id, reserved_name,
    reserved_phone, reserved_from, reserved_until, status, notes, created_by
)
SELECT
    rv.code,
    ps.id,
    cust.id,
    veh.id,
    rv.reserved_name,
    COALESCE(rv.reserved_phone, cust.phone),
    rv.reserved_from::TIMESTAMPTZ,
    rv.reserved_until::TIMESTAMPTZ,
    rv.status,
    rv.notes,
    emp.id
FROM (
    VALUES
        ('RSV-2026-0001', 'B1', 'A', 'A-09', 'KH0006', 'XE0016', 'Tạ Thị Minh Châu', NULL, '2026-04-15 06:00:00+07', '2026-10-25 22:00:00+07', 'ACTIVE', 'Đặt trước ô đỗ tiêu chuẩn khu A tầng B1', 'NV002'),
        ('RSV-2026-0002', 'B1', 'A', 'A-10', 'KH0007', 'XE0017', 'Cao Tiến Dũng', NULL, '2026-04-15 06:00:00+07', '2026-10-25 22:00:00+07', 'ACTIVE', 'Đặt trước ô đỗ xe gia đình', 'NV005'),
        ('RSV-2026-0003', 'B1', 'B', 'B-05', NULL, NULL, 'Phạm Đức Thành', '0373370580', '2026-04-15 06:00:00+07', '2026-10-25 22:00:00+07', 'ACTIVE', 'Khách vãng lai gọi điện đặt chỗ ưu tiên', 'NV002'),
        ('RSV-2026-0004', 'B2', 'A', 'A-11', 'KH0009', 'XE0019', 'Hà Mạnh Cường', NULL, '2026-03-10 08:00:00+07', '2026-03-10 18:00:00+07', 'COMPLETED', 'Đã hoàn tất nhận chỗ đúng giờ', 'NV002'),
        ('RSV-2026-0005', 'B2', 'A', 'A-12', 'KH0010', 'XE0020', 'Mai Thị Phương Thảo', NULL, '2026-03-14 09:00:00+07', '2026-03-14 15:00:00+07', 'CANCELLED', 'Khách báo hủy lịch hẹn trước 2 giờ', 'NV005'),
        ('RSV-2026-0006', 'B2', 'A', 'A-13', NULL, NULL, 'Lê Quang Khải', '0707202810', '2026-03-18 07:30:00+07', '2026-03-18 12:30:00+07', 'EXPIRED', 'Quá thời gian giữ chỗ không thấy phương tiện vào bãi', 'NV008')
) AS rv(code, floor_code, zone_code, slot_code, cust_code, veh_code, reserved_name, reserved_phone, reserved_from, reserved_until, status, notes, emp_code)
JOIN parking_floor pf ON pf.code = rv.floor_code AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.code = rv.zone_code AND pz.deleted_at IS NULL
JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.code = rv.slot_code AND ps.deleted_at IS NULL
LEFT JOIN customer cust ON rv.cust_code IS NOT NULL AND cust.code = rv.cust_code AND cust.deleted_at IS NULL
LEFT JOIN vehicle veh ON rv.veh_code IS NOT NULL AND veh.code = rv.veh_code AND veh.deleted_at IS NULL
LEFT JOIN employee emp ON emp.code = rv.emp_code AND emp.deleted_at IS NULL
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.13. PLATE BLACKLIST (2 BLACKLISTED LICENSE PLATES — TL-08)
-- ----------------------------------------------------------------------------
INSERT INTO plate_blacklist (license_plate, reason, unpaid_amount, is_active, added_by)
SELECT
    b.license_plate,
    b.reason,
    b.unpaid_amount::NUMERIC(12, 2),
    b.is_active,
    emp.id
FROM (
    VALUES
        ('43V-856.12', 'Nợ cước phí đỗ xe quá hạn nhiều kỳ chưa thanh toán', 450000.00, TRUE, 'NV001'),
        ('92P-280.96', 'Làm hư hỏng thanh chắn barrier cổng ra số 2 và rời bãi chưa bồi thường', 1200000.00, TRUE, 'NV001')
) AS b(license_plate, reason, unpaid_amount, is_active, emp_code)
JOIN employee emp ON emp.code = b.emp_code AND emp.deleted_at IS NULL
ON CONFLICT (license_plate_norm) WHERE deleted_at IS NULL AND is_active = TRUE DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.14. VEHICLE ENTRY/EXIT LOG SESSIONS (50 SESSIONS: 36 CLOSED + 14 OPEN — TL-05, TL-17)
-- ----------------------------------------------------------------------------
INSERT INTO vehicle_entry_exit_log (
    session_code, vehicle_id, slot_id, ticket_id, entry_gate_id, exit_gate_id,
    license_plate, ai_confidence, recognition_source, review_status, fee_amount,
    entry_time, exit_time, entry_image_url, exit_image_url,
    entry_handled_by, exit_handled_by, notes, created_at
)
SELECT
    l.session_code,
    veh.id,
    ps.id,
    tk.id,
    in_g.id,
    out_g.id,
    l.license_plate,
    l.ai_conf::NUMERIC(5, 2),
    l.rec_src,
    l.rev_status,
    l.fee::NUMERIC(12, 2),
    l.entry_time::TIMESTAMPTZ,
    l.exit_time::TIMESTAMPTZ,
    NULL,
    NULL,
    in_emp.id,
    out_emp.id,
    l.notes,
    l.entry_time::TIMESTAMPTZ
FROM (
    VALUES
        ('#PK-20261017-001', 'XE0001', 'B1', 'A', 'A-01', 'VT0001', 'IN_01', 'OUT_01', '43K-860.50', 96.20, 'AI', 'MATCHED', 0.00, '2026-10-15 07:15:00+07', '2026-10-15 11:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-002', 'XE0002', 'B1', 'C', 'C-01', 'VT0002', 'IN_02', 'OUT_02', '92F-187.13', 97.00, 'AI', 'MATCHED', 0.00, '2026-10-15 08:15:00+07', '2026-10-15 12:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-003', 'XE0003', 'B1', 'A', 'A-02', 'VT0003', 'IN_01', 'OUT_01', '43X-433.53', 97.80, 'AI', 'MATCHED', 0.00, '2026-10-15 09:15:00+07', '2026-10-15 13:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-004', 'XE0004', 'B1', 'A', 'A-03', 'VT0004', 'IN_02', 'OUT_02', '43B-40962', 98.60, 'AI', 'MATCHED', 0.00, '2026-10-15 10:15:00+07', '2026-10-15 14:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-005', 'XE0005', 'B1', 'C', 'C-02', 'VT0005', 'IN_01', 'OUT_01', '92E-750.51', 96.20, 'AI', 'MATCHED', 0.00, '2026-10-15 11:15:00+07', '2026-10-15 15:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-006', 'XE0006', 'B1', 'A', 'A-04', 'VT0006', 'IN_02', 'OUT_02', '77K-893.90', 97.00, 'AI', 'MATCHED', 0.00, '2026-10-15 12:15:00+07', '2026-10-15 16:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-007', 'XE0007', 'B1', 'A', 'A-05', 'VT0007', 'IN_01', 'OUT_01', '43T-814.62', 97.80, 'AI', 'MATCHED', 0.00, '2026-10-16 07:15:00+07', '2026-10-16 11:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-008', 'XE0008', 'B1', 'C', 'C-03', 'VT0008', 'IN_02', 'OUT_02', '92V-27566', 98.60, 'AI', 'MATCHED', 0.00, '2026-10-16 08:15:00+07', '2026-10-16 12:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-009', 'XE0009', 'B1', 'B', 'B-01', 'VT0009', 'IN_01', 'OUT_01', '75E-689.74', 96.20, 'AI', 'MATCHED', 0.00, '2026-10-16 09:15:00+07', '2026-10-16 13:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-010', 'XE0010', 'B1', 'B', 'B-02', 'VT0010', 'IN_02', 'OUT_02', '43P-613.59', 97.00, 'AI', 'MATCHED', 0.00, '2026-10-16 10:15:00+07', '2026-10-16 14:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-011', 'XE0011', 'B1', 'A', 'A-06', 'VT0011', 'IN_01', 'OUT_01', '92V-929.32', 97.80, 'AI', 'MATCHED', 0.00, '2026-10-16 11:15:00+07', '2026-10-16 15:40:00+07', 'NV002', 'NV005', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-012', 'XE0012', 'B1', 'C', 'C-04', 'VT0012', 'IN_02', 'OUT_02', '75V-56297', 98.60, 'AI', 'MATCHED', 0.00, '2026-10-16 12:15:00+07', '2026-10-16 16:40:00+07', 'NV005', 'NV008', 'Phiên đỗ xe theo vé định kỳ còn hiệu lực'),
        ('#PK-20261017-013', 'XE0016', 'B2', 'A', 'A-14', NULL, 'IN_01', 'OUT_03', '43M-14723', 91.50, 'AI', 'AUTO', 20000.00, '2026-10-16 06:10:00+07', '2026-10-16 08:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-014', 'XE0017', 'B2', 'A', 'A-15', NULL, 'IN_02', 'OUT_02', '92V-661.69', 92.70, 'AI', 'MATCHED', 25000.00, '2026-10-16 07:10:00+07', '2026-10-16 09:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-015', 'XE0018', 'B2', 'A', 'A-16', NULL, 'IN_01', 'OUT_02', '76C-752.60', 93.90, 'AI', 'AUTO', 30000.00, '2026-10-16 08:10:00+07', '2026-10-16 10:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-016', 'XE0019', 'B2', 'A', 'A-17', NULL, 'IN_02', 'OUT_03', '43K-367.67', 95.10, 'AI', 'MATCHED', 35000.00, '2026-10-16 09:10:00+07', '2026-10-16 11:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-017', 'XE0020', 'B2', 'A', 'A-18', NULL, 'IN_01', 'OUT_02', '92G-11274', 96.30, 'AI', 'AUTO', 40000.00, '2026-10-16 10:10:00+07', '2026-10-16 12:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-018', 'XE0021', 'B2', 'A', 'A-19', NULL, 'IN_02', 'OUT_02', '76K-438.79', 97.50, 'AI', 'MATCHED', 50000.00, '2026-10-16 06:10:00+07', '2026-10-16 08:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-019', 'XE0022', 'B2', 'B', 'B-02', NULL, 'IN_01', 'OUT_03', '43P-163.22', 91.50, 'AI', 'AUTO', 20000.00, '2026-10-17 07:10:00+07', '2026-10-17 09:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-020', 'XE0023', 'B2', 'B', 'B-03', NULL, 'IN_02', 'OUT_02', '92N-954.16', 92.70, 'AI', 'MATCHED', 30000.00, '2026-10-17 08:10:00+07', '2026-10-17 10:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-021', 'XE0024', 'B2', 'B', 'B-04', NULL, 'IN_01', 'OUT_02', '79Y-65161', 93.90, 'AI', 'AUTO', 25000.00, '2026-10-17 09:10:00+07', '2026-10-17 11:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-022', 'XE0025', 'B2', 'B', 'B-05', NULL, 'IN_02', 'OUT_03', '43C-276.58', 95.10, 'AI', 'MATCHED', 45000.00, '2026-10-17 10:10:00+07', '2026-10-17 12:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-023', 'XE0026', 'B2', 'B', 'B-06', NULL, 'IN_01', 'OUT_02', '92Y-146.47', 96.30, 'AI', 'AUTO', 35000.00, '2026-10-17 06:10:00+07', '2026-10-17 08:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-024', 'XE0027', 'B2', 'B', 'B-07', NULL, 'IN_02', 'OUT_02', '92P-175.17', NULL, 'MANUAL', 'APPROVED', 60000.00, '2026-10-17 07:10:00+07', '2026-10-17 09:25:00+07', 'NV002', 'NV005', 'Khách hàng đăng ký gửi xe theo lượt'),
        ('#PK-20261017-025', NULL, 'F1', 'A', 'A-03', NULL, 'IN_02', 'OUT_01', '77E-47035', 89.40, 'AI', 'MATCHED', 15000.00, '2026-10-17 07:05:00+07', '2026-10-17 08:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-026', NULL, 'F1', 'A', 'A-04', NULL, 'IN_01', 'OUT_02', '43D-726.16', 90.70, 'AI', 'AUTO', 20000.00, '2026-10-17 08:05:00+07', '2026-10-17 09:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-027', NULL, 'F1', 'A', 'A-05', NULL, 'IN_02', 'OUT_01', '77K-921.74', 92.00, 'AI', 'AUTO', 25000.00, '2026-10-17 09:05:00+07', '2026-10-17 10:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-028', NULL, 'F1', 'A', 'A-06', NULL, 'IN_01', 'OUT_02', '77B-55013', 93.30, 'AI', 'MATCHED', 30000.00, '2026-10-17 10:05:00+07', '2026-10-17 11:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-029', NULL, 'F1', 'A', 'A-07', NULL, 'IN_02', 'OUT_01', '92B-705.93', 94.60, 'AI', 'AUTO', 35000.00, '2026-10-17 07:05:00+07', '2026-10-17 08:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-030', NULL, 'F1', 'A', 'A-08', NULL, 'IN_01', 'OUT_02', '30M-286.55', NULL, 'MANUAL', 'APPROVED', 40000.00, '2026-10-17 08:05:00+07', '2026-10-17 09:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-031', NULL, 'F1', 'B', 'B-02', NULL, 'IN_02', 'OUT_01', '92Z-97612', 97.20, 'AI', 'MATCHED', 20000.00, '2026-10-17 09:05:00+07', '2026-10-17 10:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-032', NULL, 'F1', 'B', 'B-03', NULL, 'IN_01', 'OUT_02', '51K-533.43', 89.40, 'AI', 'AUTO', 25000.00, '2026-10-17 10:05:00+07', '2026-10-17 11:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-033', NULL, 'F1', 'B', 'B-04', NULL, 'IN_02', 'OUT_01', '75B-441.56', 90.70, 'AI', 'AUTO', 30000.00, '2026-10-17 07:05:00+07', '2026-10-17 08:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-034', NULL, 'F1', 'B', 'B-05', NULL, 'IN_01', 'OUT_02', '30V-63728', 92.00, 'AI', 'MATCHED', 45000.00, '2026-10-17 08:05:00+07', '2026-10-17 09:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-035', NULL, 'F1', 'B', 'B-06', NULL, 'IN_02', 'OUT_01', '79C-756.44', NULL, 'MANUAL', 'APPROVED', 50000.00, '2026-10-17 09:05:00+07', '2026-10-17 10:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-036', NULL, 'F1', 'B', 'B-07', NULL, 'IN_01', 'OUT_02', '51C-882.54', 94.60, 'AI', 'AUTO', 30000.00, '2026-10-17 10:05:00+07', '2026-10-17 11:35:00+07', 'NV005', 'NV008', 'Khách vãng lai gửi xe theo giờ'),
        ('#PK-20261017-037', 'XE0001', 'B1', 'A', 'A-01', 'VT0001', 'IN_01', NULL, '43K-860.50', 97.10, 'AI', 'MATCHED', 0.00, '2026-10-17 07:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-038', 'XE0002', 'B1', 'C', 'C-01', 'VT0002', 'IN_02', NULL, '92F-187.13', 97.50, 'AI', 'MATCHED', 0.00, '2026-10-17 08:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-039', 'XE0003', 'B1', 'A', 'A-02', 'VT0003', 'IN_01', NULL, '43X-433.53', 97.90, 'AI', 'MATCHED', 0.00, '2026-10-17 09:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-040', 'XE0004', 'B1', 'A', 'A-03', 'VT0004', 'IN_02', NULL, '43B-40962', 98.30, 'AI', 'MATCHED', 0.00, '2026-10-17 10:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-041', 'XE0005', 'B1', 'C', 'C-02', 'VT0005', 'IN_01', NULL, '92E-750.51', 98.70, 'AI', 'MATCHED', 0.00, '2026-10-17 11:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-042', 'XE0006', 'B1', 'A', 'A-04', 'VT0006', 'IN_02', NULL, '77K-893.90', 99.10, 'AI', 'MATCHED', 0.00, '2026-10-17 12:20:00+07', NULL, 'NV002', NULL, 'Xe vé tháng/quý/năm đang đỗ trong bãi'),
        ('#PK-20261017-043', 'XE0018', 'B2', 'C', 'C-01', NULL, 'IN_01', NULL, '76C-752.60', 94.00, 'AI', 'AUTO', 25000.00, '2026-10-17 08:12:00+07', NULL, 'NV005', NULL, 'Xe khách hàng đã đăng ký đang gửi theo lượt'),
        ('#PK-20261017-044', 'XE0019', 'B2', 'A', 'A-01', NULL, 'IN_01', NULL, '43K-367.67', 95.10, 'AI', 'AUTO', 30000.00, '2026-10-17 09:12:00+07', NULL, 'NV005', NULL, 'Xe khách hàng đã đăng ký đang gửi theo lượt'),
        ('#PK-20261017-045', 'XE0020', 'B2', 'A', 'A-02', NULL, 'IN_01', NULL, '92G-11274', 96.20, 'AI', 'AUTO', 20000.00, '2026-10-17 10:12:00+07', NULL, 'NV005', NULL, 'Xe khách hàng đã đăng ký đang gửi theo lượt'),
        ('#PK-20261017-046', 'XE0021', 'B2', 'B', 'B-01', NULL, 'IN_01', NULL, '76K-438.79', 97.30, 'AI', 'AUTO', 35000.00, '2026-10-17 11:12:00+07', NULL, 'NV005', NULL, 'Xe khách hàng đã đăng ký đang gửi theo lượt'),
        ('#PK-20261017-047', NULL, 'F1', 'A', 'A-01', NULL, 'IN_02', NULL, '51H-109.81', 95.20, 'AI', 'AUTO', 15000.00, '2026-10-17 09:28:00+07', NULL, 'NV008', NULL, 'Khách vãng lai đang đỗ tại tầng F1'),
        ('#PK-20261017-048', NULL, 'F1', 'A', 'A-02', NULL, 'IN_02', NULL, '92K-910.76', 84.50, 'AI', 'NEEDS_REVIEW', 20000.00, '2026-10-17 10:28:00+07', NULL, 'NV008', NULL, 'Khách vãng lai đang đỗ tại tầng F1'),
        ('#PK-20261017-049', NULL, 'F1', 'B', 'B-01', NULL, 'IN_02', NULL, '79U-163.47', 96.60, 'AI', 'AUTO', 25000.00, '2026-10-17 11:28:00+07', NULL, 'NV008', NULL, 'Khách vãng lai đang đỗ tại tầng F1'),
        ('#PK-20261017-050', NULL, 'F1', 'C', 'C-01', NULL, 'IN_02', NULL, '30C-468.58', 97.30, 'AI', 'MATCHED', 30000.00, '2026-10-17 12:28:00+07', NULL, 'NV008', NULL, 'Khách vãng lai đang đỗ tại tầng F1')
) AS l(session_code, veh_code, floor_code, zone_code, slot_code, ticket_code, in_gate_code, out_gate_code, license_plate, ai_conf, rec_src, rev_status, fee, entry_time, exit_time, in_staff_code, out_staff_code, notes)
JOIN parking_floor pf ON pf.code = l.floor_code AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
JOIN parking_zone pz ON pz.floor_id = pf.id AND pz.code = l.zone_code AND pz.deleted_at IS NULL
JOIN parking_slot ps ON ps.zone_id = pz.id AND ps.code = l.slot_code AND ps.deleted_at IS NULL
LEFT JOIN vehicle veh ON l.veh_code IS NOT NULL AND veh.code = l.veh_code AND veh.deleted_at IS NULL
LEFT JOIN ticket tk ON l.ticket_code IS NOT NULL AND tk.code = l.ticket_code AND tk.deleted_at IS NULL
LEFT JOIN parking_gate in_g ON in_g.lot_id = pl.id AND in_g.code = l.in_gate_code AND in_g.deleted_at IS NULL
LEFT JOIN parking_gate out_g ON l.out_gate_code IS NOT NULL AND out_g.lot_id = pl.id AND out_g.code = l.out_gate_code AND out_g.deleted_at IS NULL
LEFT JOIN employee in_emp ON l.in_staff_code IS NOT NULL AND in_emp.code = l.in_staff_code AND in_emp.deleted_at IS NULL
LEFT JOIN employee out_emp ON l.out_staff_code IS NOT NULL AND out_emp.code = l.out_staff_code AND out_emp.deleted_at IS NULL
ON CONFLICT (session_code) DO NOTHING;

-- Mark 2 EV_CHARGING slots with active EV open sessions (B1/C/C-01 and B1/C/C-02) as CHARGING (TL-03, TL-20)
UPDATE parking_slot ps
SET status = 'CHARGING'
FROM parking_zone pz
JOIN parking_floor pf ON pf.id = pz.floor_id AND pf.deleted_at IS NULL
JOIN parking_lot pl ON pl.id = pf.lot_id AND pl.code = 'SMART_MOBILITY' AND pl.deleted_at IS NULL
WHERE ps.zone_id = pz.id
  AND pz.deleted_at IS NULL
  AND ps.deleted_at IS NULL
  AND pf.code = 'B1'
  AND pz.code = 'C'
  AND ps.code IN ('C-01', 'C-02')
  AND ps.status <> 'CHARGING';

-- ----------------------------------------------------------------------------
-- 2.15. PAYMENTS (53 PAYMENTS MATCHING CLOSED SESSIONS, TICKETS & RENEWALS — TL-07)
-- ----------------------------------------------------------------------------
-- (a) 24 payments for the 24 fee-bearing closed sessions (#PK-20261017-013..036)
INSERT INTO payment (
    code, amount, method, status, paid_at, received_by,
    provider_ref, session_id, notes, created_at
)
SELECT
    'PAY-SES-' || right(l.session_code, 3),
    l.fee_amount,
    CASE WHEN CAST(right(l.session_code, 3) AS INTEGER) % 3 = 0 THEN 'CASH' ELSE 'VIETQR' END,
    'PAID',
    l.exit_time,
    l.exit_handled_by,
    CASE WHEN CAST(right(l.session_code, 3) AS INTEGER) % 3 = 0 THEN NULL ELSE 'VQR-SES-20261017-' || right(l.session_code, 3) END,
    l.id,
    'Thanh toán cước phí phiên đỗ xe ' || l.session_code,
    l.exit_time
FROM vehicle_entry_exit_log l
WHERE l.exit_time IS NOT NULL
  AND l.fee_amount > 0
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- (b) 24 payments for tickets VT0001..VT0024 (21 PAID, 1 UNPAID for VT0015, 1 CANCELLED for VT0023, 1 REFUNDED for VT0024)
INSERT INTO payment (
    code, amount, method, status, paid_at, received_by,
    provider_ref, ticket_id, notes, created_at
)
SELECT
    'PAY-TKT-' || right(t.code, 4),
    t.price,
    CASE WHEN CAST(right(t.code, 4) AS INTEGER) % 4 = 0 THEN 'CASH' ELSE 'VIETQR' END,
    CASE
        WHEN t.code = 'VT0015' THEN 'UNPAID'
        WHEN t.code = 'VT0023' THEN 'CANCELLED'
        WHEN t.code = 'VT0024' THEN 'REFUNDED'
        ELSE 'PAID'
    END,
    CASE
        WHEN t.code IN ('VT0015', 'VT0023') THEN NULL
        ELSE t.effective_from
    END,
    t.issued_by,
    CASE
        WHEN CAST(right(t.code, 4) AS INTEGER) % 4 = 0 OR t.code IN ('VT0015', 'VT0023') THEN NULL
        ELSE 'VQR-TKT-2026-' || right(t.code, 4)
    END,
    t.id,
    'Thanh toán đăng ký vé ' || t.code,
    t.effective_from
FROM ticket t
WHERE t.deleted_at IS NULL
  AND t.code <> 'VT0025'
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- (c) 5 payments for the 5 ticket renewals
INSERT INTO payment (
    code, amount, method, status, paid_at, received_by,
    provider_ref, renewal_id, notes, created_at
)
SELECT
    'PAY-REN-' || right(t.code, 4),
    tr.additional_price,
    CASE WHEN CAST(right(t.code, 4) AS INTEGER) % 2 = 0 THEN 'VIETQR' ELSE 'CASH' END,
    'PAID',
    tr.created_at,
    tr.renewed_by,
    CASE WHEN CAST(right(t.code, 4) AS INTEGER) % 2 = 0 THEN 'VQR-REN-2026-' || right(t.code, 4) ELSE NULL END,
    tr.id,
    'Thanh toán gia hạn vé ' || t.code,
    tr.created_at
FROM ticket_renewal tr
JOIN ticket t ON t.id = tr.ticket_id
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.16. NEWS ARTICLES (3 PUBLISHED ARTICLES — SCO-03, OQ-51)
-- ----------------------------------------------------------------------------
INSERT INTO news (
    title, slug, summary, content, thumbnail_url,
    author_id, is_published, published_at, view_count
)
SELECT
    n.title,
    n.slug,
    n.summary,
    n.content,
    n.thumbnail_url,
    emp.id,
    TRUE,
    n.published_at::TIMESTAMPTZ,
    n.view_count
FROM (
    VALUES
        (
            'Vận hành hệ thống nhận diện biển số ô tô tự động bằng AI tại Bãi xe Smart Mobility',
            'van-hanh-he-thong-nhan-dien-bien-so-o-to-tu-dong-bang-ai',
            'Hệ thống camera AI tại 4 cổng quét tự động giúp rút ngắn thời gian xe ô tô qua trạm xuống dưới 3 giây.',
            'Bãi xe Smart Mobility chính thức đưa vào vận hành hệ thống nhận diện biển số tự động (ALPR) tại Cổng vào 1, Cổng vào 2, Cổng ra 1 và Cổng ra 2, kết hợp đối soát hình ảnh thời gian thực.',
            '/media/news/alpr-smart-mobility.jpg',
            'NV001',
            '2026-10-01 08:00:00+07',
            148
        ),
        (
            'Hướng dẫn thanh toán cước phí đỗ xe và gia hạn vé định kỳ qua mã VietQR',
            'huong-dan-thanh-toan-cuoc-phi-do-xe-va-gia-han-ve-qua-vietqr',
            'Khách hàng có thể thanh toán nhanh bằng mã VietQR tại cổng ra hoặc khi đăng ký, gia hạn vé tháng, vé quý, vé năm.',
            'Nhằm nâng cao trải nghiệm không dùng tiền mặt, Bãi xe Smart Mobility hỗ trợ thanh toán VietQR tự động đối soát cho cả phiên đỗ xe theo lượt và các gói vé định kỳ.',
            '/media/news/vietqr-payment-guide.jpg',
            'NV003',
            '2026-10-08 09:30:00+07',
            96
        ),
        (
            'Thông báo lịch bảo trì định kỳ trụ sạc ô tô điện tại Khu C Tầng B2',
            'thong-bao-lich-bao-tri-dinh-ky-tru-sac-o-to-dien-khu-c-tang-b2',
            'Trụ sạc tại vị trí C-08 Tầng B2 tạm ngừng phục vụ để kiểm định kỹ thuật định kỳ.',
            'Đội ngũ kỹ thuật viên tiến hành kiểm tra an toàn điện và bảo dưỡng trụ sạc AC 22kW tại ô C-08 Khu C Tầng B2. Các ô sạc xe điện tại Tầng B1 và Tầng F1 vẫn hoạt động bình thường.',
            '/media/news/ev-charger-maintenance.jpg',
            'NV007',
            '2026-10-15 14:00:00+07',
            64
        )
) AS n(title, slug, summary, content, thumbnail_url, emp_code, published_at, view_count)
JOIN employee emp ON emp.code = n.emp_code AND emp.deleted_at IS NULL
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2.17. NOTIFICATIONS (6 NOTIFICATIONS ACROSS ALL 4 TYPES — SRS 4.2, OQ-51)
-- ----------------------------------------------------------------------------
INSERT INTO notification (
    recipient_account_id, title, content, notification_type,
    is_read, read_at, created_at
)
SELECT
    acc.id,
    nt.title,
    nt.content,
    nt.notification_type,
    nt.is_read,
    nt.read_at::TIMESTAMPTZ,
    nt.created_at::TIMESTAMPTZ
FROM (
    VALUES
        (NULL, 'Cập nhật sơ đồ bãi đỗ xe 3 tầng B1, B2, F1', 'Hệ thống đã đồng bộ 150 vị trí đỗ xe ô tô và ô tô điện trên toàn bộ 3 tầng.', 'SYSTEM', FALSE, NULL, '2026-10-15 08:00:00+07'),
        ('hoang.dinh.khang@example.com', 'Báo cáo đối soát doanh thu ca sáng', 'Doanh thu tiền mặt và VietQR ca sáng đã được tổng hợp đầy đủ trên bảng điều khiển.', 'PAYMENT', TRUE, '2026-10-17 07:10:00+07', '2026-10-17 07:00:00+07'),
        ('luong.mai.phuong@example.org', 'Cảnh báo chất lượng camera Cổng ra 1', 'Camera tại Cổng ra 1 đang ở trạng thái ánh sáng yếu (LOW_LIGHT), cần kiểm tra đèn chiếu biển số.', 'SECURITY', FALSE, NULL, '2026-10-17 06:45:00+07'),
        ('lam.hoang.viet@example.net', 'Nhắc lịch gia hạn vé tháng VT0013', 'Vé tháng VT0013 của phương tiện Hyundai Tucson 2.0 sắp đến hạn, vui lòng xác nhận gia hạn.', 'TICKET_EXPIRY', FALSE, NULL, '2026-10-16 09:00:00+07'),
        ('doan.tuyet.mai@example.com', 'Xác nhận yêu cầu gia hạn vé quý VT0014', 'Yêu cầu gia hạn vé VT0014 tại ô B-03 Tầng B1 đã được ghi nhận.', 'TICKET_EXPIRY', TRUE, '2026-10-16 15:20:00+07', '2026-10-16 14:30:00+07'),
        ('trinh.xuan.truong@example.com', 'Biên lai thanh toán gia hạn vé VT0001', 'Giao dịch thanh toán gia hạn vé tháng VT0001 số tiền 500.000đ đã hoàn tất.', 'PAYMENT', TRUE, '2026-10-01 09:20:00+07', '2026-10-01 09:16:00+07')
) AS nt(acc_email, title, content, notification_type, is_read, read_at, created_at)
LEFT JOIN account acc ON nt.acc_email IS NOT NULL AND lower(acc.email) = lower(nt.acc_email) AND acc.deleted_at IS NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM notification existing
    WHERE existing.title = nt.title
      AND existing.created_at = nt.created_at::TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- 2.18. ACTIVITY LOG (10 APPEND-ONLY OPERATIONAL EVENTS — TL-12)
-- ----------------------------------------------------------------------------
INSERT INTO activity_log (actor_account_id, action, entity_type, entity_id, message, occurred_at)
SELECT
    acc.id,
    a.action,
    a.entity_type,
    a.entity_id,
    a.message,
    a.occurred_at::TIMESTAMPTZ
FROM (
    VALUES
        ('hoang.dinh.khang@example.com', 'LOT_INIT',         'PARKING_LOT',       1,  'Khởi tạo sơ đồ bãi xe Smart Mobility gồm 3 tầng B1, B2, F1 và 150 ô đỗ.', '2026-10-01 07:30:00+07'),
        ('ngo.gia.bao@example.com',      'SLOT_MAINTENANCE', 'PARKING_SLOT',      8,  'Đánh dấu bảo trì cảm biến siêu âm tại ô A-08 Khu A Tầng B1.',              '2026-10-15 10:00:00+07'),
        ('ngo.gia.bao@example.com',      'SLOT_MAINTENANCE', 'PARKING_SLOT',      93, 'Đánh dấu bảo trì trụ sạc điện AC 22kW tại ô C-08 Khu C Tầng B2.',          '2026-10-15 14:15:00+07'),
        ('do.minh.quan@example.net',     'TICKET_ISSUE',     'TICKET',            1,  'Phát hành vé tháng VT0001 cho xe tại ô A-01 Khu A Tầng B1.',               '2026-10-01 08:30:00+07'),
        ('do.minh.quan@example.net',     'TICKET_RENEW',     'TICKET_RENEWAL',    1,  'Gia hạn vé tháng VT0001 thêm 30 ngày tại ô A-01 Khu A Tầng B1.',           '2026-10-01 09:15:00+07'),
        ('luong.mai.phuong@example.org', 'SLOT_RESERVE',     'SLOT_RESERVATION',  1,  'Đặt trước ô A-09 Khu A Tầng B1 (mã đặt chỗ RSV-2026-0001).',               '2026-10-16 08:00:00+07'),
        ('vu.quoc.hung@example.org',     'SLOT_RESERVE',     'SLOT_RESERVATION',  2,  'Đặt trước ô A-10 Khu A Tầng B1 (mã đặt chỗ RSV-2026-0002).',               '2026-10-16 08:20:00+07'),
        ('hoang.dinh.khang@example.com', 'BLACKLIST_ADD',    'PLATE_BLACKLIST',   1,  'Thêm biển số nợ phí quá hạn vào danh sách cảnh báo Blacklist.',            '2026-10-16 11:00:00+07'),
        (NULL,                           'SLOT_CHECKIN',     'VEHICLE_SESSION',   37, 'Hệ thống AI tự động mở Cổng vào 1 cho xe vé tháng vào ô A-01 Tầng B1.',    '2026-10-17 07:20:00+07'),
        ('phan.thanh.thao@example.net',  'PAYMENT_COLLECT',  'PAYMENT',           1,  'Xác nhận thu phí đỗ xe qua VietQR cho phiên đỗ xe tại tầng F1.',           '2026-10-17 08:35:00+07')
) AS a(acc_email, action, entity_type, entity_id, message, occurred_at)
LEFT JOIN account acc ON a.acc_email IS NOT NULL AND lower(acc.email) = lower(a.acc_email) AND acc.deleted_at IS NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM activity_log existing
    WHERE existing.action = a.action
      AND existing.occurred_at = a.occurred_at::TIMESTAMPTZ
);

-- ----------------------------------------------------------------------------
-- 2.19. SYSTEM ALERTS (4 ALERTS ACROSS ALL 4 TYPES & 3 SEVERITIES — TL-13)
-- ----------------------------------------------------------------------------
INSERT INTO system_alert (
    alert_type, severity, message, entity_type, entity_id,
    occurred_at, resolved_at, resolved_by, created_at
)
SELECT
    sa.alert_type,
    sa.severity,
    sa.message,
    sa.entity_type,
    sa.entity_id,
    sa.occurred_at::TIMESTAMPTZ,
    sa.resolved_at::TIMESTAMPTZ,
    emp.id,
    sa.occurred_at::TIMESTAMPTZ
FROM (
    VALUES
        ('BLACKLIST_PLATE', 'CRITICAL', 'Phát hiện biển số thuộc danh sách Blacklist (Nợ phí quá hạn) tại khu vực cổng kiểm soát.', 'PLATE_BLACKLIST', 1, '2026-10-17 07:14:00+07', NULL, NULL),
        ('OVERSTAY',        'WARNING',  'Cảnh báo phương tiện đỗ liên tục gần chạm ngưỡng 48 giờ tại Tầng B2.',                     'VEHICLE_SESSION', 43, '2026-10-17 06:55:00+07', NULL, NULL),
        ('CAMERA_QUALITY',  'WARNING',  'Camera Cổng ra 1: Độ sáng môi trường thấp, tỷ lệ nhận diện AI giảm nhẹ.',                 'PARKING_GATE',    3, '2026-10-17 06:30:00+07', NULL, NULL),
        ('SYSTEM',          'INFO',     'Hoàn tất đồng bộ cấu hình trạm sạc ô tô điện Khu C trên toàn bộ 3 tầng.',                 'PARKING_LOT',     1, '2026-10-16 22:00:00+07', '2026-10-16 22:15:00+07', 'NV007')
) AS sa(alert_type, severity, message, entity_type, entity_id, occurred_at, resolved_at, resolved_emp_code)
LEFT JOIN employee emp ON sa.resolved_emp_code IS NOT NULL AND emp.code = sa.resolved_emp_code AND emp.deleted_at IS NULL
WHERE NOT EXISTS (
    SELECT 1
    FROM system_alert existing
    WHERE existing.alert_type = sa.alert_type
      AND existing.occurred_at = sa.occurred_at::TIMESTAMPTZ
);

-- ============================================================================
-- PART 2: SAMPLE OPERATIONAL DATA (REMOVABLE BLOCK — END)
-- ============================================================================

COMMIT;
