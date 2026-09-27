import uuid

from django.contrib.gis.db import models
from django.conf import settings


class Region(models.Model):

    nom = models.CharField(max_length=100, unique=True)

    geometrie = models.PolygonField(srid=4326)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nom

    class Meta:
        verbose_name = "Région"
        verbose_name_plural = "Régions"


class Department(models.Model):

    nom = models.CharField(max_length=100)

    region = models.ForeignKey(
        Region,
        on_delete=models.CASCADE,
        related_name="departements",
    )

    geometrie = models.PolygonField(srid=4326)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nom} ({self.region.nom})"

    class Meta:
        verbose_name = "Département"
        verbose_name_plural = "Départements"
        unique_together = ["nom", "region"]


class Zone(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    nom = models.CharField(max_length=200)

    region = models.CharField(max_length=100)

    departement = models.CharField(max_length=100)

    latitude = models.DecimalField(max_digits=10, decimal_places=7)

    longitude = models.DecimalField(max_digits=10, decimal_places=7)

    location = models.PointField(srid=4326, geography=True)

    rayon = models.PositiveIntegerField()

    statut = models.BooleanField(default=True)

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="zones",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_zones",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} ({self.region} - {self.departement})"

    class Meta:
        verbose_name = "Zone"
        verbose_name_plural = "Zones"
