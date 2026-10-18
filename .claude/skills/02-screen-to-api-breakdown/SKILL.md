---
name: 02-screen-to-api-breakdown
description: Deconstruct the 11 Frontend screen designs (Primary) and SRS v4.1 (Secondary) into RESTful API contracts, incorporating TL-28 derived values.
---

# Skill: Screen-to-API Breakdown & OpenAPI 3.0 Contracts

## 1. Objective

Deconstruct the 11 Frontend screen designs in `Parking Project` (Primary Source) and SRS v4.1 (Secondary Source) into RESTful API contracts, ensuring accurate representation of UI elements, filters, badges, and TL-28 derived fields.

## 2. Step-by-Step Breakdown Workflow

1. **Frontend Screen Inspection (Primary Source)**:
   - Inspect the 11 Frontend PNG images in `Parking Project` (`login-container.png`, `Trang chủ.png`, `Danh sách khách hàng.png`, `Quản lý phương tiện.png`, `Lịch sử ra vào bãi xe.png`, `Sơ đồ bãi đậu xe.png`, `Quản lý thông tin vé - Danh sách vé.png`, `Danh sách nhân viên.png`, `MainPage.png`, `icon.png`, `icon2.png`) and `docs/requirements/06-frontend-srs-db-alignment.md` (`TL-01`–`TL-35`).
   - Catalog all UI table columns, search filters, action buttons, modals, and status badges via `docs/requirements/07-fe-srs-traceability.md`.
2. **SRS v4.1 Alignment (Secondary Source)**:
   - Cross-reference with the corresponding SRS module (`docs/requirements/00-srs-catalog.md`) for verbatim validation messages, field length limits, and business constraints where the Frontend is silent.
3. **Incorporate TL-28 Derived Values (`docs/requirements/07-fe-srs-traceability.md` Section 3)**:
   - Compute required UI badges and metrics in selectors/serializers (`SerializerMethodField`) using the verified `TL-28` SQL queries:
     - **Ticket Expiring Soon (`Sắp hết hạn`)**: `status == 'ACTIVE' and now < effective_to <= now + 7 days`.
     - **Vehicle Derived Status**: `"Đang đỗ"` (open session `exit_time IS NULL`), `"Đang hoạt động"` (active ticket or no open session), `"Đã rời bãi"` (closed session and no active ticket).
     - **Remaining Ticket Days**: `GREATEST(0, CEIL(EXTRACT(EPOCH FROM (effective_to - now)) / 86400.0))`.
     - **Parking Duration (`Tổng thời gian đỗ`)**: `COALESCE(exit_time, now) - entry_time`.
     - **Customer Metrics**: Count of active subscriptions (`Thuê bao kích hoạt`) and tickets expiring within 7 days (`Sắp hết hạn (7 ngày)`).
     - **Floor Occupancy Bars**: Percentage of occupied slots (`ROUND(100.0 * occupied_slots / NULLIF(total_slots, 0), 0)`) from `v_slot_occupancy_by_floor`.
4. **Design Endpoint URIs & Methods**: Follow plural noun RESTful conventions and expose `isDeleted: bool` (`deleted_at is not None`, `TL-23`).
5. **Annotate with `drf-spectacular`**: Attach `@extend_schema` for OpenAPI 3.0 documentation (`13-api-first-contract-and-mock-data`).

## 3. Verification Checklist

- [ ] Every column, filter, and button visible in the 11 Frontend PNGs maps to an API field or parameter (`07-fe-srs-traceability.md`).
- [ ] All 6 groups of `TL-28` derived values are exposed in serializers.
- [ ] Verbatim SRS Vietnamese messages and registered `PROP-*` / `PROP-DEL-*` strings are preserved.
- [ ] Endpoints enforce role-based access control (`IsManager` / `IsEmployeeOrManager`) and always filter `deleted_at IS NULL` (`TL-27`).
