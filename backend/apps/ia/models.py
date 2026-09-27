import uuid
from django.db import models
from apps.campaigns.models import Campaign


class IAnalyse(models.Model):
    """
    Modèle pour stocker les résultats d'analyses IA.
    """
    class TypeAnalyse(models.TextChoices):
        GLOBAL = 'global', 'Analyse Globale'
        EXECUTIVE = 'executive', 'Executive Insight'
        FINANCE = 'finance', 'Analyse Financière'
        ZONES = 'zones', 'Analyse Zones'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campagne = models.ForeignKey(
        Campaign,
        on_delete=models.CASCADE,
        related_name='ia_analyses'
    )
    type_analyse = models.CharField(
        max_length=20,
        choices=TypeAnalyse.choices,
        default=TypeAnalyse.GLOBAL
    )
    response_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ia_ianalyse'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['campagne', 'type_analyse']),
        ]

    def __str__(self):
        return f"{self.type_analyse} - {self.campagne.nom}"