import logging
import uuid
import requests
from decimal import Decimal
from django.conf import settings
from django.utils import timezone

from .models import Subscription, Transaction

logger = logging.getLogger(__name__)


class PayTechService:
    """
    Service pour interagir avec l'API PayTech Sénégal.
    """

    BASE_URL = "https://paytech.sn/api"
    CHECKOUT_URL = "https://paytech.sn/payment/checkout"

    def __init__(self):
        self.api_key = getattr(settings, "PAYTECH_API_KEY", "")
        self.api_secret = getattr(settings, "PAYTECH_API_SECRET", "")
        self.success_url = getattr(
            settings, "PAYTECH_SUCCESS_URL", "http://localhost:5173/payment/success"
        )
        self.cancel_url = getattr(
            settings, "PAYTECH_CANCEL_URL", "http://localhost:5173/payment/cancel"
        )
        self.ipn_url = getattr(
            settings, "PAYTECH_IPN_URL", "http://localhost:8000/api/payment/webhook/"
        )

    def _headers(self):
        return {
            "API_KEY": self.api_key,
            "API_SECRET": self.api_secret,
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        }

    def create_payment(self, subscription: Subscription) -> dict:
        """
        Crée un paiement PayTech pour un abonnement.
        Retourne : {"payment_url": "...", "transaction_id": "..."}
        """
        transaction_id = f"TXN-{subscription.ong.id}-{uuid.uuid4().hex[:8].upper()}"

        # Créer la transaction en base
        transaction = Transaction.objects.create(
            subscription=subscription,
            montant=subscription.prix,
            transaction_id=transaction_id,
            statut=Transaction.Statut.PENDING,
        )

        # PayTech attend un payload form-encodé (pas JSON)
        # PayTech exige HTTPS pour toutes les URLs de callback
        def to_https(url):
            if url.startswith("http://"):
                return url.replace("http://", "https://", 1)
            return url

        # En développement local, utiliser les URLs de test PayTech
        success_url = to_https(self.success_url)
        cancel_url = to_https(self.cancel_url)
        ipn_url = to_https(self.ipn_url)

        # Si les URLs sont localhost, utiliser les URLs mobile PayTech en mode test
        if "localhost" in success_url or "127.0.0.1" in success_url:
            success_url = "https://paytech.sn/mobile/success"
        if "localhost" in cancel_url or "127.0.0.1" in cancel_url:
            cancel_url = "https://paytech.sn/mobile/cancel"
        if "localhost" in ipn_url or "127.0.0.1" in ipn_url:
            ipn_url = "https://paytech.sn/mobile/success"  # URL factice valide pour le mode test

        payload = {
            "item_name": f"Abonnement BarakaGive - {subscription.ong.name}",
            "item_price": str(int(subscription.prix)),
            "currency": "XOF",
            "ref_command": transaction_id,
            "command_name": "Abonnement mensuel BarakaGive",
            "custom_field": f'{{"subscription_id": "{str(subscription.id)}"}}',
            "success_url": success_url,
            "cancel_url": cancel_url,
            "ipn_url": ipn_url,
            "env": "test",
        }

        try:
            response = requests.post(
                f"{self.BASE_URL}/payment/request-payment",
                data=payload,           # form-encoded, pas json=
                headers=self._headers(),
                timeout=30,
            )
            logger.error(f"PayTech status: {response.status_code} | body: {response.text[:500]}")
            response.raise_for_status()
            data = response.json()

            logger.info(f"PayTech response: {data}")

            # PayTech retourne un token → URL = checkout/{token}
            if "token" in data:
                token = data["token"]
                payment_url = f"{self.CHECKOUT_URL}/{token}"

                transaction.payment_url = payment_url
                transaction.raw_data = data
                transaction.save(update_fields=["payment_url", "raw_data", "updated_at"])

                return {
                    "payment_url": payment_url,
                    "transaction_id": transaction_id,
                }
            else:
                errors = data.get("error", data.get("message", "Erreur PayTech inconnue"))
                error_msg = str(errors)
                logger.error(f"PayTech error: {error_msg} | full response: {data}")
                transaction.statut = Transaction.Statut.FAILED
                transaction.raw_data = data
                transaction.save(update_fields=["statut", "raw_data", "updated_at"])
                raise Exception(f"PayTech: {error_msg}")

        except requests.RequestException as e:
            logger.error(f"PayTech request failed: {e}")
            transaction.statut = Transaction.Statut.FAILED
            transaction.raw_data = {"error": str(e)}
            transaction.save(update_fields=["statut", "raw_data", "updated_at"])
            raise

    def verify_payment(self, transaction_id: str) -> dict:
        """
        Vérifie le statut d'un paiement auprès de PayTech.
        """
        try:
            response = requests.post(
                f"{self.BASE_URL}/payment/check-status-payment",
                json={"ref_command": transaction_id},
                headers=self._headers(),
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"PayTech verify failed: {e}")
            return {"success": 0, "message": str(e)}


