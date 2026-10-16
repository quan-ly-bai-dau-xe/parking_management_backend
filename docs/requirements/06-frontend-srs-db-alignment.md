# Frontend Design, SRS v4.1, and PostgreSQL Schema Alignment Report

## 1. Scope

Alignment audit across the 11 Frontend PNGs in `D:\GitHub\codegym\[FE-BE-Thực tập]-Project\Parking Project` (`9` screens + `2` icons `Vector.png`, `clarity_edit-line.png`; full inventory in `.agents/round17_fe_inventory.md`), SRS v4.1 (`Quan ly bai dau xe oto_SRS_v4.1.docx`, `image1.png`–`image25.png`), PostgreSQL 18.6 ([`db/01-schema.sql`](../../db/01-schema.sql), [`db/02-seed.sql`](../../db/02-seed.sql)), and ERD ([`db/03-erd.asta`](../../db/03-erd.asta), [`db/04-erd.png`](../../db/04-erd.png)–[`db/09-erd-reference-views.png`](../../db/09-erd-reference-views.png)). Statuses: `MATCH`, `FE-ONLY`, `SRS-ONLY`, `CONFLICT`, `SAMPLE-DATA-ERROR`, `UNVERIFIED`. Owner decisions `D1`–`D8` and [`01-open-questions.md`](01-open-questions.md) (`OQ-71`–`OQ-78`) are updated through Round 19 (`D5` and `D8` implemented; `D1`–`D4`, `D6`, `D7` deferred).

---

## 2. Alignment Matrix (`FRONTEND <-> SRS v4.1 <-> DATABASE`)

### 2.1 Screen-by-Screen Alignment Matrix

