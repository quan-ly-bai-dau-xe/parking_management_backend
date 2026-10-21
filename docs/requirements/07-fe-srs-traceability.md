# Frontend & SRS Requirements Traceability Matrix

Traceability matrix for `parking_management_backend` (Round 28). Cross-references 100% of **11 UI design files** (`Parking Project`) and **SRS v4.1** (Sections 4.1–4.8, NFRs) against [`db/01-schema.sql`](../../db/01-schema.sql) and [`db/02-seed.sql`](../../db/02-seed.sql).

---

## 1. Traceability Methodology & UI Assets

- **`COVERED`**: Directly mapped to schema objects (tables, columns, constraints, FKs, views).
- **`DERIVED`**: Computed dynamically at runtime via SQL or serializers per **TL-28**.
- **`GAP`**: Variations resolved by Team Lead decisions (`TL-01`–`TL-41`).
- **Trigram Rule (TL-41, G4)**: Query GIN trigram columns via direct `col ILIKE '%x%'` (`Bitmap Index Scan`); avoid `lower(col) LIKE ...` (forces Seq Scan).

### Authoritative UI Design Files (11 Files in `Parking Project`)

1. `login-container.png`
2. `Trang chủ — Smart Mobility.png`
3. `Khách hàng — Smart Mobility.png`
4. `Quản lý xe — Smart Mobility.png`
5. `Lịch sử ra/vào — Smart Mobility.png` (Windows: `Lịch sử ra\vào — Smart Mobility.png`)
6. `Sơ đồ bãi đậu xe — Smart Mobility.png`
7. `Quản lý vé — Smart Mobility.png`
8. `Quản lý nhân viên - Smart mobility.png`
9. `Main Page.png`
10. `Vector.png`
11. `clarity_edit-line.png`

---

## 2. Frontend Screen Traceability Matrix (67 Items)

