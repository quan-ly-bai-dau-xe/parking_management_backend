"""
Parking serializers module exports.
"""

from apps.parking.serializers.gates import ParkingGateSerializer
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
)

__all__ = [
    "ActiveTicketSummarySerializer",
    "BoundingBoxSerializer",
    "CheckInRequestSerializer",
    "CheckInResponseSerializer",
    "CheckOutRequestSerializer",
    "CheckOutResponseSerializer",
    "CustomerDetailSerializer",
    "OpenSessionSummarySerializer",
    "ParkingGateSerializer",
    "ParkingPositionSerializer",
    "PaymentSummarySerializer",
    "PlateCandidateSerializer",
    "PlateScanRequestSerializer",
    "PlateScanResponseSerializer",
    "SessionDetailSerializer",
    "SessionListItemSerializer",
    "VehicleDetailSerializer",
    "VehicleLookupResponseSerializer",
]
