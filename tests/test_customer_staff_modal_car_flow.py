"""
End-to-end integration tests for Customer, Staff (Employee), and Vehicle flows.

Verifies:
1. Customer creation, list filtering, modal vehicle registration (CAR & EV),
   vehicle detail (ticket state and owner count), customer detail, and KPI
   summaries cross-checked against independent SQL.
2. Customer optimistic concurrency control (row_version) and DEL-02 delete guard.
3. Staff (Employee) lifecycle (list, create, update, soft delete) and DEL-01
   self-deletion protection for an authenticated Manager with an Employee row.
4. Role gates (GET/POST/PATCH/DELETE and anonymous 401) across MANAGER,
   EMPLOYEE, and CUSTOMER accounts.
5. Sprint-2 negative paths (duplicate plate, multi-field validation errors,
   and unique conflicts).
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.employees.models import Employee, Position
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


def _lookup_by_code(items: list[dict[str, Any]], code: str) -> dict[str, Any]:
    """Find a unique item by code without positional fallbacks."""
    matches = [item for item in items if item.get("code") == code]
    assert len(matches) == 1, f"Expected unique item with code={code!r}, got {matches}"
    return matches[0]


def _get_sql_vehicle_kpis() -> dict[str, int]:
    """Compute the 4 vehicle KPI counts directly from PostgreSQL for cross-check."""
    sql = """
        WITH rep_ticket AS (
            SELECT v.id AS vehicle_id, COALESCE(
                (SELECT t.id FROM ticket t
                 WHERE t.vehicle_id = v.id AND t.deleted_at IS NULL
                   AND t.status IN ('ACTIVE', 'RENEWING') AND t.effective_to >= CURRENT_TIMESTAMP
                 ORDER BY t.effective_to DESC, t.id DESC LIMIT 1),
                (SELECT t.id FROM ticket t
                 WHERE t.vehicle_id = v.id AND t.deleted_at IS NULL AND t.status != 'CANCELLED'
                 ORDER BY t.effective_to DESC, t.id DESC LIMIT 1)
            ) AS ticket_id
            FROM vehicle v WHERE v.deleted_at IS NULL
        ), classified AS (
            SELECT rt.vehicle_id,
                   CASE
                       WHEN t.id IS NULL THEN 'none'
                       WHEN t.effective_to < CURRENT_TIMESTAMP THEN 'expired'
                       WHEN t.effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'expiring_soon'
                       ELSE 'valid'
                   END AS ticket_state
            FROM rep_ticket rt LEFT JOIN ticket t ON t.id = rt.ticket_id
        )
        SELECT COUNT(v.id),
               COUNT(v.id) FILTER (
                   WHERE EXISTS (SELECT 1 FROM vehicle_entry_exit_log l WHERE l.vehicle_id = v.id AND l.exit_time IS NULL)
                      OR c.ticket_state IN ('valid', 'expiring_soon')
               ),
               COUNT(v.id) FILTER (WHERE c.ticket_state = 'expiring_soon'),
               COUNT(v.id) FILTER (WHERE c.ticket_state = 'expired')
        FROM vehicle v JOIN classified c ON c.vehicle_id = v.id WHERE v.deleted_at IS NULL;
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    assert row is not None
    return {
        "total_vehicles": int(row[0]),
        "active_vehicles": int(row[1]),
        "expiring_soon_tickets": int(row[2]),
        "expired_tickets": int(row[3]),
    }


def _get_or_create_account(email: str, phone: str, role: str) -> Account:
    acc, _ = Account.objects.get_or_create(
        email=email,
        defaults={
            "phone": phone,
            "role": role,
            "is_active": True,
            "password": f"!dummy_password_hash_{role.lower()}",
        },
    )
    return acc


def _auth_client(account: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=account)
    return client


@pytest.fixture
def manager_account() -> Account:
    """Manager Account linked to an active Employee row for DEL-01 checks."""
    acc = _get_or_create_account(
        "manager_flow_test@smartpark.vn", "0909000101", "MANAGER"
    )
    ql_pos = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    assert ql_pos is not None, "Seed data must provide QL manager position"
    Employee.objects.get_or_create(
        account=acc,
        defaults={
            "code": "NV890",
            "full_name": "Quản lý Flow Test",
            "email": acc.email or "manager_flow_test@smartpark.vn",
            "phone": "0909000101",
            "position": ql_pos,
            "status": "ACTIVE",
        },
    )
    return acc


