from rest_framework.permissions import BasePermission

from apps.accounts.models import User


class IsAgentOrChefProjetOrGerant(BasePermission):
    """
    Accès pour AGENT, CHEF_PROJET et GERANT.
    Utilisé pour la liste des bénéficiaires.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role in [
                User.Role.AGENT,
                User.Role.CHEF_PROJET,
                User.Role.GERANT,
            ]
        )


class IsAgentOnly(BasePermission):
    """
    Accès réservé à l'AGENT uniquement.
    Utilisé pour la création de bénéficiaires.
    """

    message = "Seul un Agent terrain peut créer un bénéficiaire."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role == User.Role.AGENT
        )


class CanManageBeneficiary(BasePermission):
    """
    Permission objet pour gérer un bénéficiaire.
    - AGENT : seulement ses propres bénéficiaires
    - CHEF_PROJET : tous les bénéficiaires de ses campagnes
    - GERANT : lecture seule
    """

    message = "Vous n'avez pas l'autorisation sur ce bénéficiaire."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if obj.organization != request.user.organization:
            return False

        if request.user.role == User.Role.AGENT:
            # L'agent ne peut gérer que ses propres bénéficiaires
            if view.action in ["update", "partial_update", "destroy"]:
                return obj.created_by == request.user
            return True

        if request.user.role == User.Role.CHEF_PROJET:
            # Le chef de projet gère les bénéficiaires de ses campagnes
            return obj.campagne.projet.chef_projet == request.user

        if request.user.role == User.Role.GERANT:
            # Le gérant a accès en lecture seule
            return view.action in ["list", "retrieve"]

        return False


class CanViewBeneficiary(BasePermission):
    """
    Permission pour voir un bénéficiaire.
    - AGENT : ses propres bénéficiaires
    - CHEF_PROJET : tous les bénéficiaires de ses campagnes
    - GERANT : tous les bénéficiaires de son ONG
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if obj.organization != request.user.organization:
            return False

        if request.user.role == User.Role.AGENT:
            return obj.created_by == request.user

        if request.user.role == User.Role.CHEF_PROJET:
            return obj.campagne.projet.chef_projet == request.user

        if request.user.role == User.Role.GERANT:
            return True

        return False