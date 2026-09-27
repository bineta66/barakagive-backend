from django.contrib import admin

from .models import Project, ProjectCriteria


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "region", "budget", "archived", "created_at"]
    list_filter = ["archived", "region"]
    search_fields = ["name", "code"]
    readonly_fields = ["code", "created_at", "updated_at"]


@admin.register(ProjectCriteria)
class ProjectCriteriaAdmin(admin.ModelAdmin):
    list_display = ["projet", "nom", "poids", "actif", "created_by", "created_at"]
    list_filter = ["actif", "projet"]
    search_fields = ["nom", "projet__name"]
    readonly_fields = ["created_by", "created_at"]
