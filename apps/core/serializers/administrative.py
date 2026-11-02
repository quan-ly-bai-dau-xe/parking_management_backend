"""
Serializers for administrative boundary units and query parameters.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)


class AdministrativeProvinceSerializer(serializers.ModelSerializer):
    """Serializer for administrative province dropdown."""

    class Meta:
        model = AdministrativeProvince
        fields = ["id", "code", "name"]


class AdministrativeDistrictSerializer(serializers.ModelSerializer):
    """Serializer for administrative district dropdown."""

    class Meta:
        model = AdministrativeDistrict
        fields = ["id", "code", "name"]


class AdministrativeWardSerializer(serializers.ModelSerializer):
    """Serializer for administrative ward dropdown."""

    class Meta:
        model = AdministrativeWard
        fields = ["id", "code", "name"]


class DistrictFilterQuerySerializer(serializers.Serializer):
    """Validate query parameters for filtering districts by province."""

    province_id = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="ID của Tỉnh/Thành phố trực thuộc trung ương (bắt buộc, số nguyên dương >= 1)",
    )


class WardFilterQuerySerializer(serializers.Serializer):
    """Validate query parameters for filtering wards by district."""

    district_id = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="ID của Quận/Huyện/Thị xã (bắt buộc, số nguyên dương >= 1)",
    )