@pytest.fixture
def manager_api_client(manager_account: Account) -> APIClient:
    """Authenticated APIClient for Manager."""
    return _auth_client(manager_account)


@pytest.fixture
def employee_api_client() -> APIClient:
    """Authenticated APIClient for Employee."""
    return _auth_client(
        _get_or_create_account(
            "employee_flow_test@smartpark.vn", "0909000102", "EMPLOYEE"
        )
    )


@pytest.fixture
def customer_api_client() -> APIClient:
    """Authenticated APIClient for Customer."""
    return _auth_client(
        _get_or_create_account(
            "customer_flow_test@smartpark.vn", "0909000103", "CUSTOMER"
        )
    )


def _create_vehicle(
    client: APIClient,
    customer_id: int,
    vehicle_type_id: int,
    plate: str,
    model_name: str,
    brand: str = "Toyota",
    color: str = "Trắng",
    notes: str = "",
) -> dict[str, Any]:
    res = client.post(
        "/api/v1/vehicles/",
        {
            "license_plate": plate,
            "model_name": model_name,
            "brand": brand,
            "color": color,
            "vehicle_type_id": vehicle_type_id,
            "customer_id": customer_id,
            "notes": notes,
        },
        format="json",
    )
    assert res.status_code == status.HTTP_201_CREATED, res.json()
    return dict(res.json())


def test_customer_and_modal_vehicle_e2e_flow(employee_api_client: APIClient) -> None:
    """Verify tasks 4.4.3, 4.4.1, Other (modal add vehicle), 4.4.2, and KPI SQL parity."""
    kpi_keys = {
        "total_vehicles",
        "active_vehicles",
        "expiring_soon_tickets",
        "expired_tickets",
    }
    before_res = employee_api_client.get("/api/v1/vehicles/summary/")
    assert before_res.status_code == status.HTTP_200_OK
    before_kpi = before_res.json()
    assert set(before_kpi.keys()) == kpi_keys
    assert before_kpi == _get_sql_vehicle_kpis()

    cust_res = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "Nguyễn Văn Minh Flow",
            "phone": "0987111222",
            "email": "minh_flow@smartpark.vn",
            "identity_card_number": "048202611999",
            "gender": "Nam",
            "date_of_birth": "1995-05-15",
        },
        format="json",
    )
    assert cust_res.status_code == status.HTTP_201_CREATED, cust_res.json()
    cust = cust_res.json()

    list_res = employee_api_client.get(f"/api/v1/customers/?code={cust['code']}")
    assert list_res.status_code == status.HTTP_200_OK
    assert list_res.json()["count"] == 1
    assert list_res.json()["results"][0]["id"] == cust["id"]

    types_res = employee_api_client.get("/api/v1/vehicle-types/")
    assert types_res.status_code == status.HTTP_200_OK
    car_type = _lookup_by_code(types_res.json(), "CAR")
    ev_type = _lookup_by_code(types_res.json(), "EV")
    assert car_type["id"] != ev_type["id"]

    car = _create_vehicle(
        employee_api_client,
        cust["id"],
        car_type["id"],
        "51K-888.88",
        "Camry 2.5Q",
        notes="Xe cá nhân đăng ký vé tháng",
    )
    _create_vehicle(
        employee_api_client,
        cust["id"],
        ev_type["id"],
        "51K-888.99",
        "VF8 Plus",
        brand="VinFast",
        color="Xanh dương",
        notes="Xe điện cần sạc tại tầng B1",
    )

    veh_detail = employee_api_client.get(f"/api/v1/vehicles/{car['id']}/")
    assert veh_detail.status_code == status.HTTP_200_OK
    v_data = veh_detail.json()
    assert v_data["ticket"] is None
    assert v_data["status"] == "left"
    assert v_data["customer"]["id"] == cust["id"]
    assert v_data["customer"]["registered_vehicles_count"] == 2
    assert v_data["vehicle_type"]["id"] == car_type["id"]

    cust_detail = employee_api_client.get(f"/api/v1/customers/{cust['id']}/")
    assert cust_detail.status_code == status.HTTP_200_OK
    c_vehicles = cust_detail.json()["vehicles"]
    assert len(c_vehicles) == 2
    assert {v["license_plate"] for v in c_vehicles} == {"51K-888.88", "51K-888.99"}
    assert all(v["ticket"] is None for v in c_vehicles)

    after_res = employee_api_client.get("/api/v1/vehicles/summary/")
    assert after_res.status_code == status.HTTP_200_OK
    after_kpi = after_res.json()
    assert set(after_kpi.keys()) == kpi_keys
    assert after_kpi["total_vehicles"] == before_kpi["total_vehicles"] + 2
    assert after_kpi == _get_sql_vehicle_kpis()


