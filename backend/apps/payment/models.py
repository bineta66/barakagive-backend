import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone


class Subscription(models.Model):
    """
    Abonnement d'une ONG. Une seule par ONG.
    """

    class Statut(models.TextChoices):
        TRIAL = "TRIAL", "Essai gratuit"
        ACTIVE = "ACTIVE", "Actif"
        EXPIRED = "EXPIRED", "Expiré"
        CANCELLED = "CANCELLED", "Annulé"

    class Plan(models.TextChoices):
        MENSUEL = "MENSUEL", "Mensuel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    ong = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="payment_subscription",
    )

    plan = models.CharField(
        max_length=20,
        choices=Plan.choices,
        default=Plan.MENSUEL,
    )

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.TRIAL,
    )

    prix = models.DecimalField(
        max_digits=10,
        decimal_places=0,
        default=50000,
    )

    trial_days = models.PositiveIntegerField(default=7)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    next_payment_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payment_subscription"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ong.name} - {self.statut}"

    @property
    def days_remaining(self):
        """Jours restants d'essai ou avant prochain paiement."""
        if self.statut == self.Statut.TRIAL and self.trial_end:
            delta = self.trial_end - timezone.now()
            return max(0, delta.days)
        if self.statut == self.Statut.ACTIVE and self.next_payment_date:
            delta = self.next_payment_date - timezone.now().date()
            return max(0, delta.days)
        return 0

    @property
    def is_trial_expired(self):
        """Vérifie si l'essai est expiré."""
        if self.statut == self.Statut.TRIAL and self.trial_end:
            return timezone.now() > self.trial_end
        return False

    def start_trial(self):
        """Démarre l'essai gratuit de 7 jours."""
        self.trial_start = timezone.now()
        self.trial_end = self.trial_start + timezone.timedelta(days=self.trial_days)
        self.statut = self.Statut.TRIAL
        self.is_active = True
        self.save(update_fields=["trial_start", "trial_end", "statut", "is_active", "updated_at"])

    def activate_subscription(self):
        """Active l'abonnement après paiement réussi."""
        self.statut = self.Statut.ACTIVE
        self.is_active = True
        self.next_payment_date = timezone.now().date() + timezone.timedelta(days=30)
        self.save(update_fields=["statut", "is_active", "next_payment_date", "updated_at"])

    def expire_trial(self):
        """Passe l'essai à EXPIRED."""
        self.statut = self.Statut.EXPIRED
        self.is_active = False
        self.save(update_fields=["statut", "is_active", "updated_at"])

    def renew(self):
        """Renouvelle l'abonnement pour 30 jours."""
        if self.next_payment_date:
            base = max(self.next_payment_date, timezone.now().date())
        else:
            base = timezone.now().date()
        self.next_payment_date = base + timezone.timedelta(days=30)
        self.statut = self.Statut.ACTIVE
        self.is_active = True
        self.save(update_fields=["next_payment_date", "statut", "is_active", "updated_at"])


class Transaction(models.Model):
    """
    Transaction de paiement PayTech.
    """

    class Statut(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCESS = "SUCCESS", "Réussi"
        FAILED = "FAILED", "Échoué"
        CANCELLED = "CANCELLED", "Annulé"

    class Provider(models.TextChoices):
        PAYTECH = "PAYTECH", "PayTech"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    montant = models.DecimalField(max_digits=10, decimal_places=0)

    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        default=Provider.PAYTECH,
    )

    transaction_id = models.CharField(max_length=100, unique=True)
    payment_url = models.URLField(max_length=500, blank=True)

    statut = models.CharField(
        max_length=20,
        choices=Statut.choices,
        default=Statut.PENDING,
    )

    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Données brutes PayTech pour debug
    raw_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "payment_transaction"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["statut"]),
        ]

    def __str__(self):
        return f"{self.subscription.ong.name} - {self.montant} FCFA - {self.statut}"