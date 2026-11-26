"""
Parking serializers module exports.
"""

from apps.parking.serializers.gates import (
    GateAutoEventSerializer,
    ParkingGateSerializer,
)
from apps.parking.serializers.lookup import (
    ActiveTicketSummarySerializer,
    CustomerDetailSerializer,
    OpenSessionSummarySerializer,
    ParkingPositionSerializer,
    VehicleDetailSerializer,
    VehicleLookupResponseSerializer,
)
from apps.parking.serializers.scans import (
    BoundingBoxSerializer,
    PlateCandidateSerializer,
    PlateScanRequestSerializer,
    PlateScanResponseSerializer,
)
from apps.parking.serializers.sessions import (
    CheckInRequestSerializer,
    CheckInResponseSerializer,
    CheckOutRequestSerializer,
    CheckOutResponseSerializer,
    PaymentSummarySerializer,
    SessionDetailSerializer,
    SessionListItemSerializer,
    SessionUpdateSerializer,
)
from apps.parking.serializers.slots import (
    ParkingSlotSerializer,
    ParkingSlotUpdateSerializer,
)

__all__ = [
    "ActiveTicketSummarySerializer",
    "BoundingBoxSerializer",
    "CheckInRequestSerializer",
    "CheckInResponseSerializer",
    "CheckOutRequestSerializer",
    "CheckOutResponseSerializer",
    "CustomerDetailSerializer",
    "GateAutoEventSerializer",
    "OpenSessionSummarySerializer",
    "ParkingGateSerializer",
    "ParkingPositionSerializer",
    "ParkingSlotSerializer",
    "ParkingSlotUpdateSerializer",
    "PaymentSummarySerializer",
    "PlateCandidateSerializer",
    "PlateScanRequestSerializer",
    "PlateScanResponseSerializer",
    "SessionDetailSerializer",
    "SessionListItemSerializer",
    "SessionUpdateSerializer",
    "VehicleDetailSerializer",
    "VehicleLookupResponseSerializer",
]
