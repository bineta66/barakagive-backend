from rest_framework.permissions import BasePermission

from .models import User


class IsAccountActive(BasePermission):
    """
    Vérifie que l'utilisateur est authentifié
    et que son compte est actif.
    """

    message = "Votre compte est inactif ou suspendu."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
        )


class IsSuperAdmin(BasePermission):
    """Accès réservé au Super Admin"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.SUPER_ADMIN
        )


class IsGerant(BasePermission):
    """Accès réservé au Gérant"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.GERANT
        )


class IsChefProjet(BasePermission):
    """Accès réservé au Chef de projet"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.CHEF_PROJET
        )


class IsFinance(BasePermission):
    """Accès réservé au Responsable Finance"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.FINANCE
        )


class IsAgent(BasePermission):
    """Accès réservé à l'Agent Terrain"""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == User.Role.AGENT
        )