from django.contrib import admin
from .models import Budget, Don, Depense, Justification


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = (
        "projet",
        "montant",
        "source_financement",
        "statut",
        "date",
        "organization",
    )
    list_filter = ("statut", "date", "organization")
    search_fields = ("projet__nom", "source_financement")
    ordering = ("-date",)


@admin.register(Don)
class DonAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "bailleur",
        "projet",
        "campagne",
        "montant",
        "moyen_paiement",
        "date",
    )
    list_filter = ("moyen_paiement", "date", "organization")
    search_fields = (
        "reference",
        "bailleur",
        "projet__nom",
        "campagne__nom",
    )
    ordering = ("-date",)


@admin.register(Depense)
class DepenseAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "projet",
        "campagne",
        "region",
        "categorie",
        "montant",
        "statut",
        "date",
    )
    list_filter = (
        "statut",
        "categorie",
        "region",
        "date",
        "organization",
    )
    search_fields = (
        "reference",
        "projet__nom",
        "campagne__nom",
        "fournisseur",
    )
    ordering = ("-date",)


@admin.register(Justification)
class JustificationAdmin(admin.ModelAdmin):
    list_display = (
        "depense",
        "type_fichier",
        "statut",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("statut", "type_fichier")
    search_fields = (
        "depense__reference",
        "uploaded_by__username",
    )
    ordering = ("-created_at",)