from rest_framework import serializers
from .models import Subscription, Transaction


class SubscriptionSerializer(serializers.ModelSerializer):
    days_remaining = serializers.SerializerMethodField()
    trial_end_formatted = serializers.SerializerMethodField()
    next_payment_date_formatted = serializers.SerializerMethodField()
    is_trial_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "statut",
            "prix",
            "days_remaining",
            "trial_end",
            "trial_end_formatted",
            "next_payment_date",
            "next_payment_date_formatted",
            "is_active",
            "is_trial_expired",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_days_remaining(self, obj):
        return obj.days_remaining

    def get_trial_end_formatted(self, obj):
        if obj.trial_end:
            return obj.trial_end.strftime("%d/%m/%Y")
        return None

    def get_next_payment_date_formatted(self, obj):
        if obj.next_payment_date:
            return obj.next_payment_date.strftime("%d/%m/%Y")
        return None


class TransactionSerializer(serializers.ModelSerializer):
    paid_at_formatted = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id",
            "montant",
            "provider",
            "transaction_id",
            "statut",
            "paid_at",
            "paid_at_formatted",
            "created_at",
            "created_at_formatted",
        ]
        read_only_fields = fields

    def get_paid_at_formatted(self, obj):
        if obj.paid_at:
            return obj.paid_at.strftime("%d/%m/%Y %H:%M")
        return None

    def get_created_at_formatted(self, obj):
        return obj.created_at.strftime("%d/%m/%Y %H:%M")


class SubscriptionStatusSerializer(serializers.ModelSerializer):
    """Serializer léger pour le status de l'abonnement (banner, dashboard)."""

    days_remaining = serializers.SerializerMethodField()
    trial_end_formatted = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "plan",
            "statut",
            "prix",
            "days_remaining",
            "trial_end",
            "trial_end_formatted",
            "is_trial_expired",
        ]

    def get_days_remaining(self, obj):
        return obj.days_remaining

    def get_trial_end_formatted(self, obj):
        if obj.trial_end:
            return obj.trial_end.strftime("%d %B %Y")
        return None


class PaymentInitiateSerializer(serializers.Serializer):
    """Serializer pour initier un paiement."""

    payment_url = serializers.URLField(read_only=True)
    transaction_id = serializers.CharField(read_only=True)