def test_customer_edit_occ_and_del02_delete_flow(
    employee_api_client: APIClient,
) -> None:
    """Verify tasks 4.4.4 (OCC PATCH + 409) and 4.4.5 (DEL-02 guard + soft delete)."""
    cust_res = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "Lê Thị Thu Hà Flow",
            "phone": "0987333444",
            "identity_card_number": "048202622888",
            "address": "10 Bạch Đằng, Đà Nẵng",
        },
        format="json",
    )
    assert cust_res.status_code == status.HTTP_201_CREATED, cust_res.json()
    cust = cust_res.json()
    cust_id, cust_code, row_ver = cust["id"], cust["code"], cust["row_version"]

    car_type = _lookup_by_code(
        employee_api_client.get("/api/v1/vehicle-types/").json(), "CAR"
    )
    veh = _create_vehicle(
        employee_api_client, cust_id, car_type["id"], "51K-777.55", "Civic RS", "Honda"
    )

    patch_ok = employee_api_client.patch(
        f"/api/v1/customers/{cust_id}/",
        {"row_version": row_ver, "address": "99 Trần Phú, Hải Châu, Đà Nẵng"},
        format="json",
    )
    assert patch_ok.status_code == status.HTTP_200_OK
    assert patch_ok.json()["address"] == "99 Trần Phú, Hải Châu, Đà Nẵng"
    assert patch_ok.json()["row_version"] == row_ver + 1

    patch_stale = employee_api_client.patch(
        f"/api/v1/customers/{cust_id}/",
        {"row_version": row_ver, "address": "Địa chỉ xung đột"},
        format="json",
    )
    assert patch_stale.status_code == status.HTTP_409_CONFLICT
    assert patch_stale.json()["code"] == "MSG-4.3.1-M03"
    cust_obj = Customer.objects.get(id=cust_id)
    assert cust_obj.address == "99 Trần Phú, Hải Châu, Đà Nẵng"

    del_blocked = employee_api_client.delete(f"/api/v1/customers/{cust_id}/")
    assert del_blocked.status_code == status.HTTP_409_CONFLICT
    assert del_blocked.json()["code"] == "PROP-DEL-02-ACTIVE-VEH"

    del_veh = employee_api_client.delete(f"/api/v1/vehicles/{veh['id']}/")
    assert del_veh.status_code == status.HTTP_200_OK
    assert del_veh.json()["code"] == "MSG-4.3.1-M01"

    del_ok = employee_api_client.delete(f"/api/v1/customers/{cust_id}/")
    assert del_ok.status_code == status.HTTP_200_OK
    assert del_ok.json()["code"] == "MSG-4.4.5-M01"
    assert del_ok.json()["message"] == "Xóa thành công"

    cust_obj.refresh_from_db()
    assert cust_obj.deleted_at is not None
    assert (
        employee_api_client.get(f"/api/v1/customers/{cust_id}/").status_code
        == status.HTTP_404_NOT_FOUND
    )
    assert (
        employee_api_client.get(f"/api/v1/customers/?code={cust_code}").json()["count"]
        == 0
    )