| Screen (`Filename & Size`)|FE Evidence|SRS v4.1 Evidence|DB Evidence (`01-schema.sql` / `02-seed.sql`)|Status & Findings |
| :---|:---|:---|:---|:--- |
| `login-container.png` (`1200x693`)|`Email hoặc Số điện thoại`, `Mật khẩu` (`Hiện`), `Ghi nhớ đăng nhập`, `Quên mật khẩu?`, `Đăng ký ngay`|4.1 (`image2.png` R5–9): `Tên đăng nhập` (`MSG-4.1-M03`), `Mật khẩu`, `Ghi nhớ mật khẩu`, `Quên mật khẩu` link (no dialog); 4.3.2 (`image5.png`): Admin-only provisioning|`account.username` (`lines 26, 37`, rejects `@`); no `email`/`phone`/self-signup (`OQ-02`, `OQ-55`); `persistent_login_token` (`lines 61-73`), `password_reset_token` (`lines 93-103`)|`CONFLICT` / `MATCH` (`F01`, `F02`, `D1`, `OQ-01`, `OQ-71`) |
| All 8 screens (`Main Page.png`..`Quản lý vé — Smart Mobility.png`)|Top bar (`LOGO`, `Camera`, `Admin`) + 7 top tabs (`Quản lý loại vé` on 6 screens vs `Quản lý vé` on 2)|4.2 (`image3.png` Home): LEFT side menu of 7 items (`Quản lý nhân viên`, `Quản lý khách hàng`, `Quản lý xe vào/ra`, `Quản lý vé`, `Thống kê`, `Quản lý bãi đỗ xe`, `Bảng thông báo`) + `Quản lý tài khoản` dropdown + `Chào admin`|`account.role` (`MANAGER`, `EMPLOYEE`, `CUSTOMER`, `line 38`)|`CONFLICT` (`F03`, `F04`, `F26`, `OQ-74`) |
| `Main Page.png` (`1278x2065`)|`VietQR`, 5 badges (+`Sạc xe điện`), `24` lots, `78.4%` (`392+108=500`), `35.4M`, `4 Cổng`, `Tầng B1..B3`, `Khu A..C` (`28.4%` vs `28/100=28.0%`), `SmartPark UI Template Kit`|4.5.2 (`image14.png`) & 4.7.1 (`image19.png`): 2 slot colors (green/red), single lot, integer floors, no EV/VietQR/zones/gates|`ck_slot_status_enum` (`line 517`, 4 states), `v_revenue_statistics` (`line 1140`), `v_vehicle_traffic_daily` (`line 1180`), `v_slot_occupancy_by_floor` (`line 1195`)|`CONFLICT` / `FE-ONLY` / `SAMPLE-DATA-ERROR` (`F04`–`F11`, `F23`, `F24`, `D3`, `D4`, `D7`) |
| `Trang chủ — Smart Mobility.png` (`1440x911`)|`342/550` vs `298/550`, `150.000đ (Tiền mặt: 18% \| QR: 82%)`, `AI: 98.4%`, `Cổng vào/ra`, `Xem ảnh (99%)`, `51G-888.88 Blacklist (Nợ phí)`, `>48h`, camera alert|4.2 (`image3.png`): Left menu & `Bảng thông báo`; traffic charts in 4.7.2 (`image20.png`)|Computable: logs, >48h, hourly traffic, floor occupancy. Not in DB: `QR`/`Tiền mặt`, AI score, gates, blacklist|`SAMPLE-DATA-ERROR` / `FE-ONLY` (`F04`–`F09`, `F23`, `F25`, `D2`, `D4`, `OQ-72`, `OQ-74`) |
| `Khách hàng — Smart Mobility.png` (`1440x911`)|Cards (`1,420`, `1,280`, `42`, `Blacklist: 15`), 4 cols (`Mã KH`, `Tên KH`, `SĐT`, `Số CCCD`) + `Chưa có dữ liệu`|4.4.1 (`image8.png`): 8 cols (`ID`, `Họ tên`, `Ngày sinh`, `CMND`, `Số ĐT`, `Email`, `Địa chỉ`, `Giới tính`) + 3 icons + Vehicle sub-table|`customer` (`lines 292-321`): `ck_customer_idcard_digits` (`line 316`); no `is_blacklisted`|`CONFLICT` / `SAMPLE-DATA-ERROR` (`F08`, `F22`, `F23`, `D4`, `OQ-74`) |
| `Quản lý xe — Smart Mobility.png` (`1470x1580`)|`Tổng: 6` vs `4+2+1=7`, 11 cols, dotted plates (`51K-992.14`, `30A-123.45`), `Xe điện`, `Vé quý`, `Đang đỗ`/`Đã rời bãi`, `↓ Xuất CSV`, bottom cards (`12/12/2026` vs `VT0001` `12/06/2026`, `Slot 42`, `Ghi chú`, `module Vé/Giao dịch`)|4.4.1–4.4.2 (`image8.png`, `image9.png`): Sub-table in Customer. 4.5.1/4.8.2: `Xe 4/7/12 chỗ`, `Xe máy`; no `Ghi chú` or `Giao dịch`|`vehicle` (`lines 437-461`) has `license_plate_norm` (`line 443`, `D5`/`OQ-75`), `v_customer_vehicle_summary` (`line 1277`); no `image_url`, `notes`, `status`. `02-seed.sql:34-54`|`CONFLICT` / `SAMPLE-DATA-ERROR` (`F05`, `F13`, `F14`, `F17` fixed, `F18`, `F19`, `F23`, `F26`, `D5`, `D6`) |
| `Lịch sử ra\vào — Smart Mobility.png` (`1440x911`)|5 filters (`00:00`, no buttons, `F29`); 7 cols (`Mã phiên đỗ xe`, `Tổng thời gian đỗ`, `Cước phí`)|4.5.1 (`image13.png`) live gate; 4.7.2 (`image20.png`) traffic chart; no session code/fee|`vehicle_entry_exit_log` (`lines 688-712`): `id`, `license_plate_norm` (`line 692`), `entry_time`, `exit_time`, `notes`; no `fee_amount`|`FE-ONLY` / `CONFLICT` (`F05`, `F20`, `F29`, `D2`, `OQ-72`) |
| `Sơ đồ bãi đậu xe — Smart Mobility.png` (`1440x1750`)|`+ Thêm tầng/khu/ô đỗ`, `Tầng B1`, `Khu A`, `Tổng: 24` (`7+12+5`), bar `18/24`, `16` cells (`XE ƯU TIÊN`), `A-01` green `TRỐNG` vs `Đang đỗ (30A-123.45)`, 4 manual status buttons, `Tầng B1 (72 ô)` vs `24+24=48 ô`, `Hoạt động gần đây`|4.5.2 (`image14.png`): Floors `1..10`, `108` slots/floor, `Rộng x Dài x Cao`. 4.8 (`image21.png`–`image25.png`): Per-slot CRUD, read-only detail popup (`image24.png`)|`parking_slot` (`lines 494-519`): `floor_number`, `slot_number`, `code`, `width`, `length`, `height`, `map_row`, `map_col`, `status` synced by triggers (`lines 872-1046`); only `MAINTENANCE` is manual|`CONFLICT` / `SAMPLE-DATA-ERROR` (`F09`–`F12`, `F18`, `F23`, `F26`, `D3`, `D4`, `D7`, `OQ-73`, `OQ-74`, `OQ-77`) |
| `Quản lý nhân viên - Smart mobility.png` (`1470x1299`)|`● Dữ liệu minh họa — chưa kết nối API`, 4 positions, `KHU VỰC` (`Hải Châu Đà Nẵng`), `TRẠNG THÁI` (`Không hoạt động`)|4.3.1 (`image4.png`): `ID`, `Họ tên`, `Ngày sinh`, `Địa chỉ`, `Số ĐT`, `Email`, `Giới tính`, `Vị trí` (`Bảo vệ`, `Giữ xe`) + `Sửa`, `Xóa`|`employee` (`lines 232-260`), `account.is_active` (`line 29`), `02-seed.sql:21-26` (`BV`, `GX`, `QL`). District ended `01-07-2025` (Law 72/2025/QH15)|`CONFLICT` (`F21`, `F23`, `F24`, `D6`, `OQ-50`, `OQ-57`, `OQ-76`) |
| `Quản lý vé — Smart Mobility.png` (`3470x911`) — Main|8 filters, 10 cols (omits `Họ tên`, `SĐT`, `Thao tác`, `F30`). `VT0001` (`51K-992-14`, `500k`), `VT0002` (`10/5/2026`–`10/5/2026`, `50k`, `Sắp hết hạn`), `VT0004` (`Vé quý`, `1.2M`), `VT0005` (`Đang gia hạn`)|4.6.1 (`image15.png`): Has `Họ tên`, `Số điện thoại`, `Sửa`, `Xóa` (`4.6.4`), no `Trạng thái`; `Vé Năm` = `100.000đ`|`ticket` (`lines 570-598`): `ck_ticket_time_order` (`line 589`) and `ck_ticket_status_enum` (`ACTIVE`, `EXPIRED`, `RENEWED`, `CANCELLED`, `line 591`)|`CONFLICT` / `SAMPLE-DATA-ERROR` (`F09`, `F13`, `F15`–`F17`, `F23`, `F30`, `D5`, `D6`, `OQ-75`, `OQ-76`) |
| `Quản lý vé — Smart Mobility.png` — Dialog 1|`Thêm vé mới`: `Khách hàng *`, `Xe *`, `Loại vé *`, `Vị trí đỗ xe *`, `Ngày hiệu lực *`, editable `Ngày hết hạn *`, `Giá vé *`, `Ghi chú`|4.6.2 (`image16.png`): Read-only `Họ tên`, `SĐT`, `Loại xe`, `Ngày hết hạn`; separate `Tầng` + `Vị trí`; no `Ghi chú`|`ticket` (`lines 570-598`) has no `notes` column|`CONFLICT` / `FE-ONLY` (`F16`, `F18`, `D4`, `OQ-74`, `OQ-76`) |
| `Quản lý vé — Smart Mobility.png` — Dialog 2|`Gia hạn vé`: `Mã vé` (`Chọn Gia hạn từ danh sách`), `Loại vé mới *`, `Vị trí đỗ xe mới *`, `Ngày hết hạn mới *`, `Giá gia hạn *`, `Ghi chú`|4.6.3 (`image17.png`): Read-only header + editable `Loại vé`, `Tầng`, `Vị trí`, `Giá`, `Ngày gia hạn`, `Ngày hết hạn`; no `Ghi chú`|`ticket_renewal` (`lines 634-658`, `OQ-58`) has no `notes` column|`CONFLICT` / `FE-ONLY` (`F16`, `F18`, `F30`, `D4`, `OQ-58`, `OQ-74`) |
| `Quản lý vé — Smart Mobility.png` — Dialog 3|`Chi tiết vé`: `VT0001`, `KH0001`, `51K-992-14`, `12/05/2026`–`12/06/2026`, `NV0005 (Nguyễn Văn A)`, `Ghi chú: -`, `Lịch sử gia hạn`|Not in SRS v4.1 (4.6 has only List, Add, Edit/Renew, Delete)|Backed by `ticket` + `ticket_renewal` + `employee` (no `ticket.notes`)|`FE-ONLY` / `SAMPLE-DATA-ERROR` (`F17`, `F18`, `F23`, `D4`, `OQ-74`) |
| `Vector.png` (`17x17`), `clarity_edit-line.png` (`18x18`)|Standalone pencil edit icons|Row edit (`Sửa`)|N/A|`MATCH` |

