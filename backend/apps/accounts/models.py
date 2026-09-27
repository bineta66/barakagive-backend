from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
import uuid

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):

    class Role(models.TextChoices):
        SUPER_ADMIN = "SUPER_ADMIN", "Super Admin"
        GERANT = "GERANT", "Gérant"
        CHEF_PROJET = "CHEF_PROJET", "Chef de projet"
        FINANCE = "FINANCE", "Responsable Finance"
        AGENT = "AGENT", "Agent Terrain"

    class Status(models.TextChoices):
        EN_ATTENTE = "EN_ATTENTE", "En attente"
        EN_ATTENTE_ACTIVATION = "EN_ATTENTE_ACTIVATION", "En attente d'activation"
        INVITED = "INVITED", "Invitation envoyée"
        ACTIVE = "ACTIVE", "Actif"
        SUSPENDED = "SUSPENDED", "Suspendu"

    # Informations personnelles
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)

    # Rôle et statut
    role = models.CharField(
        max_length=30,
        choices=Role.choices
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.EN_ATTENTE
    )

    # ONG d'appartenance
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True
    )

    # Date de la dernière invitation (activation)
    last_invited_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Django
    is_active = models.BooleanField(default=False)
    must_change_password = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    @property
    def can_login(self):
        """
        L'utilisateur peut se connecter uniquement
        si son compte est ACTIVE.
        """
        return (
            self.status == self.Status.ACTIVE
            and self.is_active
        )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __str__(self):
        return self.full_name


class ActivationToken(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="activation_tokens",
    )
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"ActivationToken {self.id} for {self.user.email}"
