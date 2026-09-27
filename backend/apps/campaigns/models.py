import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone


class Campaign(models.Model):
    """
    Modèle représentant une campagne humanitaire.
    Une campagne appartient à un projet et peut couvrir plusieurs zones.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    projet = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="campaigns",
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="campaigns",
    )

    nom = models.CharField(max_length=200)

    code_campagne = models.CharField(max_length=30, unique=True, blank=True, editable=False)

    description = models.TextField()

    zones = models.ManyToManyField(
        "zones.Zone",
        related_name="campaigns",
        blank=True,
    )

    agents = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CampagneAffectation",
        through_fields=("campagne", "agent"),
        related_name="campagnes_assignees",
        blank=True,
    )

    date_debut = models.DateField()

    date_fin = models.DateField()

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        PLANIFIER = "PLANIFIER", "Planifiée"
        EN_COURS = "EN_COURS", "En cours"
        TERMINE = "TERMINE", "Terminée"
        ANNULEE = "ANNULEE", "Annulée"

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_COURS,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_campaigns",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code_campagne} - {self.nom}"

    def statut_auto(self):
        today = timezone.now().date()
        if self.statut in {self.Statut.ANNULEE, self.Statut.TERMINE}:
            return self.statut
        if self.date_debut and self.date_fin:
            if today < self.date_debut:
                return self.Statut.PLANIFIER
            if today > self.date_fin:
                return self.Statut.TERMINE
        return self.Statut.EN_COURS

    class Meta:
        verbose_name = "Campagne"
        verbose_name_plural = "Campagnes"
        ordering = ["-created_at"]


class CampagneAffectation(models.Model):
    """Affectation d'un agent terrain à une campagne et à une zone."""

    class Statut(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_COURS = "EN_COURS", "En cours"
        TERMINE = "TERMINE", "Terminé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campagne = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name="affectations",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="affectations_campagnes",
    )
    zone = models.CharField(max_length=150)
    objectif_beneficiaires = models.PositiveIntegerField(default=0)
    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.EN_ATTENTE,
    )
    date_affectation = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="affectations_creees",
    )

    class Meta:
        verbose_name = "Affectation de campagne"
        verbose_name_plural = "Affectations de campagnes"
        constraints = [
            models.UniqueConstraint(
                fields=["campagne", "agent", "zone"],
                name="unique_campagne_agent_zone",
            ),
        ]

    def __str__(self):
        return f"{self.agent} - {self.campagne}"