### 2.2 SRS v4.1 Screens Missing from FE (`SRS-ONLY` / `F03`) & Unspecified PO Questions

| SRS (`Wireframes`)|Requirement vs Frontend Export|DB Support (`db/01-schema.sql`)|Classification |
| :---|:---|:---|:---: |
| **4.1 & 4.2** (`image2.png`, `image3.png`)|**`Quên mật khẩu` & `Đổi mật khẩu/profile`**: SRS 4.1 (`image2.png` R8) has `Quên mật khẩu` link only; SRS 4.2 (`image3.png`) has `Quản lý tài khoản` dropdown only.|`password_reset_token` (`lines 93-103`), `account.password_hash` (`line 27`)|**Not specified by SRS — PO Question** (`OQ-01`) |
| **4.3.2–4.3.4** (`image5.png`–`image7.png`)|**Add/Edit/Delete Employee Modals**: `Tỉnh/Huyện/Xã`, `Vị trí`, default password checkbox, delete popup.|`employee`, `account`, `position`, `administrative_*`|`SRS-ONLY` (`F03`) |
| **4.4.2–4.4.5** (`image9.png`–`image12.png`)|**Customer `Thông tin xe` & Add/Edit/Delete Customer Modals**: Master-detail customer/vehicle forms, delete popup.|`customer`, `vehicle`, `administrative_*`|`SRS-ONLY` (`F03`) |
| **4.5.1** (`image13.png`)|**Barrier Gate Check-In/Out (`Quản lý xe ra/vào`)**: Dual-camera ANPR (`Xe vào`/`Xe ra`), `Tìm xe`, slot selection, `Lưu thông tin`.|`vehicle_entry_exit_log`, `fn_guard_slot_reservation_on_entry`, `fn_sync_slot_status_on_traffic`|`SRS-ONLY` (`F03`) |
| **4.6.4** (`image15.png`, `image18.png`)|**Ticket Row Actions (`Sửa`, `Xóa`) & Delete Ticket Popup (`Xác nhận xóa vé`)**: Expired, non-renewed tickets (`TH1..TH3`).|`ticket` (`ck_ticket_delete_only_expired`, `line 592`)|`SRS-ONLY` (`F03`, `F30`) |
| **4.7.1–4.7.2** (`image19.png`, `image20.png`)|**Statistics (`Thống kê tổng hợp`, `Thống kê chi tiết`)**: Revenue by `Tháng`/`Quý`/`Năm` (`"Tuần"` not in SRS), daily traffic, floor occupancy, vehicles-by-customer.|`v_revenue_statistics`, `v_vehicle_traffic_daily`, `v_slot_occupancy_by_floor`, `v_customer_vehicle_summary`, `fn_stat_*` (`lines 1140-1519`)|`SRS-ONLY` (`F03`) |
| **4.8.1–4.8.5** (`image21.png`–`image25.png`)|**Add/Edit/Detail/Delete Slot Modals**: Per-slot forms (`Rộng`, `Dài`, `Cao`), allowed vehicle types, delete popup.|`parking_slot`, `slot_allowed_vehicle_type`|`SRS-ONLY` (`F03`, `F12`) |
| **4.2 / Plan** (`image3.png`, Tasks 2 & 17)|**`Bảng thông báo` & `Quản lý tin tức`**: Left menu item on `image3.png` and `Tasks_Sprint_1`.|`news` (`lines 749-789`), `notification` (`lines 794-822`)|`SRS-ONLY` (`F03`, `OQ-51`) |

