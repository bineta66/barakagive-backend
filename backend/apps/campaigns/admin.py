from django.contrib import admin

from .models import Campaign, CampagneAffectation


class CampagneAffectationInline(admin.TabularInline):
    model = CampagneAffectation
    extra = 0
    readonly_fields = ["id", "agent", "zone", "objectif_beneficiaires", "statut", "date_affectation", "created_by"]
    fields = ["agent", "zone", "objectif_beneficiaires", "statut", "date_affectation"]
    ordering = ["-date_affectation"]


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ["code_campagne", "nom", "projet", "organization", "date_debut", "date_fin", "created_by", "created_at"]
    list_filter = ["organization", "projet", "date_debut", "date_fin", "created_at"]
    search_fields = ["code_campagne", "nom", "description", "projet__name", "organization__name"]
    readonly_fields = ["id", "code_campagne", "created_by", "created_at", "updated_at"]
    inlines = [CampagneAffectationInline]
    ordering = ["-created_at"]


@admin.register(CampagneAffectation)
class CampagneAffectationAdmin(admin.ModelAdmin):
    list_display = ["campagne", "agent", "zone", "objectif_beneficiaires", "statut", "date_affectation", "created_by"]
    list_filter = ["statut", "campagne__organization", "campagne", "date_affectation"]
    search_fields = ["campagne__nom", "campagne__code_campagne", "agent__email", "agent__first_name", "agent__last_name", "zone"]
    readonly_fields = ["id", "date_affectation", "created_by"]
    ordering = ["-date_affectation"]
