from rest_framework.permissions import BasePermission

# Accès au module Finance
FINANCE_ROLES = {
    "SUPER_ADMIN",
    "GERANT",
    "CHEF_PROJET",
    "FINANCE",
    "AGENT",
}

# Création / modification
WRITE_ROLES = {
    "SUPER_ADMIN",
    "GERANT",
    "CHEF_PROJET",
    "FINANCE",
    "AGENT",
}


class FinancePermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # Lecture autorisée pour tout utilisateur connecté
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return True

        # Écriture autorisée pour les utilisateurs enregistrés de l'application
        return True


class CanApproveExpense(BasePermission):
    """
    Seul le Chef de Projet ou le Gérant peut approuver une dépense.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["CHEF_PROJET", "GERANT", "SUPER_ADMIN", "FINANCE"]
        )