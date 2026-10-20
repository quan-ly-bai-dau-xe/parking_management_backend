"""
Gate selectors for parking app.
Read-only queries for parking gates.
"""

from django.db.models import QuerySet

from apps.parking.models import ParkingGate


def get_gates(
    direction: str | None = None, is_active: bool | None = None
) -> QuerySet[ParkingGate]:
    """
    Truy vấn danh sách cổng kiểm soát xe vào/ra (ParkingGate).
    Hỗ trợ lọc theo hướng (IN/OUT) và trạng thái hoạt động (is_active).
    """
    qs = ParkingGate.objects.filter(deleted_at__isnull=True)
    if direction:
        qs = qs.filter(direction=direction.upper())
    if is_active is not None:
        qs = qs.filter(is_active=is_active)
    return qs.order_by("code")


def get_gate_by_id(gate_id: int) -> ParkingGate | None:
    """Truy vấn thông tin chi tiết một cổng theo id."""
    return ParkingGate.objects.filter(id=gate_id, deleted_at__isnull=True).first()
