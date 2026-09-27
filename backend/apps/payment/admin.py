from django.contrib import admin
from .models import Subscription, Transaction


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "ong",
        "plan",
        "statut",
        "prix",
        "trial_end",
        "next_payment_date",
        "is_active",
        "created_at",
    ]
    list_filter = ["statut", "plan", "is_active"]
    search_fields = ["ong__name", "ong__acronym"]
    readonly_fields = ["id", "created_at", "updated_at", "days_remaining", "is_trial_expired"]
    ordering = ["-created_at"]

    fieldsets = (
        ("Organisation", {"fields": ("ong",)}),
        ("Plan", {"fields": ("plan", "prix")}),
        ("Statut", {"fields": ("statut", "is_active", "next_payment_date")}),
        ("Essai gratuit", {"fields": ("trial_days", "trial_start", "trial_end")}),
        ("Métadonnées", {"fields": ("id", "created_at", "updated_at")}),
    )


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "subscription",
        "montant",
        "provider",
        "transaction_id",
        "statut",
        "paid_at",
        "created_at",
    ]
    list_filter = ["statut", "provider"]
    search_fields = ["transaction_id", "subscription__ong__name"]
    readonly_fields = ["id", "created_at", "updated_at", "raw_data"]
    ordering = ["-created_at"]

    fieldsets = (
        ("Transaction", {"fields": ("subscription", "montant", "provider", "transaction_id", "payment_url")}),
        ("Statut", {"fields": ("statut", "paid_at")}),
        ("Données brutes", {"fields": ("raw_data",), "classes": ("collapse",)}),
        ("Métadonnées", {"fields": ("id", "created_at", "updated_at")}),
    )