| ID | Element | Target Object | Status | Decision / Logic |
|---|---|---|:---:|---|
| TRC-FE-01-01 | Login ID | account(email,phone) | COVERED | Lowercase lookup (TL-01,21) |
| TRC-FE-01-02 | Password | account.password_hash | COVERED | Argon2 hash (OQ-01) |
| TRC-FE-01-03 | Remember Login | persistent_login_token | COVERED | Split-token (OQ-01,TL-36) |
| TRC-FE-01-04 | Forgot Password | password_reset_token | COVERED | Timed token (OQ-84,TL-36) |
| TRC-FE-01-05 | Register Link | account, customer | COVERED | Auto-create account (TL-01) |
| TRC-FE-01-06 | Hero Banner | N/A (UI asset) | COVERED | UI asset (TL-16) |
| TRC-FE-02-01 | Slot KPI (342/550) | v_slot_occupancy_by_floor | COVERED | Occupancy (TL-14) |
| TRC-FE-02-02 | Traffic KPI (52 in) | vehicle_entry_exit_log | DERIVED | Daily count (entry >= TODAY) |
| TRC-FE-02-03 | Revenue KPI (150k) | v_revenue_today_by_method | COVERED | Daily sum (TL-07,14) |
| TRC-FE-02-04 | AI KPI (98.4%) | v_ai_recognition_stats | COVERED | AI ratio (TL-06,14) |
| TRC-FE-02-05 | Activity Feed | vehicle_entry_exit_log, gate | COVERED | Feed log (TL-06) |
| TRC-FE-02-06 | Floor Bars (B1 92%) | v_slot_occupancy_by_floor | DERIVED | Occupancy bar (TL-28.6,29) |
| TRC-FE-02-07 | Traffic Chart 24h | v_traffic_by_hour | COVERED | Hourly traffic (TL-14) |
| TRC-FE-02-08 | Emergency Alerts | system_alert, blacklist | COVERED | Alerts (TL-08,13) |
| TRC-FE-03-01 | Total Customers | v_customer_status_summary | COVERED | Customer count (TL-08) |
| TRC-FE-03-02 | Active Subscribers | ticket, customer | DERIVED | Active subscribers (TL-28.5) |
| TRC-FE-03-03 | Expiring Soon (7d) | ticket, customer | DERIVED | Expiring 7d (TL-28.5) |
| TRC-FE-03-04 | Blacklist/Suspended | customer.status | COVERED | Status filter (TL-08) |
| TRC-FE-03-05 | Customer Filters | customer(code,name,phone,id) | COVERED | Trigram & prefix (TL-31,41) |
| TRC-FE-03-06 | Customer Table | customer, vehicle summary | COVERED | Summary (TL-15) |
| TRC-FE-04-01 | Vehicle Filters | vehicle, vehicle_type, ticket | COVERED | Indexed FKs (TL-31) |
| TRC-FE-04-02 | Vehicle KPIs | vehicle, ticket | DERIVED | State/validity (TL-28) |
| TRC-FE-04-03 | Vehicle Grid | vehicle, customer, ticket, slot | COVERED | Profile (TL-09) |
| TRC-FE-04-04 | Mockup "Xe máy" | vehicle_type | GAP | Cars only (CAR, EV) (TL-20,35) |
| TRC-FE-04-05 | Derived Status | vehicle_entry_exit_log, ticket | DERIVED | Derived status (TL-28.2) |
| TRC-FE-04-06 | Vehicle Detail | vehicle(brand,model,color,date) | COVERED | Attributes (TL-09) |
| TRC-FE-04-07 | Owner Detail | customer, vehicle summary | COVERED | Contact & vehicles |
| TRC-FE-04-08 | Ticket Lifecycle | ticket, ticket_type | DERIVED | Days & % (TL-28.3) |
| TRC-FE-05-01 | Session Filters | vehicle_entry_exit_log | COVERED | Indexed (TL-05,31) |
| TRC-FE-05-02 | Session Code | vehicle_entry_exit_log.session_code | COVERED | Unique code (TL-05) |
| TRC-FE-05-03 | Plate & Photos | vehicle_entry_exit_log(plate,photos) | COVERED | Plate & URLs (TL-06) |
| TRC-FE-05-04 | Timestamps in/out | vehicle_entry_exit_log(entry, exit) | COVERED | TIMESTAMPTZ (TL-34) |
| TRC-FE-05-05 | Parking Duration | vehicle_entry_exit_log | DERIVED | Duration interval (TL-28.4) |
| TRC-FE-05-06 | Parking Fee | vehicle_entry_exit_log.fee_amount | COVERED | Fee NUMERIC(12,2) (TL-05) |
| TRC-FE-05-07 | ALPR Camera Scan | apps/parking/views/scans.py (`POST /api/v1/parking/plate-scans/`) | COVERED | Round 32 Fast-ALPR scan + Pillow security validation |
| TRC-FE-05-08 | Auto Vehicle & Customer Fill | apps/parking/views/lookup.py (`GET /api/v1/parking/vehicle-lookup/`) | COVERED | Round 32 Exact lookup by license_plate_norm (TL-17) |
| TRC-FE-05-09 | Check-in Action | apps/parking/views/sessions.py (`POST /api/v1/parking/sessions/check-in/`) | COVERED | Round 32 Session creation (#PK-YYYYMMDD-NN), blacklist guard |
| TRC-FE-05-10 | Check-out & Tariff Payment | apps/parking/views/sessions.py (`POST /api/v1/parking/sessions/check-out/`) | COVERED | Round 32 TL-50 tariff Decimal, atomic payment row |
| TRC-FE-05-11 | Gate Selection | apps/parking/views/gates.py (`GET /api/v1/parking/gates/`) | COVERED | Round 32 Active barrier gates list |
| TRC-FE-05-12 | Modal Tìm Xe (Unified Search) | apps/parking/views/search.py (`GET /api/v1/parking/vehicle-search/`) | COVERED | Round 32 Task 9 multi-field search (TL-41 GIN trigram) |
| TRC-FE-06-01 | Hierarchy 4-lvl | lot, floor, zone, slot | COVERED | 4-level model (TL-02,29) |
| TRC-FE-06-02 | Slot Filters | parking_slot, allowed_type | COVERED | Filters (TL-37) |
| TRC-FE-06-03 | Slot Stats KPI | v_slot_occupancy_by_floor | COVERED | Counts (TL-14) |
| TRC-FE-06-04 | 2D Grid (A1-B08) | parking_slot(map_row, map_col) | COVERED | Grid coords (TL-02,03) |
| TRC-FE-06-05 | Slot Live States | parking_slot.status, triggers | COVERED | Sync guards (TL-03) |
| TRC-FE-06-06 | Slot Reservation | slot_reservation | COVERED | Exclusion (TL-04) |
| TRC-FE-06-07 | Manual Slot Action | parking_slot, guard triggers | COVERED | Guarded (TL-03,38) |
| TRC-FE-06-08 | Activity Feed | activity_log | COVERED | Append-only (TL-12) |
| TRC-FE-07-01 | Ticket Filters | ticket, customer, vehicle, slot | COVERED | Search indexes (TL-31) |
| TRC-FE-07-02 | Ticket Badges | ticket.status | COVERED / DERIVED | Enum / Derived (TL-28.1) |
| TRC-FE-07-03 | Slot Location | parking_floor.name, slot.code | DERIVED | Floor + slot code (TL-29) |
| TRC-FE-07-04 | Dialog 1: Add | ticket, payment | COVERED | Issue ticket (TL-10,38) |
| TRC-FE-07-05 | Dialog 2: Renew | ticket_renewal, payment | COVERED | Renewal flow (TL-10) |
| TRC-FE-07-06 | Dialog 3: Detail | ticket, renewal, employee | COVERED | Detail view |
| TRC-FE-08-01 | Employee KPIs | employee, position | COVERED | Staff counts (TL-11) |
| TRC-FE-08-02 | Employee Filters | employee(code, name, email, pos) | COVERED | Staff lookup (TL-31) |
| TRC-FE-08-03 | Employee Code | employee.code, ck constraint | COVERED | Regex `^NV[0-9]{3,4}$` (TL-11) |
| TRC-FE-08-04 | Four Positions | position | COVERED | Positions (TL-11) |
| TRC-FE-08-05 | Employee Area | district, province | GAP / DERIVED | 3 tiers (TL-15,30) |
| TRC-FE-08-06 | Employee Status | employee.status | COVERED | ACTIVE/INACTIVE (TL-11) |
| TRC-FE-08-07 | Delete Emp Guard | employee.deleted_at, trigger | COVERED | Soft delete (DEL-01) |
| TRC-FE-09-01 | Executive KPIs | v_slot_occupancy_by_floor, payment | COVERED | Aggregation (TL-14) |
| TRC-FE-09-02 | Gate Scanners | parking_gate, log | COVERED | Gate scans (TL-06) |
| TRC-FE-09-03 | Floor Tab (B1-B3) | parking_floor | COVERED | Floor tabs (TL-02,29) |
| TRC-FE-09-04 | Hero Marketing | N/A (UI asset) | COVERED | UI copy (TL-16) |
| TRC-FE-10-01 | Trash Icon 17x17 | N/A (UI icon asset) | COVERED | Delete modal (`Vector.png`, TL-16) |
| TRC-FE-10-02 | Edit Icon 18x18 | N/A (UI icon asset) | COVERED | Edit modal (`clarity_edit-line.png`, TL-16) |

---

## 3. SRS v4.1 Functional & Non-Functional Traceability Matrix (45 Items)

| ID | Requirement | Target Object | Status | Guard & Logic |
|---|---|---|:---:|---|
| TRC-SRS-01-01 | Login by ID/Password (4.1.1) | account, customer, employee | COVERED | Auth (TL-01) |
| TRC-SRS-01-02 | Invalid Credential (4.1.1) | MSG-4.1-01 | COVERED | 'Xin vui lòng nhập lại Tên đăng nhập...' |
| TRC-SRS-01-03 | Special Chars Msg (4.1.1) | MSG-4.1-02 | COVERED | 'Tên đăng nhập không chứa ký tự đặc biệt' |
| TRC-SRS-01-04 | Persistent Login (4.1.1) | persistent_login_token | COVERED | Split-token (OQ-01, TL-36) |
| TRC-SRS-02-01 | Role-Based Access (4.2.1) | account.role, ck constraint | COVERED | Enum roles (TL-01) |
| TRC-SRS-02-02 | Manager vs Staff Menu (4.2.1) | API Permissions / DRF | COVERED | Manager only (OQ-45) |
| TRC-SRS-03-01 | Employee List & Filter (4.3.1) | employee, position | COVERED | Filter (TL-11) |
| TRC-SRS-03-02 | Add Employee Form (4.3.2) | employee, account | COVERED | Validation (TL-15) |
| TRC-SRS-03-03 | Edit Employee Profile (4.3.3) | employee, row_version trigger | COVERED | OCC row_version |
| TRC-SRS-03-04 | Delete Employee (DEL-01, 4.3.4) | employee.deleted_at, trigger | COVERED | Soft delete (TL-25) |
| TRC-SRS-03-05 | Employee Delete Msgs (4.3.4) | MSG-4.3.4-M01..M03 | COVERED | 'Xóa nhân viên thành công', 'Lỗi hệ thống' |
| TRC-SRS-04-01 | Customer Search (4.4.1) | customer, summary view | COVERED | Search (TL-31,41) |
| TRC-SRS-04-02 | View Customer Cars (4.4.2) | vehicle, vehicle_type | COVERED | Vehicles sub-grid |
| TRC-SRS-04-03 | Add Customer & Cars (4.4.3) | customer, vehicle | COVERED | Tx create (TL-15) |
| TRC-SRS-04-04 | Edit Customer Profile (4.4.4) | customer, vehicle | COVERED | RESTRICT FK |
| TRC-SRS-04-05 | Delete Customer (DEL-02, 4.4.5) | customer.deleted_at, trigger | COVERED | Guarded delete (TL-25) |
| TRC-SRS-04-06 | PII Anonymization (4.4.5) | customer(anonymized fields) | COVERED | PII anon (OQ-12) |
| TRC-SRS-05-01 | Vehicle Entry Check-in (4.5.1) | vehicle_entry_exit_log, guard (`POST /api/v1/parking/sessions/check-in/`) | COVERED | Check-in, session_code, blacklist guard (Round 32) |
| TRC-SRS-05-02 | Exit & Payment (4.5.1) | vehicle_entry_exit_log, payment (`POST /api/v1/parking/sessions/check-out/`) | COVERED | Check-out, TL-50 tariff Decimal, atomic payment (Round 32) |
| TRC-SRS-05-03 | Entry Guard Msgs (4.5.1) | MSG-4.5.1-M01..M03, PROP-4.5.1-P01..P12 | COVERED | Verbatim M03 fix ('lỗi kết nối'), mapped trigger exceptions (Round 32) |
| TRC-SRS-05-04 | Parking Visual Grid (4.5.2) | lot, floor, zone, slot | COVERED | 4-level map (TL-02) |
| TRC-SRS-05-05 | Slot Maint Guard (4.5.2) | MSG-4.5.2-M02, PROP-4.5.2-P01 | COVERED | 'Vị trí này đang bảo trì, chọn vị trí khác' |
| TRC-SRS-05-06 | Offline Plate Scan ALPR (4.5.1) | apps/parking/views/scans.py (`POST /api/v1/parking/plate-scans/`) | COVERED | Offline Fast-ALPR OCR, Pillow magic validation & EXIF strip (Round 32) |
| TRC-SRS-05-07 | Exact Vehicle Lookup (4.5.1) | apps/parking/views/lookup.py (`GET /api/v1/parking/vehicle-lookup/`) | COVERED | Exact match on license_plate_norm, parking position, ticket (Round 32) |
| TRC-SRS-05-08 | Vehicle Search Modal (Task 9) | apps/parking/views/search.py (`GET /api/v1/parking/vehicle-search/`) | COVERED | Multi-field search (q, name, phone, plate) utilizing TL-41 GIN trigram (Round 32) |
| TRC-SRS-06-01 | Ticket List & Expiry (4.6.1) | ticket, ticket_type | COVERED / DERIVED | Filter/derived (TL-28) |
| TRC-SRS-06-02 | Issue / Buy Ticket (4.6.2) | ticket, payment | COVERED | Issue ticket (TL-10,38) |
| TRC-SRS-06-03 | Ticket Renewal Flow (4.6.3) | ticket_renewal, ticket | COVERED | Renewal (OQ-52) |
| TRC-SRS-06-04 | Delete Ticket (DEL-04, 4.6.4) | ticket.deleted_at, guard | COVERED | Expired only (TL-25) |
| TRC-SRS-06-05 | Delete Ticket Msgs (4.6.4) | MSG-4.6.4-M01..M03 | COVERED | 'Xóa vé thành công', 'Lỗi kết nối CSDL' |
| TRC-SRS-07-01 | Revenue Statistics (4.7.1) | v_revenue_statistics, stat fn | COVERED | Sum revenue (TL-07,27) |
| TRC-SRS-07-02 | Traffic Statistics (4.7.2) | v_vehicle_traffic_daily, stat fn | COVERED | Daily traffic (TL-27) |
| TRC-SRS-07-03 | Export Reports (4.7.1/2) | API ViewSet export | COVERED | Export (TL-27) |
| TRC-SRS-08-01 | Slot List & Dimensions (4.8.1) | parking_slot, parking_zone | COVERED | Dimensions/types (TL-37) |
| TRC-SRS-08-02 | Add Parking Slot (4.8.2) | parking_slot, allowed_type | COVERED | Validation (TL-02,37) |
| TRC-SRS-08-03 | Edit Parking Slot (4.8.3) | parking_slot, row_version | COVERED | OCC row_version |
| TRC-SRS-08-04 | Slot Detail View (4.8.4) | parking_slot, allowed_type | COVERED | Dimensions/EV (TL-37) |
| TRC-SRS-08-05 | Delete Slot (DEL-05, 4.8.5) | parking_slot.deleted_at, guard | COVERED | Guarded delete (TL-25) |
| TRC-SRS-09-01 | Administrative Units (NFR) | province, district, ward | COVERED | VN admin units (TL-15) |
| TRC-SRS-09-02 | News & Announcements (NFR) | news | COVERED | News (TL-15) |
| TRC-SRS-09-03 | In-App Notifications (NFR) | notification | COVERED | Notifications (TL-15) |
| TRC-SRS-09-04 | Automated ALPR Gates (NFR) | parking_gate | COVERED | ALPR gates (TL-06) |
| TRC-SRS-09-05 | Blacklist & Debt (NFR) | plate_blacklist | COVERED | Blacklist (TL-08) |
| TRC-SRS-09-06 | Multi-Target Payments (NFR) | payment | COVERED | Payment link (TL-39) |
| TRC-SRS-09-07 | Activity Log Audit (NFR) | activity_log | COVERED | Audit log (TL-12) |

---

## 4. SQL Proof Queries for Frontend Derived Values (TL-28)

Six UI values are computed dynamically per **TL-28** to avoid redundancy:

### 4.1. Expiring Tickets (TL-28.1)

```sql
SELECT t.code, c.full_name, v.license_plate, tt.name AS ticket_type, t.effective_to AS expires_at, t.status AS base_status,
  CASE WHEN t.status = 'ACTIVE' AND t.effective_to BETWEEN '2026-10-17 00:00:00+07'::TIMESTAMPTZ AND '2026-10-17 00:00:00+07'::TIMESTAMPTZ + INTERVAL '7 days' THEN 'Sắp hết hạn'
       WHEN t.status = 'ACTIVE' AND t.effective_to > '2026-10-17 00:00:00+07'::TIMESTAMPTZ + INTERVAL '7 days' THEN 'Đang hoạt động'
       WHEN t.status = 'ACTIVE' THEN 'Đã hết hạn' ELSE t.status END AS fe_display_status,
  GREATEST(0, CEIL(EXTRACT(EPOCH FROM (t.effective_to - '2026-10-17 00:00:00+07'::TIMESTAMPTZ)) / 86400))::INTEGER AS remaining_days
FROM ticket t JOIN customer c ON c.id = t.customer_id AND c.deleted_at IS NULL
JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
JOIN ticket_type tt ON tt.id = t.ticket_type_id AND tt.deleted_at IS NULL
WHERE t.deleted_at IS NULL ORDER BY t.effective_to ASC;
```

### 4.2. Derived Parking Status (TL-28.2)

```sql
SELECT v.code, v.license_plate, c.full_name, vt.name AS vehicle_type,
  CASE WHEN EXISTS (SELECT 1 FROM vehicle_entry_exit_log l WHERE l.vehicle_id = v.id AND l.exit_time IS NULL) THEN 'Đang đỗ'
       WHEN EXISTS (SELECT 1 FROM ticket t WHERE t.vehicle_id = v.id AND t.status IN ('ACTIVE','RENEWING') AND t.effective_to >= '2026-10-17 00:00:00+07'::TIMESTAMPTZ AND t.deleted_at IS NULL) THEN 'Đang hoạt động'
       ELSE 'Đã rời bãi' END AS derived_status,
  (SELECT ps.code || ' (' || pf.name || ')' FROM vehicle_entry_exit_log l JOIN parking_slot ps ON ps.id = l.slot_id JOIN parking_zone pz ON pz.id = ps.zone_id JOIN parking_floor pf ON pf.id = pz.floor_id WHERE l.vehicle_id = v.id AND l.exit_time IS NULL LIMIT 1) AS current_parked_slot
FROM vehicle v JOIN customer c ON c.id = v.customer_id AND c.deleted_at IS NULL
JOIN vehicle_type vt ON vt.id = v.vehicle_type_id AND vt.deleted_at IS NULL
WHERE v.deleted_at IS NULL ORDER BY v.code ASC;
```

### 4.3. Remaining Days & Progress (TL-28.3)

```sql
SELECT t.code, v.license_plate, tt.name AS ticket_type, t.effective_from, t.effective_to,
  GREATEST(0, CEIL(EXTRACT(EPOCH FROM (t.effective_to - '2026-10-17 00:00:00+07'::TIMESTAMPTZ)) / 86400))::INTEGER AS remaining_days,
  ROUND((EXTRACT(EPOCH FROM (LEAST(t.effective_to, '2026-10-17 00:00:00+07'::TIMESTAMPTZ) - t.effective_from)) / NULLIF(EXTRACT(EPOCH FROM (t.effective_to - t.effective_from)), 0)) * 100, 1) AS consumed_percentage
FROM ticket t JOIN vehicle v ON v.id = t.vehicle_id AND v.deleted_at IS NULL
JOIN ticket_type tt ON tt.id = t.ticket_type_id AND tt.deleted_at IS NULL
WHERE t.deleted_at IS NULL AND t.status = 'ACTIVE' ORDER BY remaining_days ASC;
```

### 4.4. Session Duration (TL-28.4)

```sql
SELECT l.session_code, l.license_plate, l.entry_time, l.exit_time,
  CASE WHEN l.exit_time IS NULL THEN 'Đang đỗ' ELSE 'Đã rời bãi' END AS session_state,
  COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time AS duration_interval,
  EXTRACT(HOUR FROM (COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time))::INTEGER || 'h' || LPAD(EXTRACT(MINUTE FROM (COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time))::INTEGER::TEXT, 2, '0') || 'm' AS formatted_duration,
  l.fee_amount FROM vehicle_entry_exit_log l ORDER BY l.entry_time DESC LIMIT 10;
```

### 4.5. Subscription Metrics (TL-28.5)

```sql
WITH ref AS (SELECT '2026-10-17 00:00:00+07'::TIMESTAMPTZ AS now)
SELECT COUNT(*)::BIGINT AS total_customers,
  COUNT(DISTINCT c.id) FILTER (WHERE EXISTS (SELECT 1 FROM ticket t, ref WHERE t.customer_id = c.id AND t.status = 'ACTIVE' AND t.effective_to >= ref.now AND t.deleted_at IS NULL))::BIGINT AS active_subscribers,
  COUNT(DISTINCT c.id) FILTER (WHERE EXISTS (SELECT 1 FROM ticket t, ref WHERE t.customer_id = c.id AND t.status = 'ACTIVE' AND t.effective_to BETWEEN ref.now AND ref.now + INTERVAL '7 days' AND t.deleted_at IS NULL))::BIGINT AS expiring_within_7_days,
  COUNT(*) FILTER (WHERE c.status IN ('SUSPENDED', 'BLACKLISTED'))::BIGINT AS blacklisted_or_suspended
FROM customer c WHERE c.deleted_at IS NULL;
```

### 4.6. Floor Occupancy Percentage Bars (TL-28.6)

```sql
WITH occ AS (
  SELECT v.floor_id, v.floor_code, v.floor_name, SUM(v.total_slots)::BIGINT AS total_slots, SUM(v.operational_slots)::BIGINT AS operational_slots,
    SUM(v.occupied_slots + v.reserved_slots + v.charging_slots)::BIGINT AS used_slots, SUM(v.available_slots)::BIGINT AS available_slots,
    COALESCE(ROUND(100.0 * SUM(v.occupied_slots + v.reserved_slots + v.charging_slots) / NULLIF(SUM(v.operational_slots), 0), 1), 0.0) AS occ_pct
  FROM v_slot_occupancy_by_floor v GROUP BY v.floor_id, v.floor_code, v.floor_name
)
SELECT floor_code, floor_name, total_slots, operational_slots, used_slots, available_slots, occ_pct AS occupancy_percentage,
  CASE WHEN occ_pct >= 90.0 THEN 'Sắp đầy' ELSE 'Còn chỗ' END AS status_badge,
  floor_name || ' · ' || ROUND(occ_pct, 0)::TEXT || '% (' || used_slots::TEXT || '/' || operational_slots::TEXT || ' chỗ)' AS fe_display_label
FROM occ ORDER BY floor_code ASC;
```

---

## 5. Traceability Audit Summary & Verification Checklist

- [x] **100% UI Image Coverage**: All 11 UI design files verified across 67 items (Section 1 & 2).
- [x] **100% SRS Coverage**: Sections 4.1–4.8, deletion guards DEL-01..DEL-05, NFRs mapped across 45 items (Section 3).
- [x] **Schema Invariant**: Preserves 28 tables, 8 views, 69 FKs, 338+55 columns.
- [x] **Zero Gaps**: All variations resolved under `TL-29`–`TL-50`.