def test_staff_lifecycle_and_del01_self_delete_flow(
    manager_account: Account,
    manager_api_client: APIClient,
) -> None:
    """Verify tasks 4.3.1-4.3.4 and non-vacuous DEL-01 self-deletion guard."""
    pos_res = manager_api_client.get("/api/v1/positions/")
    assert pos_res.status_code == status.HTTP_200_OK
    staff_pos = _lookup_by_code(pos_res.json(), "NVVH")

    emp_res = manager_api_client.post(
        "/api/v1/employees/",
        {
            "full_name": "Trần Thị Mai Lan",
            "email": "mailan_flow@smartpark.vn",
            "phone": "0912999888",
            "position_id": staff_pos["id"],
            "password": "SmartPark@2026",
            "address": "123 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
            "status": "ACTIVE",
        },
        format="json",
    )
    assert emp_res.status_code == status.HTTP_201_CREATED, emp_res.json()
    emp_data = emp_res.json()
    emp_id = emp_data["id"]
    emp_code = emp_data["code"]
    row_ver = emp_data["row_version"]

    list_res = manager_api_client.get(f"/api/v1/employees/?q={emp_code}")
    assert list_res.status_code == status.HTTP_200_OK
    assert list_res.json()["count"] == 1
    assert list_res.json()["results"][0]["id"] == emp_id

    patch_res = manager_api_client.patch(
        f"/api/v1/employees/{emp_id}/",
        {"status": "INACTIVE", "row_version": row_ver},
        format="json",
    )
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["status"] == "INACTIVE"
    assert patch_res.json()["row_version"] == row_ver + 1

    del_emp = manager_api_client.delete(f"/api/v1/employees/{emp_id}/")
    assert del_emp.status_code == status.HTTP_200_OK
    assert del_emp.json()["code"] == "MSG-4.3.4-M01"
    assert del_emp.json()["message"] == "Xóa thành công"
    assert Employee.all_objects.get(id=emp_id).deleted_at is not None
    assert (
        manager_api_client.get(f"/api/v1/employees/?q={emp_code}").json()["count"] == 0
    )

    self_emp = Employee.objects.filter(
        account=manager_account, deleted_at__isnull=True
    ).first()
    assert self_emp is not None, "manager_account must have an active Employee row"
    del_self = manager_api_client.delete(f"/api/v1/employees/{self_emp.id}/")
    assert del_self.status_code == status.HTTP_409_CONFLICT
    assert del_self.json()["code"] == "PROP-DEL-01-SELF-EMP"
    self_emp.refresh_from_db()
    assert self_emp.deleted_at is None
    assert Employee.all_objects.get(id=self_emp.id).deleted_at is None


def test_role_gates_employee_manager_customer(
    manager_api_client: APIClient,
    employee_api_client: APIClient,
    customer_api_client: APIClient,
) -> None:
    """Verify RBAC gates: CUSTOMER->403, EMPLOYEE->customer/vehicle only, MANAGER->all."""
    for url in (
        "/api/v1/positions/",
        "/api/v1/employees/",
        "/api/v1/customers/",
        "/api/v1/vehicles/",
        "/api/v1/vehicles/summary/",
        "/api/v1/vehicle-types/",
    ):
        cust_res = customer_api_client.get(url)
        assert cust_res.status_code == status.HTTP_403_FORBIDDEN, url
        assert cust_res.json()["code"] == "MSG-4.2-M01"

    for url in (
        "/api/v1/positions/",
        "/api/v1/employees/",
        "/api/v1/employees/summary/",
    ):
        emp_forbidden = employee_api_client.get(url)
        assert emp_forbidden.status_code == status.HTTP_403_FORBIDDEN, url
        assert emp_forbidden.json()["code"] == "MSG-4.2-M01"

    for url in (
        "/api/v1/customers/",
        "/api/v1/vehicles/",
        "/api/v1/vehicles/summary/",
        "/api/v1/vehicle-types/",
    ):
        assert employee_api_client.get(url).status_code == status.HTTP_200_OK, url
        assert manager_api_client.get(url).status_code == status.HTTP_200_OK, url

    for url in ("/api/v1/positions/", "/api/v1/employees/"):
        assert manager_api_client.get(url).status_code == status.HTTP_200_OK, url


def _assert_forbidden(res: Any) -> None:
    assert res.status_code == status.HTTP_403_FORBIDDEN, res.json()
    assert res.json()["code"] == "MSG-4.2-M01"