def create_subscription_for_ong(ong) -> Subscription:
    """
    Crée un abonnement TRIAL pour une ONG (7 jours).
    Appelé automatiquement à la première connexion du Gérant.
    """
    subscription, created = Subscription.objects.get_or_create(
        ong=ong,
        defaults={
            "plan": Subscription.Plan.MENSUEL,
            "statut": Subscription.Statut.TRIAL,
            "prix": Decimal("50000"),
            "trial_days": 7,
        },
    )

    if created or subscription.statut == Subscription.Statut.TRIAL:
        subscription.start_trial()

    return subscription


def get_or_create_active_subscription(user) -> Subscription:
    """
    Récupère ou crée l'abonnement pour l'ONG du Gérant connecté.
    """
    if not user.organization:
        raise ValueError("Utilisateur sans organisation")

    return create_subscription_for_ong(user.organization)


def check_and_expire_trials():
    """
    Tâche Cron : expire les essais terminés.
    À lancer quotidiennement via Celery Beat.
    """
    expired_trials = Subscription.objects.filter(
        statut=Subscription.Statut.TRIAL,
        trial_end__lt=timezone.now(),
    )

    count = 0
    for sub in expired_trials:
        sub.expire_trial()
        count += 1

    logger.info(f"Expired {count} trials")
    return count


def check_expiring_subscriptions():
    """
    Tâche Cron : envoie des notifications J-3 et J-1 avant expiration.
    À lancer quotidiennement via Celery Beat.
    """
    from apps.payment.tasks import send_subscription_reminder

    # J-3 et J-1 pour trials
    trial_3 = Subscription.objects.filter(
        statut=Subscription.Statut.TRIAL,
        trial_end__date=timezone.now().date() + timezone.timedelta(days=3),
    )
    trial_1 = Subscription.objects.filter(
        statut=Subscription.Statut.TRIAL,
        trial_end__date=timezone.now().date() + timezone.timedelta(days=1),
    )

    # J-3 et J-1 pour abonnements actifs (renouvellement)
    active_3 = Subscription.objects.filter(
        statut=Subscription.Statut.ACTIVE,
        next_payment_date=timezone.now().date() + timezone.timedelta(days=3),
    )
    active_1 = Subscription.objects.filter(
        statut=Subscription.Statut.ACTIVE,
        next_payment_date=timezone.now().date() + timezone.timedelta(days=1),
    )

    # Envoyer rappels J-3
    for sub in trial_3:
        if sub.ong.users.filter(role="GERANT").exists():
            gerant = sub.ong.users.filter(role="GERANT").first()
            send_subscription_reminder.delay(gerant.id, 3, is_trial=True)

    for sub in active_3:
        if sub.ong.users.filter(role="GERANT").exists():
            gerant = sub.ong.users.filter(role="GERANT").first()
            send_subscription_reminder.delay(gerant.id, 3, is_trial=False)

    # Envoyer rappels J-1
    for sub in trial_1:
        if sub.ong.users.filter(role="GERANT").exists():
            gerant = sub.ong.users.filter(role="GERANT").first()
            send_subscription_reminder.delay(gerant.id, 1, is_trial=True)

    for sub in active_1:
        if sub.ong.users.filter(role="GERANT").exists():
            gerant = sub.ong.users.filter(role="GERANT").first()
            send_subscription_reminder.delay(gerant.id, 1, is_trial=False)

    return {
        "trial_j3": trial_3.count(),
        "trial_j1": trial_1.count(),
        "active_j3": active_3.count(),
        "active_j1": active_1.count(),
    }


paytech_service = PayTechService()