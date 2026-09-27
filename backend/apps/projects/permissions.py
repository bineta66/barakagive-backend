from rest_framework.permissions import BasePermission


class IsGerantOrFinanceOrAgent(BasePermission):
    """
    Accès pour GERANT, CHEF_PROJET, RESPONSABLE_FINANCE et AGENT.
    """

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role in ["GERANT", "CHEF_PROJET", "FINANCE", "AGENT"]
        )


class CanManageProject(BasePermission):
    """
    GERANT peut créer, modifier, archiver les projets de son ONG.
    CHEF_PROJET peut seulement consulter les projets qui lui sont assignés.
    RESPONSABLE_FINANCE peut uniquement modifier le budget.
    AGENT a accès en lecture seule.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        action = getattr(view, "action", None)
        method = request.method

        if request.user.role == "AGENT":
            return method in ["GET", "HEAD", "OPTIONS"] or action in ["list", "retrieve"]
        if request.user.role == "FINANCE":
            return method in ["GET", "HEAD", "OPTIONS", "PATCH"] or action in ["list", "retrieve", "update_budget"]
        if request.user.role == "GERANT":
            return True
        if request.user.role == "CHEF_PROJET":
            return method in ["GET", "HEAD", "OPTIONS"]
        return False

    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        action = getattr(view, "action", None)
        method = request.method

        if request.user.role == "AGENT":
            return method in ["GET", "HEAD", "OPTIONS"] or action in ["retrieve"]
        if request.user.role == "FINANCE":
            if action == "update_budget" or "budget" in request.path:
                return True
            return method in ["GET", "HEAD", "OPTIONS"] or action in ["list", "retrieve"]
        if request.user.role == "GERANT":
            if method in ["PATCH", "PUT", "DELETE"] or action in ["update", "destroy"]:
                return obj.organization == request.user.organization
            return True
        if request.user.role == "CHEF_PROJET":
            return method in ["GET", "HEAD", "OPTIONS"] and obj.chef_projet == request.user
        return False
