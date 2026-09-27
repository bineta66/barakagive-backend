import logging

from celery import shared_task
from django.utils import timezone

from .models import Campaign

logger = logging.getLogger(__name__)


@shared_task
def update_campaign_statuses():
    today = timezone.now().date()
    updated = 0
    for campaign in Campaign.objects.exclude(statut__in=[Campaign.Statut.ANNULEE, Campaign.Statut.TERMINE]):
        target = campaign.statut_auto()
        if campaign.statut != target:
            campaign.statut = target
            campaign.save(update_fields=["statut", "updated_at"])
            updated += 1
    logger.info("Campaign status update complete. updated=%s date=%s", updated, today)
    return updated
