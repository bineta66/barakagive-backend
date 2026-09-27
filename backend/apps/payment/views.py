from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.organizations.models import Organization
from .models import Subscription, Transaction
from .serializers import (
    SubscriptionSerializer,
    SubscriptionStatusSerializer,
    TransactionSerializer,
    PaymentInitiateSerializer,
)
from .services import (
    get_or_create_active_subscription,
    paytech_service,
    check_and_expire_trials,
)


class SubscriptionStatusView(APIView):
    """
    GET /api/payment/subscription/
    Retourne l'état de l'abonnement du Gérant connecté.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "GERANT":
            return Response(
                {"detail": "Seul le Gérant peut accéder à l'abonnement."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.organization:
            return Response(
                {"detail": "Aucune organisation associée à ce compte."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = get_or_create_active_subscription(user)
        serializer = SubscriptionStatusSerializer(subscription)
        return Response(serializer.data)


class SubscriptionDetailView(APIView):
    """
    GET /api/payment/subscription/detail/
    Retourne les détails complets de l'abonnement.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "GERANT":
            return Response(
                {"detail": "Seul le Gérant peut accéder à l'abonnement."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.organization:
            return Response(
                {"detail": "Aucune organisation associée à ce compte."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = get_or_create_active_subscription(user)
        serializer = SubscriptionSerializer(subscription)
        return Response(serializer.data)


class InitiatePaymentView(APIView):
    """
    POST /api/payment/subscribe/
    Crée une transaction PayTech et retourne l'URL de paiement.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.role != "GERANT":
            return Response(
                {"detail": "Seul le Gérant peut initier un paiement."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = get_or_create_active_subscription(user)

        # Vérifier si déjà un paiement en cours
        pending_tx = subscription.transactions.filter(
            statut=Transaction.Statut.PENDING
        ).first()
        if pending_tx and pending_tx.payment_url:
            return Response(
                {"payment_url": pending_tx.payment_url, "transaction_id": pending_tx.transaction_id},
                status=status.HTTP_200_OK,
            )

        try:
            result = paytech_service.create_payment(subscription)
            # Retourner directement sans serializer (les champs read_only posent problème)
            return Response({
                "payment_url": result["payment_url"],
                "transaction_id": result["transaction_id"],
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Payment initiation error: {str(e)}")
            return Response(
                {"detail": f"Erreur lors de la création du paiement : {str(e)}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PaymentWebhookView(APIView):
    """
    POST /api/payment/webhook/
    Webhook PayTech pour confirmation de paiement.
    """
    permission_classes = []  # Public - appelé par PayTech
    authentication_classes = []

    def post(self, request):
        data = request.data
        transaction_id = data.get("ref_command") or data.get("transaction_id")

        if not transaction_id:
            return Response(
                {"detail": "Transaction ID manquant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            transaction = Transaction.objects.select_related("subscription").get(
                transaction_id=transaction_id
            )
        except Transaction.DoesNotExist:
            return Response(
                {"detail": "Transaction introuvable"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Vérifier le paiement auprès de PayTech
        verification = paytech_service.verify_payment(transaction_id)

        if verification.get("success") == 1:
            # Paiement confirmé
            transaction.statut = Transaction.Statut.SUCCESS
            transaction.paid_at = timezone.now()
            transaction.raw_data = {**transaction.raw_data, "webhook": data, "verification": verification}
            transaction.save(update_fields=["statut", "paid_at", "raw_data", "updated_at"])

            # Activer l'abonnement
            subscription = transaction.subscription
            subscription.activate_subscription()

            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        else:
            transaction.statut = Transaction.Statut.FAILED
            transaction.raw_data = {**transaction.raw_data, "webhook": data, "verification": verification}
            transaction.save(update_fields=["statut", "raw_data", "updated_at"])

            return Response(
                {"detail": "Paiement échoué"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class TransactionHistoryView(APIView):
    """
    GET /api/payment/history/
    Retourne l'historique des transactions du Gérant.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "GERANT":
            return Response(
                {"detail": "Seul le Gérant peut accéder à l'historique."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.organization:
            return Response(
                {"detail": "Aucune organisation associée à ce compte."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = get_or_create_active_subscription(user)
        transactions = subscription.transactions.all()
        serializer = TransactionSerializer(transactions, many=True)
        return Response(serializer.data)


class SubscriptionCheckView(APIView):
    """
    GET /api/payment/check/
    Vérification rapide du statut pour le middleware/banner.
    Retourne juste le statut et jours restants.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != "GERANT":
            return Response(
                {"detail": "Seul le Gérant peut accéder."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not user.organization:
            return Response(
                {"detail": "Aucune organisation associée à ce compte."},
                status=status.HTTP_403_FORBIDDEN,
            )

        subscription = get_or_create_active_subscription(user)

        # Auto-expire si trial dépassé
        if subscription.is_trial_expired:
            subscription.expire_trial()

        return Response({
            "statut": subscription.statut,
            "days_remaining": subscription.days_remaining,
            "is_trial_expired": subscription.is_trial_expired,
            "trial_end": subscription.trial_end,
            "next_payment_date": subscription.next_payment_date,
            "is_active": subscription.is_active,
        })


# Import timezone for webhook
from django.utils import timezone


class AdminSubscriptionListView(APIView):
    """
    GET  /api/payment/admin/subscriptions/   — Super Admin : liste tous les abonnements
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != "SUPER_ADMIN":
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)

        subscriptions = (
            Subscription.objects.select_related("ong")
            .prefetch_related("transactions")
            .order_by("-created_at")
        )

        data = []
        for sub in subscriptions:
            last_tx = sub.transactions.filter(statut="SUCCESS").order_by("-paid_at").first()
            data.append({
                "id": str(sub.id),
                "ong_id": sub.ong.id,
                "ong_nom": sub.ong.name,
                "ong_email": sub.ong.email,
                "plan": sub.get_plan_display(),
                "plan_code": sub.plan,
                "statut": sub.statut,
                "prix": str(sub.prix),
                "is_active": sub.is_active,
                "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "next_payment_date": sub.next_payment_date.isoformat() if sub.next_payment_date else None,
                "date_creation": sub.created_at.isoformat(),
                "dernier_paiement": last_tx.paid_at.isoformat() if last_tx else None,
                "nb_transactions": sub.transactions.count(),
            })

        return Response(data)


class AdminSubscriptionDetailView(APIView):
    """
    GET  /api/payment/admin/subscriptions/{id}/         — détail d'un abonnement
    POST /api/payment/admin/subscriptions/{id}/suspend/ — suspendre
    POST /api/payment/admin/subscriptions/{id}/reactivate/ — réactiver
    """
    permission_classes = [IsAuthenticated]

    def _get_sub(self, pk):
        try:
            return Subscription.objects.select_related("ong").prefetch_related("transactions").get(pk=pk)
        except Subscription.DoesNotExist:
            return None

    def get(self, request, pk):
        if request.user.role != "SUPER_ADMIN":
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        sub = self._get_sub(pk)
        if not sub:
            return Response({"detail": "Abonnement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        transactions = []
        for tx in sub.transactions.all()[:10]:
            transactions.append({
                "id": str(tx.id),
                "montant": str(tx.montant),
                "statut": tx.statut,
                "transaction_id": tx.transaction_id,
                "paid_at": tx.paid_at.isoformat() if tx.paid_at else None,
                "created_at": tx.created_at.isoformat(),
            })

        return Response({
            "id": str(sub.id),
            "ong_nom": sub.ong.name,
            "ong_email": sub.ong.email,
            "plan": sub.get_plan_display(),
            "statut": sub.statut,
            "prix": str(sub.prix),
            "is_active": sub.is_active,
            "trial_start": sub.trial_start.isoformat() if sub.trial_start else None,
            "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
            "next_payment_date": sub.next_payment_date.isoformat() if sub.next_payment_date else None,
            "date_creation": sub.created_at.isoformat(),
            "transactions": transactions,
        })


class AdminSubscriptionSuspendView(APIView):
    """POST /api/payment/admin/subscriptions/{pk}/suspend/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != "SUPER_ADMIN":
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        try:
            sub = Subscription.objects.get(pk=pk)
        except Subscription.DoesNotExist:
            return Response({"detail": "Abonnement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        sub.statut = Subscription.Statut.CANCELLED
        sub.is_active = False
        sub.save(update_fields=["statut", "is_active", "updated_at"])
        return Response({"message": "Abonnement suspendu.", "statut": sub.statut})


class AdminSubscriptionReactivateView(APIView):
    """POST /api/payment/admin/subscriptions/{pk}/reactivate/"""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if request.user.role != "SUPER_ADMIN":
            return Response({"detail": "Accès réservé au Super Admin."}, status=status.HTTP_403_FORBIDDEN)
        try:
            sub = Subscription.objects.get(pk=pk)
        except Subscription.DoesNotExist:
            return Response({"detail": "Abonnement introuvable."}, status=status.HTTP_404_NOT_FOUND)

        sub.statut = Subscription.Statut.ACTIVE
        sub.is_active = True
        if not sub.next_payment_date:
            from django.utils import timezone as tz
            sub.next_payment_date = tz.now().date() + __import__('datetime').timedelta(days=30)
        sub.save(update_fields=["statut", "is_active", "next_payment_date", "updated_at"])
        return Response({"message": "Abonnement réactivé.", "statut": sub.statut})
