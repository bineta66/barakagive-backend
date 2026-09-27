from django.contrib import admin

from .models import Formulaire, FormField


class FormFieldInline(admin.TabularInline):
    model = FormField
    extra = 0
    readonly_fields = ["id", "created_at", "updated_at"]
    fields = ["label", "type", "obligatoire", "ordre", "placeholder", "options"]
    ordering = ["ordre"]


@admin.register(Formulaire)
class FormulaireAdmin(admin.ModelAdmin):
    list_display = ["nom", "campagne", "version", "statut", "created_by", "created_at"]
    list_filter = ["statut", "campagne__organization", "created_at"]
    search_fields = ["nom", "description", "campagne__nom"]
    readonly_fields = ["id", "version", "created_by", "created_at", "updated_at"]
    inlines = [FormFieldInline]
    ordering = ["-created_at"]


@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    list_display = ["label", "formulaire", "type", "obligatoire", "ordre"]
    list_filter = ["type", "obligatoire", "formulaire__statut"]
    search_fields = ["label", "formulaire__nom"]
    readonly_fields = ["id", "created_at", "updated_at"]
    ordering = ["formulaire", "ordre"]