---

## 3. Candidate Findings (`F01..F27`) & Additional Findings (`F28..F31`)

All 31 findings are **Confirmed** (`F28` re-classified `INTENTIONAL-LAYOUT`, `F17` implemented Round 18, `F27` & `F31` implemented Round 19):

| ID (`Status`)|Evidence Summary (FE PNG, SRS v4.1, `db/01-schema.sql` / `db/02-seed.sql`) |
| :---|:--- |
| **F01** (`CONFLICT`)|`login-container.png`: `"Email hoặc Số điện thoại"` vs SRS 4.1 (`image2.png` R5) `"Tên đăng nhập"` (`MSG-4.1-M03`) & `account.username` (`lines 26, 37`) (`D1`, `OQ-71`). |
| **F02** (`CONFLICT`)|`login-container.png`: `"Đăng ký ngay"` vs SRS 3 & 4.3.2 (`image5.png` R14) Admin-only provisioning (`D1`, `OQ-71`). |
| **F03** (`SRS-ONLY`)|FE omits `Thống kê` (`4.7`), gate check-in/out (`4.5.1`), Employee/Customer/Slot CRUD modals (`4.3`, `4.4`, `4.8`), Delete Ticket (`4.6.4`), `Bảng thông báo` (`4.2` `image3.png`). (`Quên mật khẩu` dialog & `Đổi mật khẩu/profile` not specified in SRS — PO question). |
| **F04** (`CONFLICT` / `SAMPLE-DATA-ERROR`)|Tab 6 `"Quản lý loại vé"` (6 screens) vs `"Quản lý vé"` (2 screens); `Main Page.png` (`500` slots, `35.4M`) conflicts with `Trang chủ` (`550` slots, `150.000đ`). |
| **F05** (`FE-ONLY` / `CONFLICT`)|FE shows `"Cước phí"`, `"Tiền mặt: 18% \| QR: 82%"`, `"VietQR"`, `"module Vé/Giao dịch"`; SRS 4.7.1 (`image19.png`) & `v_revenue_statistics` (`line 1140`) use tickets/renewals only (`D2`, `OQ-72`). |
| **F06** (`FE-ONLY`)|`Main Page.png` & `Trang chủ` show `"4 Cổng quét tự động"`, `"Cổng vào 1/2"`, `"Cổng ra 1/2/3"`; not in SRS or DB (`D4`, `OQ-74`). |
| **F07** (`FE-ONLY`)|`Trang chủ` & `Lịch sử ra\vào` show AI score (`98.4%`, `Xem ảnh (99%)`, `Ảnh khớp`, `Cần duyệt`, camera alert); DB (`lines 697-698`) has image URLs only (`D4`, `OQ-74`). |
| **F08** (`FE-ONLY`)|`Main Page`, `Trang chủ`, `Khách hàng` show `"Blacklist (Nợ phí)"` and `"Blacklist/Tạm khoá: 15"`; not in SRS or DB (`D4`, `OQ-74`). |
| **F09** (`CONFLICT`)|FE uses `"Tầng B1..B3, F1"`; SRS 4.5.2/4.8.2 & `ck_slot_floor_range` (`line 511`) require positive integers `1..99` (`D3`, `OQ-73`). |
| **F10** (`FE-ONLY` / `CONFLICT`)|FE shows `"24 Khu bãi"`, `"Bãi xe Smart Mobility"`, `"Khu A..C"`, `"+ Thêm tầng/khu"`, `"Quản lý cấu trúc bãi"`; no lot/zone tables in DB (`D3`, `OQ-73`). |
| **F11** (`CONFLICT`)|`Main Page` adds `"Sạc xe điện"`; `Sơ đồ` adds 4 manual status buttons. In DB (`lines 517, 872-1046`), only `MAINTENANCE` is manual (`D4`, `D7`, `OQ-74`, `OQ-77`). |
| **F12** (`FE-ONLY` / `SRS-ONLY`)|`Sơ đồ` adds `"Người đặt trước"`, `"Ghi chú"`, `"ĐÃ ĐẶT 13:30"`, `"1h24m"`, `"XE ƯU TIÊN"`, ultrasonic badge, omitting SRS `Rộng`, `Dài`, `Cao` (`lines 501-503`) (`D4`, `OQ-74`). |
| **F13** (`CONFLICT`)|FE uses `Vé ngày` (`50k`), `Vé tháng` (`500k`), `Vé quý` (`1.2M`), `Vé năm` vs `02-seed.sql:49-54` (`100k`/`100k`/`10k`, no `Vé quý`, `OQ-57`) (`D6`, `OQ-76`). |
| **F14** (`CONFLICT`)|FE uses `Ô tô`, `Xe máy`, `Xe điện` vs SRS 4.5.1/4.8.2 & `02-seed.sql:34-41` (`Xe 4/7/12 chỗ`, `Xe máy`, `Loại khác`) (`D6`, `OQ-76`). |
| **F15** (`CONFLICT`)|`Quản lý vé` shows 5 statuses (`+Sắp hết hạn`, `+Đang gia hạn`) vs `ck_ticket_status_enum` (`line 591`, 4 states) and omits Delete Ticket (`line 592`) (`D6`, `OQ-76`). |
| **F16** (`CONFLICT` / `SAMPLE-DATA-ERROR`)|`Quản lý vé` mixes `mm/dd/yyyy` & `d/m/yyyy`; `VT0002` has `10/5/2026`–`10/5/2026`, violating `ck_ticket_time_order` (`line 589`) (`D6`, `OQ-76`). |
| **F17** (`CONFLICT` -> **RESOLVED `D5`**)|`XE0001` `"51K-992.14"` vs `"51K-992-14"` (`VT0001`); `XE0002` `"30A-123.45"` vs `"30A-123-45"`. **Implemented (`D5`, `OQ-75`)**: `fn_normalize_license_plate(text)`, stored `license_plate_norm VARCHAR(20)` (`lines 443, 692`), unique indexes (`lines 482, 739`), normalized guard (`line 1069`). |
| **F18** (`FE-ONLY`)|FE adds `"Ghi chú"` on `ticket`, `ticket_renewal`, `vehicle`, `parking_slot`; only `vehicle_entry_exit_log.notes` (`line 701`) exists in DB (`D4`, `OQ-74`). |
| **F19** (`FE-ONLY`)|`Quản lý xe` shows `Trạng thái` (`Đang đỗ`, `Đang hoạt động`, `Đã rời bãi`); derived from open `vehicle_entry_exit_log` rows (`D6`, `OQ-76`). |
| **F20** (`FE-ONLY`)|`Lịch sử ra\vào` shows `Mã phiên đỗ` and `Tổng thời gian đỗ`; derived from `id` and `exit_time - entry_time` (`D2`, `OQ-72`). |
| **F21** (`CONFLICT`)|`Quản lý nhân viên` uses 4 non-SRS positions, `"Không hoạt động"` (`account.is_active`, `line 29`), district `"KHU VỰC"` (ended `01-07-2025`, Law 72/2025/QH15), omitting `Ngày sinh`, `Giới tính`, `Địa chỉ` (`D6`, `OQ-76`). |
| **F22** (`CONFLICT`)|`Khách hàng` has 4 cols and no actions, omitting SRS 4.4.1 (`image8.png`) cols `Ngày sinh`, `Email`, `Địa chỉ`, `Giới tính` and icons (`D4`, `D6`, `OQ-74`, `OQ-76`). |
| **F23** (`SAMPLE-DATA-ERROR`)|7 mockup errors: (1) `A-01` green `TRỐNG` vs `Đang đỗ (30A-123.45)`; (2) `16` cells vs `Tổng: 24` (`12+5=17 != 18/24`) and `72` vs `24+24=48`; (3) `Trang chủ` `342/550` vs `138+120+40=298/550`; (4) `Main Page` `28/100=28.0% != 28.4%` and `24` vs `392+108=500`; (5) `Main Page` vs `Trang chủ` conflict & identical `09:24:32` times; (6) `NV005` (`Võ Ngọc Linh`) vs `NV0005 (Nguyễn Văn A)`; (7) `XE0001` `12/12/2026` (`Slot 42`) vs `VT0001` `12/06/2026` (`Tầng B1 - A10`), `4+2+1=7 != 6`, `1,420` customers above `Chưa có dữ liệu`. |
| **F24** (`MATCH`)|`Main Page.png` (`SmartPark UI Template Kit`) and `Quản lý nhân viên` (`Dữ liệu minh họa — chưa kết nối API`) confirm static mockups. |
| **F25** (`FE-ONLY` / `DB-AHEAD`)|Computable: logs, >48h parked, hourly traffic, floor occupancy (`v_slot_occupancy_by_floor`), ticket revenue (`v_revenue_statistics`). Not computable: Blacklist/debt (`F08`), AI/camera alerts (`F07`), gates (`F06`), Cash/QR split (`F05`). |
| **F26** (`FE-ONLY`)|Top bar `Camera`, `↓ Xuất CSV`, `↓ Xuất báo cáo`, and `Hoạt động gần đây` have no audit log table in DB (`D4`, `OQ-74`). |
| **F27** (`DIAGRAM-DEFECT` -> **RESOLVED `D8`**)|`04-erd.png` draws all `44` FKs (`33` business + `11` `deleted_by`, `db/00-README.md:290`); `05..08` omitted **12 business FKs**. **Implemented (`D8`, `OQ-78`)**: all 12 added via `astah_add_presentation_link` (`0` missing across `04..09`). |
| **F28** (`INTENTIONAL-LAYOUT`)|`Parking_Ticket` (`07`) renders `parking_slot` & `ticket_type` as full tables and `240x45` stubs; `Operations_Content` (`08`) renders two `employee` stubs. Per [`db/00-README.md`](../../db/00-README.md) lines `314–318` (*"Collapsed Neighbor Stubs... each boundary side receives at most one relationship link"*), this is an **intentional layout choice**; missing links (`F27`) were the real defect. |
| **F29** (`FE-ONLY` / `CONFLICT`)|`Lịch sử ra\vào` `Bộ lọc nhanh` has `00:00` time-only inputs and **no `Tìm kiếm` or `Reset` button**. |
| **F30** (`CONFLICT`)|`Quản lý vé` main table omits `Họ tên`, `Số điện thoại`, and `Thao tác` (`Sửa`/`Xóa`) required by SRS 4.6.1/4.6.4 and Dialog 2. |
| **F31** (`DIAGRAM-DEFECT` -> **RESOLVED `D8`**)|`04-erd.png` note said `"209-attribute schemas"` (`211` pre-Round 18 table + `22` view = `233`). **Implemented (`D8`, `OQ-78`)**: `db/03-erd.asta` synced to **213** table + **22** view = **235** cols; `04-erd.png` note updated to `"213-attribute"` via `astah_set_note_text`. |

