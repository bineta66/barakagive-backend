from django.db import models
from django.utils import timezone


class Organization(models.Model):

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        ACTIVE = "ACTIVE", "Active"
        REJETEE = "REJETEE", "Rejetée"
        SUSPENDED = "SUSPENDED", "Suspendue"

    name = models.CharField(max_length=200)
    acronym = models.CharField(max_length=50, blank=True)

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)

    address = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    region = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="Sénégal")

    intervention_domain = models.CharField(max_length=150)

    logo = models.ImageField(
        upload_to="organizations/logos/",
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EN_ATTENTE
    )

    is_active = models.BooleanField(default=False)

    # Documents d'inscription
    document_receipt = models.FileField(upload_to="organizations/documents/receipts/", blank=True, null=True)
    document_ninea = models.FileField(upload_to="organizations/documents/ninea/", blank=True, null=True)
    document_statutes = models.FileField(upload_to="organizations/documents/statutes/", blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Subscription(models.Model):

    class Status(models.TextChoices):
        TRIAL = "TRIAL", "Essai gratuit"
        ACTIVE = "ACTIVE", "Active"
        EXPIRE = "EXPIRE", "Expirée"

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="subscription")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIAL)
    trial_start = models.DateField(null=True, blank=True)
    trial_end = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Subscription - {self.organization.name}"
