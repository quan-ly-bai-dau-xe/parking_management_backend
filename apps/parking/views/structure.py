"""
Parking Lot Structure View.
Returns hierarchical parking layout: Floor -> Zones -> Slots.
"""

from __future__ import annotations

from typing import Any

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
            .order_by("sort_order", "id")
        )

        data: list[dict[str, Any]] = []
        for floor in floors:
            floor_slot_count = 0
            floor_dict: dict[str, Any] = {
                "id": floor.id,
                "code": floor.code,
                "name": floor.name,
                "total_slots": 0,
                "zones": [],
            }
            for zone in floor.zones.filter(deleted_at__isnull=True).order_by("code"):
                zone_slots = list(
                    zone.slots.filter(deleted_at__isnull=True).order_by("code", "id")
                )
                zone_slot_count = len(zone_slots)
                floor_slot_count += zone_slot_count

                zone_dict: dict[str, Any] = {
                    "id": zone.id,
                    "code": zone.code,
                    "name": zone.name,
                    "total_slots": zone_slot_count,
                    "slots": [],
                }
                for idx, slot in enumerate(zone_slots, start=1):
                    digits = "".join(filter(str.isdigit, str(slot.code)))
                    slot_num = int(digits) if digits else idx
                    zone_dict["slots"].append(
                        {
                            "id": slot.id,
                            "code": slot.code,
                            "slot_number": slot_num,
                            "status": slot.status,
                            "status_display": slot.get_status_display()
                            if hasattr(slot, "get_status_display")
                            else slot.status,
                            "is_occupied": slot.status == "OCCUPIED",
                            "row": slot.code[0] if slot.code else "A",
                            "label": f"{zone.code}-{slot.code}",
                        }
                    )
                floor_dict["zones"].append(zone_dict)

            floor_dict["total_slots"] = floor_slot_count
            data.append(floor_dict)

        return Response(data, status=status.HTTP_200_OK)
