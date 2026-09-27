from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):

    model = User

    list_display = (
        "email",
        "first_name",
        "last_name",
        "role",
        "organization",
        "status",
        "is_active",
    )

    list_filter = (
        "role",
        "status",
        "organization",
    )

    ordering = ("email",)
    search_fields = ("email", "first_name", "last_name")

    fieldsets = (
        ("Connexion", {
            "fields": ("email", "password")
        }),

        ("Informations", {
            "fields": (
                "first_name",
                "last_name",
                "phone",
                "organization",
                "role",
                "status",
            )
        }),

        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "organization",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")