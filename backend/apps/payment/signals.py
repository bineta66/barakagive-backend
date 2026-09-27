import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.organizations.models import Organization
from apps.accounts.models import User

from .models import Subscription
from .services import create_subscription_for_ong, check_and_expire_trials

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Organization)
def organization_approved_create_subscription(sender, instance, created, **kwargs):
    """
    Quand une ONG est approuvée (statut -> ACTIVE) par le Super Admin,
    on ne crée PAS encore l'abonnement. Il sera créé à la première connexion du Gérant.
    """
    # On ne fait rien ici - l'abonnement sera créé à la première connexion du Gérant
    pass


@receiver(post_save, sender=User)
def gerant_first_login_create_subscription(sender, instance, created, **kwargs):
    """
    Cette fonction n'est pas un signal Django standard.
    La création de l'abonnement se fait dans la vue de connexion ou via middleware.
    """
    pass


def create_subscription_on_gerant_login(user):
    """
    Appelé depuis la vue de connexion ou middleware quand un Gérant se connecte.
    Crée l'abonnement TRIAL (7 jours) si pas déjà existant.
    """
    from .services import get_or_create_active_subscription

    if user.role == "GERANT" and user.organization:
        return get_or_create_active_subscription(user)
    return None