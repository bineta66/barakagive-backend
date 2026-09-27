from rest_framework import serializers
from django.contrib.gis.geos import Point

from .models import Zone, Region, Department


class RegionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Region
        fields = ["id", "nom"]


class DepartmentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Department
        fields = "__all__"


class ReverseGeocodeSerializer(serializers.Serializer):

    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)

    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)


class ReverseGeocodeResponseSerializer(serializers.Serializer):

    region = serializers.CharField()

    departement = serializers.CharField()

    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)

    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)


class ZoneSerializer(serializers.ModelSerializer):

    class Meta:
        model = Zone
        fields = [
            "id",
            "nom",
            "region",
            "departement",
            "latitude",
            "longitude",
            "location",
            "rayon",
            "statut",
            "organization",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "location",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def update(self, instance, validated_data):
        latitude = validated_data.get("latitude", instance.latitude)
        longitude = validated_data.get("longitude", instance.longitude)
        validated_data["location"] = Point(float(longitude), float(latitude), srid=4326)
        return super().update(instance, validated_data)


class ZoneCreateSerializer(serializers.ModelSerializer):
    region = serializers.CharField(required=False, max_length=100)
    departement = serializers.CharField(required=False, max_length=100)

    class Meta:
        model = Zone
        fields = [
            "nom",
            "region",
            "departement",
            "latitude",
            "longitude",
            "rayon",
            "statut",
        ]

    def create(self, validated_data):
        from django.contrib.gis.geos import Point
        lat = float(validated_data["latitude"])
        lng = float(validated_data["longitude"])
        validated_data["location"] = Point(lng, lat, srid=4326)
        if not validated_data.get("region") or not validated_data.get("departement"):
            dept = Department.objects.filter(geometrie__contains=validated_data["location"]).first()
            if dept:
                validated_data.setdefault("region", dept.region.nom)
                validated_data.setdefault("departement", dept.nom)
            else:
                validated_data.setdefault("region", "Sénégal")
                validated_data.setdefault("departement", "Zone")
        return super().create(validated_data)

    def validate_nom(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Le nom de la zone est obligatoire.")
        return value

    def validate_rayon(self, value):
        if not value or value <= 0:
            raise serializers.ValidationError("Le rayon doit être supérieur à 0.")
        return value

    def validate_latitude(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError("La latitude doit être entre -90 et 90.")
        return value

    def validate_longitude(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError("La longitude doit être entre -180 et 180.")
        return value
