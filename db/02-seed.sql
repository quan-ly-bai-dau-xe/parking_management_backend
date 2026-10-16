-- ============================================================================
-- Car Parking Lot Management System Backend
-- Enterprise Lookup & Reference Seed Data Script (Schema v2 — Frontend-First)
-- Target PostgreSQL Version: PostgreSQL 18.6
-- File: db/02-seed.sql
-- Execution standard: psql -v ON_ERROR_STOP=1 -f db/02-seed.sql
-- Non-destructive: Pure insertion script (conforms to ADR-0003 & Rule 05)
-- Provenance Verification (TL-01..TL-16, OQ-57):
--   Primary source: Frontend export (`Parking Project`, 11 PNG screens).
--   Secondary source: SRS v4.1 (`Quan ly bai dau xe oto_SRS_v4.1.docx`).
--   All inferred or proposed values are strictly marked [PROPOSAL] with their OQ ID.
--   ZERO personal data, ZERO accounts/employees/customers, and ZERO password hashes.
--   Floors, zones, slots, and gates are configured at runtime by administrators.
--   cspell:words VIETQR NVVH NVTN
-- ============================================================================

BEGIN;

SET client_encoding = 'UTF8';

-- ----------------------------------------------------------------------------
-- 1. EMPLOYEE POSITIONS CATALOG (POSITION LOOKUP — TL-11)
-- ----------------------------------------------------------------------------
-- Source: Frontend `Quản lý nhân viên — Smart Mobility.png` role badges & filter:
-- "Quản lý", "Nhân viên vận hành", "Nhân viên thu ngân", "Kỹ thuật viên" (TL-11).
INSERT INTO position (code, name, description)
VALUES
    ('QL', 'Quản lý', 'Facility and operations manager ("Quản lý" on Quản lý nhân viên — Smart Mobility.png, TL-11)'),
    ('NVVH', 'Nhân viên vận hành', 'Parking lot operations staff ("Nhân viên vận hành" on Quản lý nhân viên — Smart Mobility.png, TL-11)'),
    ('NVTN', 'Nhân viên thu ngân', 'Parking lot cashier staff ("Nhân viên thu ngân" on Quản lý nhân viên — Smart Mobility.png, TL-11)'),
    ('KTV', 'Kỹ thuật viên', 'Parking facility and equipment technician ("Kỹ thuật viên" on Quản lý nhân viên — Smart Mobility.png, TL-11)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. VEHICLE TYPES CATALOG (VEHICLE TYPE LOOKUP — TL-09)
-- ----------------------------------------------------------------------------
-- Source: Frontend `Quản lý xe — Smart Mobility.png` ("Loại xe" filter & table badges):
-- "Ô tô", "Xe máy", "Xe điện" (TL-09).
INSERT INTO vehicle_type (code, name, description)
VALUES
    ('CAR', 'Ô tô', 'Standard passenger automobile ("Ô tô" on Quản lý xe — Smart Mobility.png, TL-09)'),
    ('MOTO', 'Xe máy', 'Two-wheeled motorized vehicle / motorcycle ("Xe máy" on Quản lý xe — Smart Mobility.png, TL-09)'),
    ('EV', 'Xe điện', 'Electric vehicle ("Xe điện" on Quản lý xe — Smart Mobility.png, TL-09)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 3. TICKET TARIFF TYPES CATALOG (TICKET TYPE LOOKUP — TL-10)
-- ----------------------------------------------------------------------------
-- Source: Frontend `Quản lý vé — Smart Mobility.png` ("Loại vé" filter, table, and
-- dialogs "Thêm vé mới", "Gia hạn vé", "Chi tiết vé"):
-- - "Vé ngày": 50.000đ (1 day)
-- - "Vé tháng": 500.000đ (30 days)
-- - "Vé quý": 1.200.000đ (90 days)
-- - "Vé năm": shown in filter dropdown without a sample row price; 4.800.000đ
--   (365 days, same 400.000đ/month rate as Vé quý) is seeded as [PROPOSAL] (OQ-79, TL-10).
INSERT INTO ticket_type (code, name, duration_days, default_price, description)
VALUES
    ('DAILY', 'Vé ngày', 1, 50000.00, 'Daily parking ticket at 50,000 VND ("Vé ngày", "50.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('MONTHLY', 'Vé tháng', 30, 500000.00, 'Monthly parking ticket at 500,000 VND ("Vé tháng", "500.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('QUARTERLY', 'Vé quý', 90, 1200000.00, 'Quarterly parking ticket at 1,200,000 VND ("Vé quý", "1.200.000đ" on Quản lý vé — Smart Mobility.png, TL-10)'),
    ('YEARLY', 'Vé năm', 365, 4800000.00, '[PROPOSAL] (OQ-79, TL-10) Annual parking ticket ("Vé năm" on Quản lý vé — Smart Mobility.png); default price 4,800,000 VND uses the same monthly rate as Vé quý')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. ADMINISTRATIVE BOUNDARY SAMPLES (ADMINISTRATIVE REFERENCE SAMPLE — TL-11, TL-15)
-- ----------------------------------------------------------------------------
-- Retained unchanged from Schema v1 per TL-15 ("administrative provinces already seeded stay").

-- 4.1. Provinces / Municipalities
INSERT INTO administrative_province (code, name)
VALUES
    ('49', 'Tỉnh Quảng Nam'),
    ('48', 'Thành phố Đà Nẵng')
ON CONFLICT (code) DO NOTHING;

-- 4.2. Districts / Towns
INSERT INTO administrative_district (province_id, code, name)
SELECT p.id, d.code, d.name
FROM (
    VALUES
        ('49', 'DB', 'Thị xã Điện Bàn'),
        ('48', 'HC', '[PROPOSAL] (OQ-50) Quận Hải Châu')
) AS d(p_code, code, name)
JOIN administrative_province p ON p.code = d.p_code
ON CONFLICT (code) DO NOTHING;

-- 4.3. Wards / Communes
INSERT INTO administrative_ward (district_id, code, name)
SELECT dist.id, w.code, w.name
FROM (
    VALUES
        ('DB', 'DN', 'Phường Điện Ngọc'),
        ('HC', 'TT', '[PROPOSAL] (OQ-50) Phường Thạch Thang')
) AS w(d_code, code, name)
JOIN administrative_district dist ON dist.code = w.d_code
ON CONFLICT (code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 5. DEFAULT PARKING LOT FACILITY (TL-02)
-- ----------------------------------------------------------------------------
-- Source: Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` filter "Bãi đỗ xe: Bãi xe Smart Mobility" (TL-02).
-- Floors, zones, slots, and gates are not seeded here; they are created by the
-- administrator through the Frontend ("+ Thêm tầng", "+ Thêm khu", "+ Thêm ô đỗ xe").
INSERT INTO parking_lot (code, name, address, is_active)
VALUES (
    'SMART_MOBILITY',
    'Bãi xe Smart Mobility',
    'Bãi xe Smart Mobility (configured from Sơ đồ bãi đậu xe — Smart Mobility.png, TL-02)',
    TRUE
)
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

COMMIT;