---

## 4. Database Verification (`F17`), Relationship Chain Correction & ERD Audit (`F27`, `D8`)

### 4.1 PostgreSQL 18.6 Verification of `F17` (`D5` Implemented in `db/01-schema.sql`)

Tested in throwaway `postgres:18.6` containers (`--rm --tmpfs /var/lib/postgresql:rw`, random password, `docker volume ls -q` = `27`): `fn_normalize_license_plate(p_input TEXT)` (`db/01-schema.sql:424-432`) returns `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))`. `vehicle.license_plate_norm` (`line 443`) and `vehicle_entry_exit_log.license_plate_norm` (`line 692`) are `STORED` generated columns with `CHECK (license_plate_norm <> '')` (`lines 458, 705`). `uq_vehicle_license_plate_active` (`line 482`) and `uq_log_open_session_plate` (`line 739`) reject duplicate variants (`'51K-992.14'`, `'51K-992-14'`, `'51K99214'`, `'51K 992 14'`, `'51k-992.14'` -> `'51K99214'`) with `SQLSTATE 23505` (`T1`, `T5`) and allow reuse after soft-delete (`T4`). `fn_guard_slot_reservation_on_entry()` (`line 1069`) compares normalized plates, accepting all 4 variants (`T2`) and rejecting `'51K-992.15'` with `SQLSTATE 23514` (`'Lỗi dữ liệu không tìm thấy đê lưu'`, `T3`).

