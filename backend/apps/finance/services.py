from django.db.models import Sum

from apps.campaigns.models import Campaign
from .models import Budget, Don, Depense


def prepare_budget_analysis(campaign_id):
    """
    Prépare les données réelles envoyées à FastAPI.
    """

    campagne = Campaign.objects.select_related("projet").get(id=campaign_id)
    projet = campagne.projet

    # Budget du projet
    budgets = Budget.objects.filter(projet=projet)

    budget_total = budgets.aggregate(
        total=Sum("montant")
    )["total"] or 0

    # Dons de cette campagne
    dons_total = Don.objects.filter(
        campagne=campagne
    ).aggregate(
        total=Sum("montant")
    )["total"] or 0

    # Dépenses de cette campagne
    depenses_total = Depense.objects.filter(
        campagne=campagne
    ).aggregate(
        total=Sum("montant")
    )["total"] or 0

    solde = dons_total - depenses_total

    taux_execution = 0
    if budget_total > 0:
        taux_execution = round(
            (depenses_total / budget_total) * 100, 2
        )

    depenses_par_categorie = (
        Depense.objects.filter(campagne=campagne)
        .values("categorie")
        .annotate(montant=Sum("montant"))
        .order_by("-montant")
    )

    depenses_par_region = (
        Depense.objects.filter(campagne=campagne)
        .values("region")
        .annotate(montant=Sum("montant"))
        .order_by("-montant")
    )

    jours_restants = max(
        0,
        (campagne.date_fin - campagne.date_debut).days
    )

    return {
        "campagne": {
            "id": str(campagne.id),
            "nom": campagne.nom,
            "date_fin": campagne.date_fin,
            "jours_restants": jours_restants,
        },
        "budget_total": float(budget_total),
        "dons_recus": float(dons_total),
        "depenses_totales": float(depenses_total),
        "solde": float(solde),
        "taux_execution": taux_execution,
        "depenses_par_categorie": list(depenses_par_categorie),
        "depenses_par_region": list(depenses_par_region),
    }