"""
Plate scan serializers alias module (H6 contract).
Re-exports from apps.parking.serializers.scans for explicit ownership specification compatibility.
"""

from apps.parking.serializers.scans import (
    BoundingBoxSerializer,
    PlateCandidateSerializer,
    PlateCorrectionItemSerializer,
    PlateScanImageField,
    PlateScanRequestSerializer,
    PlateScanResponseSerializer,
)

__all__ = [
    "BoundingBoxSerializer",
    "PlateCandidateSerializer",
    "PlateCorrectionItemSerializer",
    "PlateScanImageField",
    "PlateScanRequestSerializer",
    "PlateScanResponseSerializer",
]
