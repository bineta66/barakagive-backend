from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "region",
        "email",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        "region",
    )

    search_fields = (
        "name",
        "email",
    )