### 4.2 Why `parking_slot -> ticket -> vehicle -> employee` Is Wrong & Corrected 25-FK Table

1. **Reversed Direction**: `ticket.slot_id` references `parking_slot(id)` (`fk_ticket_slot`, `line 595`: **`ticket -> parking_slot`**).
2. **Zero `vehicle <-> employee` FKs (`0`)**: `pg_constraint` confirms `0` FKs between `vehicle` and `employee`. `vehicle` references `customer`, `vehicle_type`, `ticket_type` (`lines 454-456`); `employee` is referenced by `ticket.issued_by` (`fk_ticket_issued_by`), `ticket_renewal.renewed_by`, `vehicle_entry_exit_log.entry_staff_id`/`exit_staff_id`, and `news.author_id`.
3. **Visual Cause (`07-erd-parking-ticket.png`)**: Stub `employee` (`x=1250,y=920`) sat beside stub `vehicle` (`x=800,y=920`) below `ticket` (`x=760,y=460`) while **`fk_ticket_issued_by` (`ticket -> employee`) was omitted** before Round 19 (`D8`).

| FK Constraint (`Child -> Parent`)|Note|
| :---|:---|
| `fk_ticket_slot`: `ticket(slot_id) -> parking_slot(id)`|`ticket->parking_slot`|
| `fk_ticket_vehicle_customer`: `ticket(vehicle_id, customer_id) -> vehicle(id, customer_id)`|`ticket->vehicle->customer`|
| `fk_vehicle_customer`: `vehicle(customer_id) -> customer(id)`|`vehicle->customer`|
| `fk_ticket_issued_by`: `ticket(issued_by) -> employee(id)`|Added `07`,`08` (`D8`)|
| `fk_ticket_type`: `ticket(ticket_type_id) -> ticket_type(id)`|`ticket->ticket_type`|
| `fk_vehicle_type`: `vehicle(vehicle_type_id) -> vehicle_type(id)`|Added `07` (`D8`)|
| `fk_vehicle_ticket_type`: `vehicle(ticket_type_id) -> ticket_type(id)`|Added `07` (`D8`)|
| `fk_renewal_ticket`: `ticket_renewal(ticket_id) -> ticket(id)`|`ticket_renewal->ticket`|
| `fk_renewal_old_slot`: `ticket_renewal(old_slot_id) -> parking_slot(id)`|Added `07` (`D8`)|
| `fk_renewal_new_slot`: `ticket_renewal(new_slot_id) -> parking_slot(id)`|`ticket_renewal->parking_slot`|
| `fk_renewal_renewed_by`: `ticket_renewal(renewed_by) -> employee(id)`|`ticket_renewal->employee`|
| `fk_slot_allowed_slot`: `slot_allowed_vehicle_type(slot_id) -> parking_slot(id)`|`slot_allowed->parking_slot`|
| `fk_log_ticket`: `vehicle_entry_exit_log(ticket_id) -> ticket(id)`|`log->ticket`|
| `fk_log_vehicle`: `vehicle_entry_exit_log(vehicle_id) -> vehicle(id)`|`log->vehicle`|
| `fk_log_slot`: `vehicle_entry_exit_log(slot_id) -> parking_slot(id)`|`log->parking_slot`|
| `fk_log_entry_staff`: `vehicle_entry_exit_log(entry_staff_id) -> employee(id)`|`log->employee`|
| `fk_log_exit_staff`: `vehicle_entry_exit_log(exit_staff_id) -> employee(id)`|Added `08` (`D8`)|
| `fk_news_author`: `news(author_id) -> employee(id)`|`news->employee`|
| `fk_employee_account`: `employee(account_id) -> account(id)`|Added `08` (`D8`)|
| `fk_employee_position`: `employee(position_id) -> position(id)`|`employee->position`|
| `fk_employee_district_province`: `employee(district_id, province_id) -> administrative_district(id, province_id)`|`employee->district`|
| `fk_employee_ward_district`: `employee(ward_id, district_id) -> administrative_ward(id, district_id)`|`employee->ward`|
| `fk_customer_account`: `customer(account_id) -> account(id)`|`customer->account`|
| `fk_customer_district_province`: `customer(district_id, province_id) -> administrative_district(id, province_id)`|`customer->district`|
| `fk_customer_ward_district`: `customer(ward_id, district_id) -> administrative_ward(id, district_id)`|`customer->ward`|

