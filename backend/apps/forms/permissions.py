from rest_framework.permissions import BasePermission

from apps.accounts.models import User
from apps.forms.models import Formulaire


class IsChefProjetOrGerantOrAgent(BasePermission):
    """
    Accès pour CHEF_PROJET, GERANT et AGENT.
    Utilisé pour la liste des formulaires.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role in [
                User.Role.CHEF_PROJET,
                User.Role.GERANT,
                User.Role.AGENT,
            ]
        )


class IsChefProjetOnly(BasePermission):
    """
    Accès réservé au CHEF_PROJET uniquement.
    Utilisé pour la création, modification, suppression des formulaires et questions.
    """

    message = "Seul le Chef de projet peut gérer les formulaires."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.can_login
            and request.user.role == User.Role.CHEF_PROJET
        )


class CanManageFormulaire(BasePermission):
    """
    Permission objet pour vérifier que le CHEF_PROJET
    ne peut gérer que les formulaires de ses campagnes/projets.
    """

    message = "Vous n'avez pas l'autorisation sur ce formulaire."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if request.user.role != User.Role.CHEF_PROJET:
            return False

        return (
            obj.organization == request.user.organization
            and obj.campagne.projet.chef_projet == request.user
        )


class CanViewFormulaire(BasePermission):
    """
    Permission pour voir un formulaire.
    - CHEF_PROJET/GERANT : tous les formulaires de leur ONG
    - AGENT : seulement les formulaires PUBLIES de leur ONG
    """

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if obj.organization != request.user.organization:
            return False

        if request.user.role == User.Role.AGENT:
            return obj.statut == Formulaire.Statut.PUBLIE

        return True


class CanManageQuestion(BasePermission):
    """
    Permission pour gérer les questions d'un formulaire.
    Vérifie que le formulaire appartient au chef de projet
    et est en statut BROUILLON.
    """

    message = "Impossible de gérer les questions de ce formulaire."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        if request.user.role != User.Role.CHEF_PROJET:
            return False

        formulaire_id = view.kwargs.get("form_id") or view.kwargs.get("pk")
        if formulaire_id:
            from apps.forms.models import Formulaire
            try:
                formulaire = Formulaire.objects.select_related(
                    "campagne__projet", "organization"
                ).get(id=formulaire_id)
                return (
                    formulaire.organization == request.user.organization
                    and formulaire.campagne.projet.chef_projet == request.user
                    and formulaire.statut == Formulaire.Statut.BROUILLON
                )
            except Formulaire.DoesNotExist:
                return False

        return True


class CanManageQuestionObject(BasePermission):
    """
    Permission objet pour les questions.
    """

    message = "Vous n'avez pas l'autorisation sur cette question."

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False

        if request.user.role != User.Role.CHEF_PROJET:
            return False

        formulaire = obj.formulaire
        return (
            formulaire.organization == request.user.organization
            and formulaire.campagne.projet.chef_projet == request.user
            and formulaire.statut == Formulaire.Statut.BROUILLON
        )