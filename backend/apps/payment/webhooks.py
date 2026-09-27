"""
Webhooks PayTech - Logique séparée pour clarté.
Le webhook principal est dans views.py (PaymentWebhookView).
Ce fichier contient les helpers pour traiter les webhooks.
"""

import logging
from django.utils import timezone
from .models import Transaction, Subscription

logger = logging.getLogger(__name__)


def process_paytech_webhook(data: dict) -> dict:
    """
    Traite un webhook PayTech.
    Retourne un dict avec le résultat du traitement.
    """
    transaction_id = data.get("ref_command") or data.get("transaction_id")

    if not transaction_id:
        return {"success": False, "error": "Transaction ID manquant"}

    try:
        transaction = Transaction.objects.select_related("subscription").get(
            transaction_id=transaction_id
        )
    except Transaction.DoesNotExist:
        logger.warning(f"Transaction {transaction_id} introuvable")
        return {"success": False, "error": "Transaction introuvable"}

    # Statut PayTech
    paytech_status = data.get("status")  # "success", "failed", "cancelled"

    if paytech_status == "success":
        return handle_successful_payment(transaction, data)
    elif paytech_status == "failed":
        return handle_failed_payment(transaction, data)
    elif paytech_status == "cancelled":
        return handle_cancelled_payment(transaction, data)
    else:
        return {"success": False, "error": f"Statut inconnu: {paytech_status}"}


def handle_successful_payment(transaction: Transaction, data: dict) -> dict:
    """Traite un paiement réussi."""
    if transaction.statut == "SUCCESS":
        return {"success": True, "message": "Déjà traité"}

    transaction.statut = "SUCCESS"
    transaction.paid_at = timezone.now()
    transaction.raw_data = {**transaction.raw_data, "webhook": data}
    transaction.save(update_fields=["statut", "paid_at", "raw_data", "updated_at"])

    # Activer l'abonnement
    subscription = transaction.subscription
    subscription.activate_subscription()

    logger.info(f"Paiement réussi pour {subscription.ong.name}: {transaction.transaction_id}")
    return {"success": True, "message": "Paiement activé"}


def handle_failed_payment(transaction: Transaction, data: dict) -> dict:
    """Traite un paiement échoué."""
    transaction.statut = "FAILED"
    transaction.raw_data = {**transaction.raw_data, "webhook": data}
    transaction.save(update_fields=["statut", "raw_data", "updated_at"])

    logger.warning(f"Paiement échoué: {transaction.transaction_id}")
    return {"success": True, "message": "Échec enregistré"}


def handle_cancelled_payment(transaction: Transaction, data: dict) -> dict:
    """Traite un paiement annulé."""
    transaction.statut = "CANCELLED"
    transaction.raw_data = {**transaction.raw_data, "webhook": data}
    transaction.save(update_fields=["statut", "raw_data", "updated_at"])

    logger.info(f"Paiement annulé: {transaction.transaction_id}")
    return {"success": True, "message": "Annulation enregistrée"}