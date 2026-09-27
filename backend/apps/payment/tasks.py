from celery import shared_task
from django.utils import timezone

from apps.payment.services import check_and_expire_trials, check_expiring_subscriptions

import logging

logger = logging.getLogger(__name__)


@shared_task
def expire_trials():
    """
    Tâche Cron quotidienne : expire les essais gratuits terminés.
    """
    from apps.payment.services import check_and_expire_trials

    count = check_and_expire_trials()
    logger.info(f"Expired {count} trials")
    return count


@shared_task
def check_expiring_subscriptions():
    """
    Tâche Cron quotidienne : vérifie les abonnements qui expirent bientôt (J-3, J-1)
    et envoie des notifications.
    """
    from apps.payment.services import check_expiring_subscriptions as check_service

    result = check_service()
    logger.info(f"Expiring check: {result}")
    return result


@shared_task
def send_subscription_reminder(user_id, days_remaining, is_trial=True):
    """
    Envoie un email de rappel avant expiration.
    """
    from apps.accounts.tasks import send_invitation_email
    from apps.accounts.models import User

    try:
        user = User.objects.get(id=user_id)
        subscription = user.organization.subscription if user.organization else None

        if not subscription:
            return

        if is_trial:
            subject = f"Votre essai gratuit expire dans {days_remaining} jour(s)"
            message = (
                f"Bonjour {user.first_name},\n\n"
                f"Votre période d'essai gratuit de 7 jours se termine dans {days_remaining} jour(s).\n"
                f"Pour continuer à utiliser BarakaGive360, veuillez activer votre abonnement mensuel de 50 000 FCFA.\n\n"
                f"Cordialement,\nL'équipe BarakaGive360"
            )
        else:
            subject = f"Votre abonnement expire dans {days_remaining} jour(s)"
            message = (
                f"Bonjour {user.first_name},\n\n"
                f"Votre abonnement mensuel de 50 000 FCFA expire dans {days_remaining} jour(s).\n"
                f"Veuillez renouveler pour continuer à utiliser BarakaGive360 sans interruption.\n\n"
                f"Cordialement,\nL'équipe BarakaGive360"
            )

        send_invitation_email.delay(
            recipient_email=user.email,
            first_name=user.first_name,
            activation_link="",  # pas de lien d'activation ici
            subject_override=subject,
            html_override=f"""
            <h2>{subject}</h2>
            <p>Bonjour {user.first_name},</p>
            <p>{message}</p>
            <p><a href="http://localhost:5173/payment" style="background:#744D03; color:white; padding:12px 20px; text-decoration:none; border-radius:6px;">
            Gérer mon abonnement
            </a></p>
            <p>L'équipe BarakaGive360</p>
            """,
        )
    except Exception as e:
        logger.error(f"Erreur envoi rappel abonnement: {e}")