def test_role_gates_customer_write_403(
    employee_api_client: APIClient,
    customer_api_client: APIClient,
) -> None:
    """Verify CUSTOMER gets 403 MSG-4.2-M01 on POST/PATCH/DELETE of customer & vehicle."""
    cust = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "Khách RBAC Write",
            "phone": "0987666111",
            "identity_card_number": "048202644111",
        },
        format="json",
    ).json()
    car_type = _lookup_by_code(
        employee_api_client.get("/api/v1/vehicle-types/").json(), "CAR"
    )
    veh = _create_vehicle(
        employee_api_client, cust["id"], car_type["id"], "51K-666.11", "Vios E"
    )
    cust_cnt, veh_cnt = Customer.all_objects.count(), Vehicle.all_objects.count()

    for method, url, body in (
        (
            "post",
            "/api/v1/customers/",
            {
                "full_name": "Blocked Cust",
                "phone": "0987666112",
                "identity_card_number": "048202644112",
            },
        ),
        (
            "post",
            "/api/v1/vehicles/",
            {
                "license_plate": "51K-666.12",
                "model_name": "Accent",
                "vehicle_type_id": car_type["id"],
                "customer_id": cust["id"],
            },
        ),
        (
            "patch",
            f"/api/v1/customers/{cust['id']}/",
            {"row_version": cust["row_version"], "address": "Đổi trái phép"},
        ),
        ("delete", f"/api/v1/customers/{cust['id']}/", None),
        (
            "patch",
            f"/api/v1/vehicles/{veh['id']}/",
            {"row_version": veh["row_version"], "color": "Đen"},
        ),
        ("delete", f"/api/v1/vehicles/{veh['id']}/", None),
    ):
        _assert_forbidden(
            getattr(customer_api_client, method)(url, body, format="json")
        )

    assert Customer.all_objects.count() == cust_cnt
    assert Vehicle.all_objects.count() == veh_cnt
    cust_obj = Customer.objects.get(id=cust["id"])
    veh_obj = Vehicle.objects.get(id=veh["id"])
    assert cust_obj.row_version == cust["row_version"] and cust_obj.deleted_at is None
    assert veh_obj.row_version == veh["row_version"] and veh_obj.deleted_at is None


def test_role_gates_employee_write_403_db_unchanged(
    manager_api_client: APIClient,
    employee_api_client: APIClient,
) -> None:
    """Verify EMPLOYEE gets 403 MSG-4.2-M01 on employee POST/PATCH/DELETE, DB unchanged."""
    nvvh = _lookup_by_code(manager_api_client.get("/api/v1/positions/").json(), "NVVH")
    emp = manager_api_client.post(
        "/api/v1/employees/",
        {
            "full_name": "Nhân Viên RBAC Target",
            "email": "emp_rbac_target@smartpark.vn",
            "phone": "0912666111",
            "position_id": nvvh["id"],
            "password": "SmartPark@2026",
            "status": "ACTIVE",
        },
        format="json",
    ).json()
    emp_cnt, acc_cnt = Employee.all_objects.count(), Account.all_objects.count()
    emp_obj = Employee.objects.get(id=emp["id"])

    _assert_forbidden(
        employee_api_client.post(
            "/api/v1/employees/",
            {
                "full_name": "Blocked Emp",
                "email": "blocked_emp@smartpark.vn",
                "phone": "0912666112",
                "position_id": nvvh["id"],
                "password": "SmartPark@2026",
            },
            format="json",
        )
    )
    assert Employee.all_objects.count() == emp_cnt
    assert Account.all_objects.count() == acc_cnt

    _assert_forbidden(
        employee_api_client.patch(
            f"/api/v1/employees/{emp['id']}/",
            {"row_version": emp["row_version"], "full_name": "Đổi trái phép"},
            format="json",
        )
    )
    emp_obj.refresh_from_db()
    assert emp_obj.full_name == "Nhân Viên RBAC Target"
    assert emp_obj.row_version == emp["row_version"] and emp_obj.deleted_at is None

    _assert_forbidden(employee_api_client.delete(f"/api/v1/employees/{emp['id']}/"))
    emp_obj.refresh_from_db()
    assert emp_obj.deleted_at is None and emp_obj.row_version == emp["row_version"]
    assert emp_obj.account is not None and emp_obj.account.is_active is True


def test_role_gates_anonymous_401_across_areas() -> None:
    """Verify unauthenticated caller gets 401 MSG-4.1-M02 on read & write of 3 areas."""
    anon = APIClient()
    cust_cnt = Customer.all_objects.count()
    veh_cnt = Vehicle.all_objects.count()
    emp_cnt = Employee.all_objects.count()

    for url in ("/api/v1/customers/", "/api/v1/vehicles/", "/api/v1/employees/"):
        read_res = anon.get(url)
        assert read_res.status_code == status.HTTP_401_UNAUTHORIZED, url
        assert read_res.json()["code"] == "MSG-4.1-M02"

        write_res = anon.post(url, {}, format="json")
        assert write_res.status_code == status.HTTP_401_UNAUTHORIZED, url
        assert write_res.json()["code"] == "MSG-4.1-M02"

    assert Customer.all_objects.count() == cust_cnt
    assert Vehicle.all_objects.count() == veh_cnt
    assert Employee.all_objects.count() == emp_cnt


