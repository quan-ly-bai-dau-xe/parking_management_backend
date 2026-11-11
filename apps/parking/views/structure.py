"""
Parking Lot Structure View.
Returns hierarchical parking layout: Floor -> Zones -> Slots.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsEmployeeOrManager
from apps.parking.models import ParkingFloor


class ParkingStructureView(APIView):
    """
    Lấy sơ đồ bãi đỗ xe phân cấp: Tầng -> Khu vực -> Ô đỗ.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def get(self, request: Request) -> Response:
        floors = (
            ParkingFloor.objects.filter(deleted_at__isnull=True)
            .prefetch_related(
                "zones",
                "zones__slots",
            )
            .order_by("display_order", "id")
        )

        data = []
        for floor in floors:
            floor_dict = {
                "id": floor.id,
                "code": floor.code,
                "name": floor.name,
                "total_slots": floor.total_slots,
                "zones": [],
            }
            for zone in floor.zones.filter(deleted_at__isnull=True).order_by("code"):
                zone_dict = {
                    "id": zone.id,
                    "code": zone.code,
                    "name": zone.name,
                    "total_slots": zone.total_slots,
                    "slots": [],
                }
                for slot in zone.slots.filter(deleted_at__isnull=True).order_by(
                    "slot_number"
                ):
                    zone_dict["slots"].append(
                        {
                            "id": slot.id,
                            "code": slot.code,
                            "slot_number": slot.slot_number,
                            "status": slot.status,
                            "status_display": slot.get_status_display()
                            if hasattr(slot, "get_status_display")
                            else slot.status,
                            "is_occupied": slot.is_occupied,
                            "row": slot.code[0] if slot.code else "A",
                            "label": f"{zone.code}-{slot.slot_number:02d}",
                        }
                    )
                floor_dict["zones"].append(zone_dict)
            data.append(floor_dict)

        return Response(data, status=status.HTTP_200_OK)