### 4.3 Per-Diagram FK Link Audit (`F27`, `F28`, `F31`) & `astah-uml` MCP Tool Implementation (`D8`)

Per [`db/00-README.md`](../../db/00-README.md) lines `290` & `314–318`, `11` `deleted_by` FKs are on `04-erd.png`, and `05..09` use **Collapsed Neighbor Stubs** (`200..240x45 px`, `F28`). In Round 19 (`D8`, `OQ-78`), all **12 missing business FKs** on `05..08`, the two `license_plate_norm` columns (`213` table + `22` view = `235` total attributes), and the `04-erd.png` legend note (`"213-attribute"`) were added via `astah-uml` MCP tools (**0** missing business FKs remaining):

| Diagram (`PNG`, `Unique/Nodes`, `Before->After FKs`)|12 Business FKs Added in Round 19 (`F27`, **0** Missing After)|Layout / Sync Result (`F28`, `F31`)|
| :---|:---|:---|
| **`ERD_Overview`** (`04-erd.png`, `23/23`, **44->44**)|**0** (`33` business + `11` `deleted_by` drawn)|Note `209-attribute` -> `213-attribute`; `2` `license_plate_norm` cols (`F31`)|
| **`Account_Staff`** (`05-erd-account-staff.png`, `7/7`, **6->7**)|**+1**: `fk_admin_ward_district` (**0** missing)|Stubs retained; `0` crossings|
| **`Customer_Vehicle`** (`06-erd-customer-vehicle.png`, `7/7`, **6->7**)|**+1**: `fk_admin_ward_district` (**0** missing)|`vehicle.license_plate_norm` (`«PUQ»`) added; `0` crossings|
| **`Parking_Ticket`** (`07-erd-parking-ticket.png`, `8/10`, **9->14**)|**+5**: `fk_ticket_issued_by`, `fk_renewal_old_slot`, `fk_renewal_old_ticket_type`, `fk_vehicle_ticket_type`, `fk_vehicle_type` (**0** missing)|`parking_slot` & `ticket_type` stubs (`F28`) retained; `0` crossings|
| **`Operations_Content`** (`08-erd-operations-content.png`, `8/9`, **6->11**)|**+5**: `fk_log_exit_staff`, `fk_ticket_issued_by`, `fk_ticket_slot`, `fk_ticket_vehicle_customer`, `fk_employee_account` (**0** missing)|`vehicle_entry_exit_log.license_plate_norm` (`«PUQ»`) added; 2nd `employee` stub (`F28`) retained; `0` crossings|
| **`Reference_Views`** (`09-erd-reference-views.png`, `7/7`, **2->2**)|**0** (`fk_admin_district_province`, `fk_admin_ward_district` drawn)|`22` view cols (`6+4+6+6`) present|

