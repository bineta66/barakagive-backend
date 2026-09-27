import uuid

from django.db import models
from django.conf import settings


class Formulaire(models.Model):
    """
    Modèle représentant un formulaire dynamique pour une campagne.
    Créé par le Chef de projet pour la collecte de données terrain.
    """

    class Statut(models.TextChoices):
        BROUILLON = "BROUILLON", "Brouillon"
        PUBLIE = "PUBLIE", "Publié"
        FERME = "FERME", "Fermé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campagne = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="formulaires",
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="formulaires",
    )

    nom = models.CharField(max_length=200)

    description = models.TextField(blank=True)

    version = models.PositiveIntegerField(default=1)

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.BROUILLON,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_formulaires",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nom} (v{self.version}) - {self.get_statut_display()}"

    class Meta:
        verbose_name = "Formulaire"
        verbose_name_plural = "Formulaires"
        ordering = ["-created_at"]


class FormField(models.Model):
    """
    Modèle représentant une question/champ d'un formulaire.
    Supporte les types : TEXT, PHONE, SELECT, CHECKBOX, YES_NO, GPS, NUMBER, DATE, TEXTAREA
    """

    class TypeChoices(models.TextChoices):
        TEXT = "TEXT", "Texte court"
        PHONE = "PHONE", "Téléphone"
        SELECT = "SELECT", "Liste déroulante"
        CHECKBOX = "CHECKBOX", "Cases à cocher"
        YES_NO = "YES_NO", "Oui/Non"
        GPS = "GPS", "Coordonnées GPS"
        NUMBER = "NUMBER", "Nombre"
        DATE = "DATE", "Date"
        TEXTAREA = "TEXTAREA", "Texte long"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    formulaire = models.ForeignKey(
        Formulaire,
        on_delete=models.CASCADE,
        related_name="fields",
    )

    label = models.CharField(max_length=300)

    type = models.CharField(
        max_length=20,
        choices=TypeChoices.choices,
    )

    obligatoire = models.BooleanField(default=False)

    ordre = models.PositiveIntegerField(default=0)

    placeholder = models.CharField(max_length=500, blank=True, null=True)

    options = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ordre}. {self.label} ({self.get_type_display()})"

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ["ordre", "created_at"]