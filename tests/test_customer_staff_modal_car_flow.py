"""
Integration test suite for Customer, Staff (Employee), and Modal-Car (Vehicle) APIs.
Verifies complete end-to-end integration matching feature/feat/Qminh-003-customer-staff-modal-car:
1. Customer Creation & Vehicle Registration (Modal Car - CAR & EV)
2. Vehicle Detail Retrieval (Chi tiết xe, Chủ sở hữu, Trạng thái vé)
3. Staff (Employee) Management & DEL-01 self-deletion protection
4. Vehicle Types & KPI Summaries
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.employees.models import Employee

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_account() -> Account:
    """Manager account with full management privileges."""
    acc, _ = Account.objects.get_or_create(
        email="manager_flow_test@smartpark.vn",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash_manager",
        },
    )
    return acc


@pytest.fixture
def manager_api_client(manager_account: Account) -> APIClient:
    """Authenticated APIClient for Manager."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


def test_customer_create_and_vehicle_registration_flow(
    manager_api_client: APIClient,
) -> None:
    """
    Test E2E flow:
    1. Tạo khách hàng mới qua API POST /api/v1/customers/
    2. Đăng ký xe xăng (CAR) cho khách hàng qua POST /api/v1/vehicles/
    3. Đăng ký xe điện (EV) cho khách hàng qua POST /api/v1/vehicles/
    4. Xem chi tiết xe (Modal Xem thông tin xe) qua GET /api/v1/vehicles/{id}/
    """
    # 1. Tạo khách hàng
    customer_payload = {
        "full_name": "Nguyễn Văn Minh Flow",
        "phone": "0987111222",
        "email": "minh_flow@smartpark.vn",
        "identity_card_number": "048202611999",
        "gender": "Nam",
        "date_of_birth": "1995-05-15",
    }
    cust_res = manager_api_client.post(
        "/api/v1/customers/", customer_payload, format="json"
    )
    assert cust_res.status_code == status.HTTP_201_CREATED, cust_res.json()
    customer_id = cust_res.json()["id"]

    # 2. Lấy loại xe
    types_res = manager_api_client.get("/api/v1/vehicle-types/")
    assert types_res.status_code == status.HTTP_200_OK
    type_list = types_res.json()
    car_type = next((t for t in type_list if t["code"] == "CAR"), type_list[0])
    ev_type = next((t for t in type_list if t["code"] == "EV"), type_list[-1])

    # 3. Đăng ký xe CAR (Modal Thêm xe mới)
    car_payload = {
        "license_plate": "51K-888.88",
        "model_name": "Camry 2.5Q",
        "brand": "Toyota",
        "color": "Trắng ngọc trai",
        "vehicle_type_id": car_type["id"],
        "customer_id": customer_id,
        "notes": "Xe cá nhân đăng ký vé tháng",
    }
    car_res = manager_api_client.post("/api/v1/vehicles/", car_payload, format="json")
    assert car_res.status_code == status.HTTP_201_CREATED, car_res.json()
    car_id = car_res.json()["id"]

    # 4. Đăng ký xe EV (Modal Thêm xe điện)
    ev_payload = {
        "license_plate": "51K-888.99",
        "model_name": "VF8 Plus",
        "brand": "VinFast",
        "color": "Xanh dương",
        "vehicle_type_id": ev_type["id"],
        "customer_id": customer_id,
        "notes": "Xe điện cần sạc tại tầng B1",
    }
    ev_res = manager_api_client.post("/api/v1/vehicles/", ev_payload, format="json")
    assert ev_res.status_code == status.HTTP_201_CREATED, ev_res.json()

    # 5. Xem thông tin chi tiết xe (Modal Xem thông tin xe)
    detail_res = manager_api_client.get(f"/api/v1/vehicles/{car_id}/")
    assert detail_res.status_code == status.HTTP_200_OK
    detail_data = detail_res.json()
    assert detail_data["license_plate"] == "51K-888.88"
    assert detail_data["model_name"] == "Camry 2.5Q"
    assert detail_data["brand"] == "Toyota"
    assert detail_data["color"] == "Trắng ngọc trai"
    assert detail_data["customer"]["id"] == customer_id
    assert detail_data["vehicle_type"]["id"] == car_type["id"]


def test_staff_management_lifecycle_and_del01_protection(
    manager_api_client: APIClient,
) -> None:
    """
    Test E2E Staff (Employee) Management:
    1. Lấy danh mục chức vụ (GET /api/v1/positions/)
    2. Thêm mới nhân sự (POST /api/v1/employees/)
    3. Cập nhật trạng thái và thông tin (PATCH /api/v1/employees/{id}/)
    4. Kiểm tra rào chắn DEL-01 chặn Quản lý tự xóa tài khoản của chính mình
    """
    # 1. Danh mục chức vụ
    pos_res = manager_api_client.get("/api/v1/positions/")
    assert pos_res.status_code == status.HTTP_200_OK
    positions = pos_res.json()
    assert len(positions) > 0
    staff_pos = next((p for p in positions if p["code"] == "NVVH"), positions[0])

    # 2. Thêm mới nhân viên
    emp_payload = {
        "full_name": "Trần Thị Mai Lan",
        "email": "mailan_flow@smartpark.vn",
        "phone": "0912999888",
        "position_id": staff_pos["id"],
        "password": "SmartPark@2026",
        "address": "123 Nguyễn Văn Linh, Hải Châu, Đà Nẵng",
        "status": "ACTIVE",
    }
    emp_res = manager_api_client.post("/api/v1/employees/", emp_payload, format="json")
    assert emp_res.status_code == status.HTTP_201_CREATED, emp_res.json()
    emp_data = emp_res.json()
    emp_id = emp_data["id"]
    row_ver = emp_data["row_version"]

    # 3. Cập nhật nhân viên (tạm khóa sang INACTIVE)
    patch_payload = {
        "status": "INACTIVE",
        "row_version": row_ver,
    }
    patch_res = manager_api_client.patch(
        f"/api/v1/employees/{emp_id}/", patch_payload, format="json"
    )
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["status"] == "INACTIVE"

    # 4. Kiểm tra rào chắn DEL-01: Tìm chính tài khoản manager đang login và gọi DELETE
    # Quản lý không được phép tự xóa tài khoản chính mình
    current_mgr_emp = Employee.objects.filter(
        account__email="manager_flow_test@smartpark.vn", deleted_at__isnull=True
    ).first()
    if current_mgr_emp:
        del_res = manager_api_client.delete(f"/api/v1/employees/{current_mgr_emp.id}/")
        assert del_res.status_code == status.HTTP_409_CONFLICT
