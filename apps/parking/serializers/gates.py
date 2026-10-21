"""
Gate serializers for parking app.
"""

from rest_framework import serializers

from apps.parking.models import ParkingGate


class ParkingGateSerializer(serializers.ModelSerializer):
    """Serializer cho cổng kiểm soát barrier xe vào/ra."""

    class Meta:
        model = ParkingGate
        fields = [
            "id",
            "lot_id",
            "code",
            "name",
            "direction",
            "camera_status",
            "is_auto_scan",
            "is_active",
        ]
