---
name: 04-blackbox-test-case-writing
description: Design black-box test suites for backend APIs matching the 5-sheet template structure (Cover, Test_Case_List, Layout, Test_Case_Screen, Data_DB_Screen).
---

# Skill: Black-box Test Case Specification

## 1. Objective

Design black-box test cases for backend API endpoints, directly mapping to the 5-sheet structure found in the project's official test template (`01-Template/Blackbox_TC/`):

1. **Sheet 1: `Cover`**: Module metadata, author, date, document version.
2. **Sheet 2: `Test_Case_List`**: Summary matrix of test case identifiers, objectives, and execution status.
3. **Sheet 3: `Layout`**: Contract validation (HTTP headers, status codes, JSON schema, data types).
4. **Sheet 4: `Test_Case_<Screen>`**: Detailed test scenarios (Normal, Abnormal, Boundary, Concurrency).
5. **Sheet 5: `Data_DB_<Screen>`**: Database state prerequisites (Pre-DB) and post-execution verification (Post-DB).

## 2. Test Specification Workflow

### Structure of Sheet `Test_Case_<Screen>`

Each test case must include standardized attributes:

- **Test Case ID**: `TC_<Screen>_<Type>_<Number>` (e.g. `TC_4.3.4_DELETE_01`, `TC_4.1_LOGIN_02`).
- **Classification**:
  - `Normal`: Valid input data returning HTTP 200/201/204.
  - `Abnormal`: Invalid data, missing required fields, format violations returning HTTP 400.
  - `Boundary`: Edge length constraints (e.g. 45 characters vs 46 characters).
  - `Security / Concurrency`: Unauthorized access (HTTP 403), concurrent contention (HTTP 409).
- **Pre-condition**: Fixture records existing in database with specified states.
- **Input / Request Payload**: JSON payload or URL parameters.
- **Expected Output**:
  - HTTP status code (200, 400, 403, 404, 409).
  - Standard JSON error envelope.
  - Verbatim message string matching SRS (`MSG-...`) or proposal catalog (`PROP-...`).

### Structure of Sheet `Data_DB_<Screen>`

Document explicit database state changes:

- **Pre-Test Data**:
  - `id=101, license_plate='43A-123.45', deleted_at=NULL, deleted_by=NULL`
- **Post-Test Data**:
  - `id=101, license_plate='43A-123.45', deleted_at='2026-10-17 12:00:00+07', deleted_by=1`
  - Append-only audit row in `activity_log`: `action='SOFT_DELETE'`, `entity_type='vehicle'`, `entity_id=101` (`fn_audit_soft_delete_and_restore`)

## 3. Generic Test Suite Template

```markdown
<!-- ILLUSTRATIVE TEST SUITE -->
### Test Suite: Parking Ticket Deletion (SRS 4.6.4)

| Test Case ID | Test Objective | Input Condition | Expected HTTP Code | Expected Message (Exact SRS / Proposal) | Post-Test DB State |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **TC_4.6.4_01** | Delete valid expired ticket | Ticket id=50 (`effective_to <= now`, `status='EXPIRED'`) | 200 OK | `Xóa thành công` (MSG-4.6.4-M01) | `deleted_at IS NOT NULL`, `activity_log` row `'SOFT_DELETE'` |
| **TC_4.6.4_02** | Prevent deleting active ticket | Ticket id=51 (`effective_to > now`, `status='ACTIVE'`) | 400 Bad Request | `Vé chưa hết hạn, không được phép xóa.` [PROP-4.6.4-P01] | Unchanged |
| **TC_4.6.4_03** | Prevent deleting soft-deleted ticket | Ticket id=50 (already deleted) | 404 Not Found | `Vé không tồn tại hoặc đã bị xóa.` [PROP-4.6.4-P05] | Unchanged |
| **TC_4.6.4_04** | Concurrent deletion contention | 2 parallel delete requests for id=52 | 1 request: 200, 1 request: 409 | `Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.` [PROP-4.6.4-P03] | 1 record soft-deleted |
| **TC_4.6.4_05** | RBAC: Employee blocked | Auth: Role=EMPLOYEE | 403 Forbidden | Access denied (DEL-04: Manager-only) | Unchanged |
```

## 4. Verification Checklist

- [ ] Expected error messages cite canonical entries from `docs/requirements/00-srs-catalog.md` or proposal registry.
- [ ] Comprehensive coverage: Normal, Boundary, Missing fields, Unauthorized, Concurrency.
- [ ] Explicit Pre-DB and Post-DB states defined for mutating operations.
- [ ] Validates soft-delete behavior and `PROTECT` foreign key constraints.
