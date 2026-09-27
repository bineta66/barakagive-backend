from django.contrib import admin

from .models import Zone, Region, Department


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ["nom", "created_at"]
    search_fields = ["nom"]


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ["nom", "region", "created_at"]
    search_fields = ["nom"]
    list_filter = ["region"]


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ["nom", "region", "departement", "rayon", "statut", "created_at"]
    list_filter = ["region", "departement", "statut"]
    search_fields = ["nom"]
    readonly_fields = ["location", "latitude", "longitude", "created_at", "updated_at"]
