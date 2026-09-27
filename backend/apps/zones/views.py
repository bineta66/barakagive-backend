from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.gis.geos import Point

from drf_spectacular.utils import extend_schema

from .models import Zone, Region, Department
from .serializers import (
    ZoneSerializer,
    ZoneCreateSerializer,
    RegionSerializer,
    ReverseGeocodeSerializer,
    ReverseGeocodeResponseSerializer,
)


@extend_schema(tags=["Zones"])
class ReverseGeocodeView(APIView):

    @extend_schema(tags=["Zones"])
    def post(self, request):
        serializer = ReverseGeocodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]

        point = Point(longitude, latitude, srid=4326)

        department = Department.objects.filter(
            geometrie__contains=point
        ).first()

        if not department:
            return Response(
                {"detail": "Aucune région trouvée pour ces coordonnées."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response = ReverseGeocodeResponseSerializer({
            "region": department.region.nom,
            "departement": department.nom,
            "latitude": latitude,
            "longitude": longitude,
        })

        return Response(response.data, status=status.HTTP_200_OK)


REGIONS_SENEGAL = [
    "Dakar",
    "Diourbel",
    "Fatick",
    "Kaffrine",
    "Kaolack",
    "Kédougou",
    "Kolda",
    "Louga",
    "Matam",
    "Saint-Louis",
    "Sédhiou",
    "Tambacounda",
    "Thiès",
    "Ziguinchor",
]


@extend_schema(tags=["Zones"])
class ZoneListView(generics.ListCreateAPIView):

    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    queryset = Zone.objects.select_related(
        "organization", "created_by"
    ).all()

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ZoneCreateSerializer
        return ZoneSerializer

    def get_queryset(self):
        user = self.request.user
        if user.organization:
            return self.queryset.filter(organization=user.organization)
        elif user.role in ["GERANT", "SUPER_ADMIN", "FINANCE"]:
            return self.queryset.all()
        return self.queryset.none()

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            organization=self.request.user.organization,
        )


@extend_schema(tags=["Zones"])
class ZoneDetailView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = ZoneSerializer
    permission_classes = [IsAuthenticated]
    lookup_url_kwarg = "id"
    queryset = Zone.objects.select_related(
        "organization", "created_by"
    ).all()

    def get_queryset(self):
        user = self.request.user
        if user.organization:
            return self.queryset.filter(organization=user.organization)
        elif user.role in ["GERANT", "SUPER_ADMIN", "FINANCE"]:
            return self.queryset.all()
        return self.queryset.none()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Zones"])
class RegionListView(generics.ListAPIView):
    """GET /api/regions/ — retourne toutes les régions (id + nom)"""
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        # Auto-seed les 14 régions du Sénégal si la table est vide
        if not Region.objects.exists():
            from django.contrib.gis.geos import Polygon
            poly = Polygon(((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)))
            for nom in REGIONS_SENEGAL:
                Region.objects.get_or_create(nom=nom, defaults={"geometrie": poly})
        return Region.objects.all().order_by("nom")
