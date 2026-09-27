from django.contrib import admin

from .models import Beneficiary, FormResponse


class FormResponseInline(admin.TabularInline):
    model = FormResponse
    extra = 0
    readonly_fields = ["id", "question", "value_text", "value_number", "value_boolean", "value_date", "value_json", "created_at"]
    fields = ["question", "value_text", "value_number", "value_boolean", "value_date", "value_json"]
    ordering = ["question__ordre"]


@admin.register(Beneficiary)
class BeneficiaryAdmin(admin.ModelAdmin):
    list_display = ["nom", "prenom", "telephone", "sexe", "campagne", "zone", "score_vulnerabilite", "sync_status", "created_by", "created_at"]
    list_filter = ["sexe", "sync_status", "campagne__organization", "campagne", "zone", "created_at"]
    search_fields = ["nom", "prenom", "telephone", "local_id", "device_id"]
    readonly_fields = ["id", "local_id", "device_id", "score_vulnerabilite", "sync_status", "created_by", "created_at", "updated_at"]
    inlines = [FormResponseInline]
    ordering = ["-created_at"]


@admin.register(FormResponse)
class FormResponseAdmin(admin.ModelAdmin):
    list_display = ["beneficiary", "formulaire", "question", "created_at"]
    list_filter = ["formulaire", "question__type", "created_at"]
    search_fields = ["beneficiary__nom", "beneficiary__prenom", "value_text"]
    readonly_fields = ["id", "created_at"]
    ordering = ["-created_at"]