def test_negative_duplicate_plate_and_multifield_validation(
    employee_api_client: APIClient,
) -> None:
    """Verify F8(a) duplicate plate 409 and F8(b) multi-field customer validation 400."""
    cust = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "Khách Negative Plate",
            "phone": "0987666222",
            "identity_card_number": "048202644222",
        },
        format="json",
    ).json()
    car_type = _lookup_by_code(
        employee_api_client.get("/api/v1/vehicle-types/").json(), "CAR"
    )
    _create_vehicle(
        employee_api_client, cust["id"], car_type["id"], "51K-654.32", "Mazda 3"
    )

    veh_cnt = Vehicle.all_objects.count()
    dup_plate_res = employee_api_client.post(
        "/api/v1/vehicles/",
        {
            "license_plate": "51K-654.32",
            "model_name": "Mazda CX-5",
            "vehicle_type_id": car_type["id"],
            "customer_id": cust["id"],
        },
        format="json",
    )
    assert dup_plate_res.status_code == status.HTTP_409_CONFLICT
    assert dup_plate_res.json()["code"] == "MSG-4.3.1-M05"
    assert Vehicle.all_objects.count() == veh_cnt

    cust_cnt = Customer.all_objects.count()
    invalid_res = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "   ",
            "identity_card_number": "abc",
            "phone": "123",
            "email": "not-an-email",
            "gender": "Khác",
            "date_of_birth": "2099-01-01",
        },
        format="json",
    )
    assert invalid_res.status_code == status.HTTP_400_BAD_REQUEST
    invalid_body = invalid_res.json()
    assert invalid_body["code"] == "PROP-GEN-P01"
    expected_fields = {
        "full_name",
        "identity_card_number",
        "phone",
        "email",
        "gender",
        "date_of_birth",
    }
    assert expected_fields.issubset(invalid_body["details"].keys())
    assert Customer.all_objects.count() == cust_cnt


def test_negative_duplicate_unique_values_customer_and_employee(
    employee_api_client: APIClient,
    manager_api_client: APIClient,
) -> None:
    """Verify F8(c) duplicate CCCD/phone/email on Customer and email on Employee -> 409."""
    base_cust = employee_api_client.post(
        "/api/v1/customers/",
        {
            "full_name": "Khách Gốc Unique",
            "identity_card_number": "048202644333",
            "phone": "0987666333",
            "email": "dup_cust_flow@smartpark.vn",
        },
        format="json",
    )
    assert base_cust.status_code == status.HTTP_201_CREATED
    cust_cnt = Customer.all_objects.count()

    for payload in (
        {
            "full_name": "Trùng CCCD",
            "identity_card_number": "048202644333",
            "phone": "0987666334",
            "email": "other1_flow@smartpark.vn",
        },
        {
            "full_name": "Trùng SĐT",
            "identity_card_number": "048202644334",
            "phone": "0987666333",
            "email": "other2_flow@smartpark.vn",
        },
        {
            "full_name": "Trùng Email",
            "identity_card_number": "048202644335",
            "phone": "0987666335",
            "email": "DUP_CUST_FLOW@SMARTPARK.VN",
        },
    ):
        res = employee_api_client.post("/api/v1/customers/", payload, format="json")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "MSG-4.3.1-M05"
        assert "048202644333" not in str(res.json())
        assert Customer.all_objects.count() == cust_cnt

    nvvh = _lookup_by_code(manager_api_client.get("/api/v1/positions/").json(), "NVVH")
    base_emp = manager_api_client.post(
        "/api/v1/employees/",
        {
            "full_name": "Nhân Viên Gốc Unique",
            "email": "dup_emp_flow@smartpark.vn",
            "phone": "0912666333",
            "position_id": nvvh["id"],
            "password": "SmartPark@2026",
        },
        format="json",
    )
    assert base_emp.status_code == status.HTTP_201_CREATED
    emp_cnt, acc_cnt = Employee.all_objects.count(), Account.all_objects.count()

    dup_emp = manager_api_client.post(
        "/api/v1/employees/",
        {
            "full_name": "Nhân Viên Trùng Email",
            "email": "dup_emp_flow@smartpark.vn",
            "phone": "0912666334",
            "position_id": nvvh["id"],
            "password": "SmartPark@2026",
        },
        format="json",
    )
    assert dup_emp.status_code == status.HTTP_409_CONFLICT
    assert dup_emp.json()["code"] == "MSG-4.3.1-M05"
    assert Employee.all_objects.count() == emp_cnt
    assert Account.all_objects.count() == acc_cnt
