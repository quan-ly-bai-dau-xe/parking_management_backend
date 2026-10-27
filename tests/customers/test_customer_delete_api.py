"""
Test suite for DELETE /api/v1/customers/{id}/ (Customer Soft-Delete API).
Covers:
- DEL-02 soft delete: deleted_at timestamp and deleted_by actor FK assignment.
- 404 Not Found when customer does not exist or was already deleted (PROP-4.4.5-P01).
- Guard 1: Customer has vehicle parked in lot (uncompleted entry log) -> 409 PROP-4.4.5-P02.
- Guard 2: Customer has active, unexpired ticket -> 409 PROP-4.4.5-P03.
- Guard 3: Customer has active registered vehicles -> 409 PROP-DEL-02-ACTIVE-VEH.
- Successful soft deletion returns 200 OK with MSG-4.4.5-M01.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def test_customer_delete_success(employee_client: APIClient, auth_employee: Account):
    """
    Verify successful soft deletion for a customer with no parked cars, no active tickets,
    and no active registered vehicles. Returns 200 MSG-4.4.5-M01.
    """
    cust = Customer.objects.create(
        code="KHDEL01",
        full_name="Khách Hàng Xóa Thành Công",
        identity_card_number="079090001111",
        phone="0901112222",
    )

    url = f"/api/v1/customers/{cust.id}/"
    response = employee_client.delete(url)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["code"] == "MSG-4.4.5-M01"
    assert "Xóa thành công" in data["message"]

    # Verify soft delete flags in DB
    cust.refresh_from_db()
    assert cust.deleted_at is not None
    assert cust.deleted_by_id == auth_employee.id

    # Verify not accessible via GET detail
    res_detail = employee_client.get(url)
    assert res_detail.status_code == status.HTTP_404_NOT_FOUND


def test_customer_delete_not_found(employee_client: APIClient):
    """Verify deleting a non-existent customer returns 404 PROP-4.4.5-P01."""
    url = "/api/v1/customers/9999999/"
    response = employee_client.delete(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND

    data = response.json()
    assert data["code"] == "PROP-4.4.5-P01"
    assert "Khách hàng không tồn tại" in data["message"]


def test_customer_delete_already_deleted_returns_404(employee_client: APIClient):
    """Verify deleting an already soft-deleted customer returns 404 PROP-4.4.5-P01."""
    cust = Customer.objects.create(
        code="KHDEL02",
        full_name="Khách Hàng Đã Xóa",
        identity_card_number="079090002222",
        phone="0902223333",
    )
    # Perform first soft-delete
    url = f"/api/v1/customers/{cust.id}/"
    res1 = employee_client.delete(url)
    assert res1.status_code == status.HTTP_200_OK

    # Second soft-delete attempt must return 404
    res2 = employee_client.delete(url)
    assert res2.status_code == status.HTTP_404_NOT_FOUND
    assert res2.json()["code"] == "PROP-4.4.5-P01"


def test_customer_delete_guard_active_vehicles(
    employee_client: APIClient, car_type: VehicleType
):
    """
    DEL-02 Guard 3:
    Customer with active registered vehicles cannot be deleted.
    Database trigger raises check_violation -> translated to 409 PROP-DEL-02-ACTIVE-VEH.
    """
    cust = Customer.objects.create(
        code="KHDEL03",
        full_name="Khách Hàng Có Xe Hoạt Động",
        identity_card_number="079090003333",
        phone="0903334444",
    )
    # Register an active vehicle to this customer
    Vehicle.objects.create(
        code="XE-DEL03",
        license_plate="51K-771.01",
        model_name="Vios",
        vehicle_type=car_type,
        customer=cust,
    )

    url = f"/api/v1/customers/{cust.id}/"
    response = employee_client.delete(url)
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "PROP-DEL-02-ACTIVE-VEH"
    assert "phương tiện hoạt động" in data["message"]


def test_customer_delete_guard_active_ticket(
    employee_client: APIClient, car_type: VehicleType
):
    """
    DEL-02 Guard 2:
    Customer with active, unexpired ticket cannot be deleted.
    Database trigger raises check_violation -> translated to 409 PROP-4.4.5-P03.
    """
    cust = Customer.objects.create(
        code="KHDEL04",
        full_name="Khách Hàng Có Vé Còn Hạn",
        identity_card_number="079090004444",
        phone="0904445555",
    )
    veh = Vehicle.objects.create(
        code="XE-DEL04",
        license_plate="51K-771.02",
        model_name="Vios",
        vehicle_type=car_type,
        customer=cust,
    )
    # Create an active subscription ticket on an available slot
    from apps.parking.models import ParkingSlot

    now = timezone.now()
    ticket = Ticket.objects.filter(deleted_at__isnull=True).first()
    assert ticket is not None, "Need a seed ticket template for foreign keys"

    free_slot = (
        ParkingSlot.objects.filter(deleted_at__isnull=True)
        .exclude(
            tickets__status__in=["ACTIVE", "RENEWING"],
            tickets__deleted_at__isnull=True,
            tickets__effective_to__gt=now,
        )
        .first()
    )
    assert free_slot is not None, "Need an available parking slot"

    Ticket.objects.create(
        code="TKT-DEL04",
        customer=cust,
        vehicle=veh,
        slot=free_slot,
        ticket_type=ticket.ticket_type,
        price=ticket.price or 500000,
        effective_from=now - timedelta(days=5),
        effective_to=now + timedelta(days=25),
        status="ACTIVE",
    )

    url = f"/api/v1/customers/{cust.id}/"
    response = employee_client.delete(url)
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "PROP-4.4.5-P03"
    assert "vé xe còn hiệu lực" in data["message"]


def test_customer_delete_guard_parked_vehicle_in_lot(
    employee_client: APIClient, car_type: VehicleType
):
    """
    DEL-02 Guard 1:
    Customer whose vehicle is currently parked inside lot (exit_time IS NULL) cannot be deleted.
    Database trigger raises check_violation -> translated to 409 PROP-4.4.5-P02.
    """
    cust = Customer.objects.create(
        code="KHDEL05",
        full_name="Khách Hàng Đang Có Xe Trong Bãi",
        identity_card_number="079090005555",
        phone="0905556666",
    )
    veh = Vehicle.objects.create(
        code="XE-DEL05",
        license_plate="51K-771.03",
        model_name="Vios",
        vehicle_type=car_type,
        customer=cust,
    )

    # Insert entry log directly into vehicle_entry_exit_log with exit_time IS NULL
    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM parking_gate LIMIT 1;")
        gate_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO vehicle_entry_exit_log
                (session_code, vehicle_id, license_plate, entry_time, entry_gate_id, exit_time)
            VALUES
                (%s, %s, %s, %s, %s, NULL);
            """,
            ["SES-DEL05", veh.id, veh.license_plate, timezone.now(), gate_id],
        )

    url = f"/api/v1/customers/{cust.id}/"
    response = employee_client.delete(url)
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "PROP-4.4.5-P02"
    assert "trong bãi" in data["message"]
