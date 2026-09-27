import uuid

from django.db import models
from django.conf import settings


class Beneficiary(models.Model):
    """
    Modèle représentant un bénéficiaire.
    Contient uniquement les informations personnelles.
    """

    class Sexe(models.TextChoices):
        M = "M", "Masculin"
        F = "F", "Féminin"
        AUTRE = "AUTRE", "Autre"

    class SyncStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SYNCED = "SYNCED", "Synchronisé"
        DUPLICATE = "DUPLICATE", "Doublon"
        FAILED = "FAILED", "Échec"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    campagne = models.ForeignKey(
        "campaigns.Campaign",
        on_delete=models.CASCADE,
        related_name="beneficiaries",
    )

    zone = models.ForeignKey(
        "zones.Zone",
        on_delete=models.CASCADE,
        related_name="beneficiaries",
    )

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="beneficiaries",
    )

    nom = models.CharField(max_length=100)

    prenom = models.CharField(max_length=100)

    telephone = models.CharField(max_length=20)

    sexe = models.CharField(
        max_length=10,
        choices=Sexe.choices,
    )

    date_naissance = models.DateField()

    latitude = models.DecimalField(max_digits=10, decimal_places=7)

    longitude = models.DecimalField(max_digits=10, decimal_places=7)

    local_id = models.UUIDField(
        help_text="ID local pour synchronisation hors ligne",
        db_index=True,
    )

    device_id = models.CharField(
        max_length=100,
        help_text="Identifiant du dispositif de collecte",
    )

    score_vulnerabilite = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Score de vulnérabilité calculé automatiquement",
    )

    sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        default=SyncStatus.SYNCED,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_beneficiaries",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.prenom} {self.nom} ({self.telephone})"

    class Meta:
        verbose_name = "Bénéficiaire"
        verbose_name_plural = "Bénéficiaires"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["campagne", "telephone"]),
            models.Index(fields=["local_id", "device_id"]),
        ]


class FormResponse(models.Model):
    """
    Modèle représentant une réponse à une question de formulaire.
    Stockage typé selon le type de question.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="responses",
    )

    formulaire = models.ForeignKey(
        "forms.Formulaire",
        on_delete=models.CASCADE,
        related_name="responses",
    )

    question = models.ForeignKey(
        "forms.FormField",
        on_delete=models.CASCADE,
        related_name="responses",
    )

    value_text = models.TextField(blank=True, null=True)
    value_number = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    value_boolean = models.BooleanField(blank=True, null=True)
    value_date = models.DateField(blank=True, null=True)
    value_json = models.JSONField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Réponse à {self.question.label} pour {self.beneficiary}"

    class Meta:
        verbose_name = "Réponse formulaire"
        verbose_name_plural = "Réponses formulaires"
        ordering = ["created_at"]
        unique_together = ["beneficiary", "question"]