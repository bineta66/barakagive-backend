from rest_framework.permissions import BasePermission


class IsGerant(BasePermission):
    """
    Permission : l'utilisateur doit être un Gérant (GERANT).
    """

    message = "Seul le Gérant de l'ONG peut accéder à cette ressource."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "GERANT"
        )


class IsSubscriptionActive(BasePermission):
    """
    Permission : l'abonnement de l'ONG doit être ACTIVE.
    Utilisé pour bloquer l'accès aux modules quand EXPIRED.
    """

    message = "Votre abonnement est expiré. Veuillez renouveler."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Super Admin a toujours accès
        if user.role == "SUPER_ADMIN":
            return True

        # Gérant : vérifier abonnement
        if user.role == "GERANT" and user.organization:
            try:
                subscription = user.organization.subscription
                return subscription.is_active and subscription.statut == "ACTIVE"
            except Subscription.DoesNotExist:
                return False

        # Autres rôles : accès selon règles métier
        return True


class CanManageSubscription(BasePermission):
    """
    Permission : seul le Gérant peut gérer l'abonnement.
    """

    message = "Seul le Gérant peut gérer l'abonnement."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "GERANT"
        )