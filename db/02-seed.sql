-- ============================================================================
-- Car Parking Lot Management System Backend
-- Enterprise Lookup & Reference Seed Data Script
-- Target PostgreSQL Version: PostgreSQL 18.6
-- File: db/02-seed.sql
-- Execution standard: psql -v ON_ERROR_STOP=1 -f db/02-seed.sql
-- Non-destructive: Contains NO DROP statements (conforms to ADR-0003 & Rule 05)
-- Strict Provenance Verification (OQ-57):
-- Only values with authentic evidence in the SRS wireframes are included.
-- All inferred or extended values are strictly marked [PROPOSAL] with their OQ ID.
-- ZERO mock customer or employee data.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- 1. EMPLOYEE POSITIONS CATALOG (POSITION LOOKUP)
-- ----------------------------------------------------------------------------
-- Wireframe image4 & image5 show only "Bảo vệ" and "Giữ xe" in dropdown.
-- "Quản lý" is an architectural inference from SRS Section 3.1 Actor list, marked PROPOSAL.
INSERT INTO position (code, name, description)
VALUES 
    ('BV', 'Bảo vệ', 'Security guard for parking lot surveillance (from SRS wireframe example image4, image5)'),
    ('GX', 'Giữ xe', 'Parking lot attendant managing vehicle entry/exit (from SRS wireframe example image4, image5)'),
    ('QL', 'Quản lý', '[PROPOSAL] (OQ-57) Facility manager role derived from SRS Section 3.1 Actor list, pending PO confirmation (not in wireframe dropdown)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. VEHICLE TYPES CATALOG (VEHICLE TYPE LOOKUP)
-- ----------------------------------------------------------------------------
-- Wireframe image22 shows: Xe 4 chỗ, Xe 7 chỗ, Xe 12 chỗ.
-- Wireframe image9 & image10 show motorbikes: SH-150i, Honda SH.
-- "Loại xe khác" is an operational fallback, marked PROPOSAL.
INSERT INTO vehicle_type (code, name, description)
VALUES 
    ('CAR_4', 'Xe 4 chỗ', 'Standard passenger automobile with 4-5 seats (from SRS wireframe example image22)'),
    ('CAR_7', 'Xe 7 chỗ', 'Multi-purpose vehicle / SUV with 7 seats (from SRS wireframe example image22)'),
    ('CAR_12', 'Xe 12 chỗ', 'Commercial minibus / van with 12-16 seats (from SRS wireframe example image22)'),
    ('MOTO', 'Xe máy / SH-150i', 'Two-wheeled motorized vehicle / motorcycle (from SRS wireframe example image9, image10, OQ-49)'),
    ('OTHER', 'Loại xe khác', '[PROPOSAL] (OQ-49) Other specialized motor vehicle categories, pending PO confirmation')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 3. TICKET TARIFF TYPES CATALOG (TICKET TYPE LOOKUP)
-- ----------------------------------------------------------------------------
-- Wireframe image15 shows only one row: "Năm ... 100.000đ".
-- Wireframe image16 shows dropdown with options: "Tháng", "Năm".
-- "Vé Ngày" is an operational proposal for walk-in parking, marked PROPOSAL.
INSERT INTO ticket_type (code, name, duration_days, default_price, description)
VALUES 
    ('YEARLY', 'Vé Năm', 365, 100000.00, 'Annual parking ticket at 100,000 VND (from SRS wireframe example image15, image16)'),
    ('MONTHLY', 'Vé Tháng', 30, 100000.00, '[PROPOSAL] (OQ-57) Monthly parking ticket option shown in wireframe image16 dropdown, default price 100,000 VND pending PO confirmation'),
    ('DAILY', 'Vé Ngày', 1, 10000.00, '[PROPOSAL] (OQ-57) Daily transient ticket for walk-in vehicles, pending PO confirmation (not shown in wireframes)')
ON CONFLICT (code) WHERE deleted_at IS NULL DO NOTHING;

-- ----------------------------------------------------------------------------
-- 4. ADMINISTRATIVE BOUNDARY SAMPLES (ADMINISTRATIVE REFERENCE SAMPLE)
-- ----------------------------------------------------------------------------
-- Wireframe image6 shows: Quảng Nam -> Điện Bàn -> Điện Ngọc.
-- Wireframe image4 & image9 show the text "Đà Nẵng" inside an address cell.
-- District and Ward for Da Nang are marked [PROPOSAL] to provide complete sample tree.
-- In accordance with OQ-57, unevidenced provinces (Hà Nội, Cầu Giấy, etc.) are excluded.

-- 4.1. Provinces / Municipalities
INSERT INTO administrative_province (code, name)
VALUES 
    ('49', 'Tỉnh Quảng Nam'), -- from SRS wireframe example image6
    ('48', 'Thành phố Đà Nẵng') -- from SRS wireframe example text in address cell, image4, image9
ON CONFLICT (code) DO NOTHING;

-- 4.2. Districts / Towns
INSERT INTO administrative_district (province_id, code, name)
SELECT p.id, d.code, d.name
FROM (
    VALUES 
        ('49', 'DB', 'Thị xã Điện Bàn'), -- from SRS wireframe example image6
        ('48', 'HC', '[PROPOSAL] (OQ-50) Quận Hải Châu') -- Proposal: Sample urban district for Đà Nẵng
) AS d(p_code, code, name)
JOIN administrative_province p ON p.code = d.p_code
ON CONFLICT (code) DO NOTHING;

-- 4.3. Wards / Communes
INSERT INTO administrative_ward (district_id, code, name)
SELECT dist.id, w.code, w.name
FROM (
    VALUES 
        ('DB', 'DN', 'Phường Điện Ngọc'), -- from SRS wireframe example image6
        ('HC', 'TT', '[PROPOSAL] (OQ-50) Phường Thạch Thang') -- Proposal: Sample ward for Quận Hải Châu
) AS w(d_code, code, name)
JOIN administrative_district dist ON dist.code = w.d_code
ON CONFLICT (code) DO NOTHING;

COMMIT;