**Why `D8` Paused in Round 18 Per Owner Decision (6) & Round 19 Verification (`38 -> 39` `astah-uml` MCP Tools)**:
Testing a sandbox copy of `db/03-erd.asta` against `C:\Users\Kirito\.gemini\antigravity\mcp\astah-uml\*.json` and `D:\GitHub\Server\mcp-uml\bridge\src\com\mcp\astah\{ModelOperations,DiagramOperations}.java` confirmed **4 of 5 operations reported in Round 18 already worked**, leaving **1 real gap** (fixed in Round 19 Task D & applied in Task E):
- **Verified Working (4/5)**: (1) `astah_add_presentation_link` (`DiagramOperations.java:339-464`, `line 351`) resolves `relationship` by FK name; (2) `astah_add_attribute` (`ModelOperations.java:224-268`, `lines 231, 237, 244`) with `type="VARCHAR(20)"` and `stereotype="PUQ"` binds to `DataTypes::VARCHAR(20)` (`41` classes unchanged); (3) `«PUQ»` removal works via `astah_delete_element` + `astah_add_attribute` (`ModelOperations.java:224-268, 469-507`); (4) `astah_add_presentation_node` (`DiagramOperations.java:271-327`, `lines 277-303`) and `astah_set_presentation_style` (`lines 482-564`, `lines 495-525`) accept `width` and `height`.
- **Single Real Gap (1/5 — Fixed in Round 19 Task D & Applied in Task E)**: None of the 38 tools called `IPresentation.setLabel(String)` on a `Note` (`DiagramOperations.java:87-127`, `lines 482-564`; `handleGetDiagramInfo` `lines 571-640` reads `node.getLabel()` at `line 586`). Task D added `astah_set_note_text` (`39` tools, `DiagramOperations.java:1383-1497`), and Task E regenerated `db/03-erd.asta` and `db/04-erd.png`..`db/09-erd-reference-views.png` via MCP tools.

---

## 5. Owner / Product Owner Decision List (`D1..D8` — All Owner Approved)

| ID (`Topic & Findings / OQs`)|Owner-Approved Default|Round 19 Status|
| :---|:---|:---:|
| **D1** (`F01`, `F02`, `OQ-71`: Login Identifier & Self-Signup)|Login by `username` (`Tên đăng nhập`) per SRS 4.1; remove `"Đăng ký ngay"` on FE (no DB change).|**Owner Approved — Deferred to PO / FE**|
| **D2** (`F05`, `F20`, `F25`, `F29`, `OQ-72`: Fees & Payments)|Keep payments, per-session fees, and transactions out of v1; derive duration/ID from `vehicle_entry_exit_log`.|**Owner Approved — Deferred to PO**|
| **D3** (`F09`, `F10`, `OQ-73`: Floor Naming & Zones)|Keep `floor_number INTEGER` (`1..99`); add no `parking_lot` or `parking_zone` tables.|**Owner Approved — Deferred to PO**|
| **D4** (`F06`–`F08`, `F11`, `F12`, `F18`, `F25`, `F26`, `OQ-74`: Non-SRS FE Extras)|Defer EV, priority, blacklist, gates, AI, extra notes, and activity feed to PO; retain `width`, `length`, `height` on `parking_slot`.|**Owner Approved — Deferred to PO**|
| **D5** (`F17`, `OQ-75`: License-Plate Normalization)|Add `fn_normalize_license_plate(text)`, stored generated `license_plate_norm VARCHAR(20)`, unique indexes, and normalized trigger comparison.|**Owner Approved — IMPLEMENTED (`db/01-schema.sql`)**|
| **D6** (`F13`–`F16`, `F19`, `F21`, `F22`, `F30`, `OQ-76`: Taxonomy, Seeds & Derived Statuses)|Keep seeds until PO confirms prices/types; keep `Sắp hết hạn`, `Đang đỗ`/`Đã rời bãi`, `Không hoạt động` derived; enforce `effective_to > effective_from`.|**Owner Approved — Deferred to PO**|
| **D7** (`F11`, `OQ-77`: Manual Slot Buttons vs Trigger Sync)|Only `MAINTENANCE` is manual; `AVAILABLE`, `OCCUPIED`, `RESERVED` remain trigger-managed.|**Owner Approved — Deferred to PO / FE**|
| **D8** (`F27`, `F28`, `F31`, `OQ-78`: Module ERD Links, Stubs & Legend)|Keep stub layout (`F28`), add `license_plate_norm` cols, draw 12 missing business FKs (`F27`), update `04-erd.png` note to `213-attribute` (`F31`) via `astah-uml` MCP tools (`astah_set_note_text` added in Task D).|**Owner Approved — IMPLEMENTED (`db/03-erd.asta`, `db/04..09.png`)**|

---

## 6. Implemented DDL for `D5` / `F17` / `OQ-75` in `db/01-schema.sql`

```sql
CREATE FUNCTION fn_normalize_license_plate(p_input TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE AS $$
    SELECT UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'));
$$;
-- vehicle (lines 443, 458, 482) & vehicle_entry_exit_log (lines 692, 705, 731, 739):
-- license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED,
-- CONSTRAINT ck_vehicle_license_plate_norm_nonempty CHECK (license_plate_norm <> ''),
-- CONSTRAINT ck_log_license_plate_norm_nonempty CHECK (license_plate_norm <> ''),
CREATE UNIQUE INDEX uq_vehicle_license_plate_active ON vehicle (license_plate_norm) WHERE deleted_at IS NULL;
CREATE INDEX idx_log_license_plate ON vehicle_entry_exit_log (license_plate_norm);
CREATE UNIQUE INDEX uq_log_open_session_plate ON vehicle_entry_exit_log (license_plate_norm) WHERE exit_time IS NULL;
-- fn_guard_slot_reservation_on_entry() (line 1069):
-- IF NOT FOUND OR fn_normalize_license_plate(NEW.license_plate) <> fn_normalize_license_plate(v_registered_plate) THEN
--     RAISE EXCEPTION 'Lỗi dữ liệu không tìm thấy đê lưu' USING ERRCODE = 'check_violation';
-- END IF;
```
