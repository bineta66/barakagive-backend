from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsChefProjetOrGerant(BasePermission):
    """
    Accès pour CHEF_PROJET, GERANT et AGENT.
    Utilisé pour la liste et le détail des campagnes.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role in [
                User.Role.SUPER_ADMIN,
                User.Role.CHEF_PROJET,
                User.Role.GERANT,
                User.Role.AGENT,
                User.Role.FINANCE,
            ]
        )

class IsChefProjetOnly(BasePermission):
    """
    Accès réservé au CHEF_PROJET uniquement.
    Utilisé pour la création, modification et suppression des campagnes.
    """

    message = "Seul le Chef de projet peut effectuer cette action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role in [User.Role.CHEF_PROJET, User.Role.SUPER_ADMIN]
        )


class CanManageCampaign(BasePermission):
    """
    Permission objet pour vérifier que le CHEF_PROJET
    ne peut gérer que les campagnes de son projet/ONG.
    """

    message = "Vous n'avez pas l'autorisation sur cette campagne."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if request.user.role == User.Role.SUPER_ADMIN:
            return True

        if request.user.role != User.Role.CHEF_PROJET:
            return False

        return (
            obj.organization == request.user.organization
            and obj.projet.chef_projet == request.user
        )