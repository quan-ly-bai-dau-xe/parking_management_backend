"""
Serializers for vehicle types.
"""

from rest_framework import serializers

from apps.vehicles.models import VehicleType


class VehicleTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for VehicleType lookup dropdown (CAR, EV).
    """

    class Meta:
        model = VehicleType
        fields = ["id", "code", "name", "description"]
