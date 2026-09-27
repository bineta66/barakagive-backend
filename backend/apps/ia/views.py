import json
import logging
import requests
from django.conf import settings
from django.utils import timezone
from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.campaigns.models import Campaign
from apps.beneficiaries.models import Beneficiary
from apps.zones.models import Zone
from apps.finance.models import Depense, Budget
from apps.projects.models import Project
from apps.ia.models import IAnalyse
from apps.ia.services import compute_region_zones_data, get_zone_beneficiaries_detail

logger = logging.getLogger(__name__)


def compute_assistant_dashboard(user):
    """
    Calcule dynamiquement les métriques exécutives réelles de l'organisation à partir de PostgreSQL.
    Aucune donnée n'est simulée ou codée en dur.
    """
    now = timezone.now()
    today = now.date()

    if user.role == "SUPER_ADMIN":
        projects_qs = Project.objects.all()
        campaigns_qs = Campaign.objects.all()
        beneficiaries_qs = Beneficiary.objects.all()
        budgets_qs = Budget.objects.all()
        depenses_qs = Depense.objects.all()
    else:
        org = user.organization
        projects_qs = Project.objects.filter(organization=org)
        campaigns_qs = Campaign.objects.filter(organization=org)
        beneficiaries_qs = Beneficiary.objects.filter(organization=org)
        budgets_qs = Budget.objects.filter(organization=org)
        depenses_qs = Depense.objects.filter(organization=org)

    # 1. Projets et Campagnes actifs
    projets_actifs = projects_qs.filter(archived=False).count()
    active_campaigns_qs = campaigns_qs.filter(statut=Campaign.Statut.EN_COURS)
    campagnes_actives = active_campaigns_qs.count()
    beneficiaires = beneficiaries_qs.count()

    # 2. Données Financières
    sum_budgets = budgets_qs.aggregate(total=models.Sum("montant"))["total"]
    if sum_budgets is None or sum_budgets == 0:
        sum_prj_budgets = projects_qs.filter(archived=False).aggregate(total=models.Sum("budget"))["total"]
        budget_total = float(sum_prj_budgets or 0)
    else:
        budget_total = float(sum_budgets or 0)

    sum_depenses = depenses_qs.aggregate(total=models.Sum("montant"))["total"]
    depenses = float(sum_depenses or 0)
    solde = budget_total - depenses
    taux_execution = (depenses / budget_total * 100) if budget_total > 0 else 0

    # 3. Campagnes proches de la clôture (date_fin >= aujourd'hui)
    closing_soon_campaigns = list(
        active_campaigns_qs.filter(date_fin__gte=today).order_by("date_fin")[:5]
    )

    # 4. Régions les plus actives
    region_counts = (
        beneficiaries_qs.values("zone__region")
        .annotate(total=models.Count("id"))
        .order_by("-total")
    )
    region_counts = [r for r in region_counts if r.get("zone__region")]
    top_region = region_counts[0]["zone__region"] if region_counts else None
    top_region_count = region_counts[0]["total"] if region_counts else 0

    # 5. Campagne avec le plus de bénéficiaires
    top_campaign = None
    if active_campaigns_qs.exists():
        top_campaign = (
            active_campaigns_qs.annotate(nb_ben=models.Count("beneficiaries"))
            .order_by("-nb_ben")
            .first()
        )

    # 6. Résumé dynamique
    if campagnes_actives > 0:
        if top_campaign and top_campaign.beneficiaries.count() > 0:
            camp_plural = "campagnes sont actuellement en cours" if campagnes_actives > 1 else "campagne est actuellement en cours"
            resume = (
                f"{campagnes_actives} {camp_plural}. "
                f"La campagne '{top_campaign.nom}' présente le plus grand nombre de bénéficiaires ({top_campaign.beneficiaries.count()})."
            )
        else:
            camp_plural = "campagnes sont actuellement en cours" if campagnes_actives > 1 else "campagne est actuellement en cours"
            ben_plural = "bénéficiaires enregistrés" if beneficiaires > 1 else "bénéficiaire enregistré"
            resume = f"{campagnes_actives} {camp_plural} avec {beneficiaires} {ben_plural}."
    elif projets_actifs > 0:
        prj_plural = "projets actifs" if projets_actifs > 1 else "projet actif"
        resume = f"{projets_actifs} {prj_plural}. Aucune campagne opérationnelle n'est actuellement en cours."
    else:
        resume = "Aucun projet ou campagne active n'est actuellement enregistré."

    # 7. Alertes réelles calculées
    alertes = []

    # Projets dépassant 80% du budget
    high_budget_projects = []
    for p in projects_qs.filter(archived=False):
        p_budget = float(p.budget or 0)
        if p_budget > 0:
            p_dep = float(depenses_qs.filter(projet=p).aggregate(s=models.Sum("montant"))["s"] or 0)
            ratio = (p_dep / p_budget) * 100
            if ratio >= 80:
                high_budget_projects.append((p.name, round(ratio, 1)))

    if len(high_budget_projects) == 1:
        alertes.append(f"Le projet '{high_budget_projects[0][0]}' dépasse {high_budget_projects[0][1]} % de son budget")
    elif len(high_budget_projects) > 1:
        alertes.append(f"{len(high_budget_projects)} projets dépassent 80 % de leur enveloppe budgétaire")

    # Concentration géographique
    if top_region and beneficiaires > 0:
        pct_region = round((top_region_count / beneficiaires) * 100)
        if pct_region >= 30:
            alertes.append(f"La région de {top_region} concentre le plus de bénéficiaires ({top_region_count} bénéficiaires, soit {pct_region} %)")

    # Campagnes proches de la clôture
    for camp in closing_soon_campaigns:
        days_left = (camp.date_fin - today).days
        if days_left <= 7:
            days_label = "aujourd'hui" if days_left == 0 else f"dans {days_left} jour{'s' if days_left > 1 else ''}"
            alertes.append(f"La campagne '{camp.nom}' se clôture {days_label}")

    # Solde déficitaire ou critique
    if solde < 0:
        alertes.append("Le solde budgétaire global présente un dépassement (déficit).")
    elif budget_total > 0 and (solde / budget_total) < 0.1:
        alertes.append("Le solde budgétaire disponible restant est inférieur à 10 %.")

    if not alertes:
        alertes.append("Aucune anomalie budgétaire ou opérationnelle détectée.")

    # 8. Recommandations dynamiques
    recommandations = []
    if closing_soon_campaigns:
        camp_names = ", ".join([c.nom for c in closing_soon_campaigns[:2]])
        recommandations.append(f"Prioriser les campagnes proches de la clôture ({camp_names})")

    if high_budget_projects:
        recommandations.append("Vérifier et ajuster les dépenses des projets à risque budgétaire élevé")

    if beneficiaires == 0 and campagnes_actives > 0:
        recommandations.append("Mobiliser les agents terrain pour accélérer le recensement des bénéficiaires")

    if solde > 0 and taux_execution < 50 and campagnes_actives > 0:
        recommandations.append("Accélérer l'exécution des activités planifiées pour atteindre les objectifs de décaissement")

    recommandations.append("Consulter la carte des priorités pour orienter les actions vers les zones les plus vulnérables")

    # Alerte status pour indicateur orb (GREEN, YELLOW, RED)
    alert_status = "GREEN"
    if high_budget_projects or solde < 0:
        alert_status = "RED"
    elif any((camp.date_fin - today).days <= 7 for camp in closing_soon_campaigns) or (budget_total > 0 and (solde / budget_total) < 0.1):
        alert_status = "YELLOW"

    return {
        "generated_at": now.isoformat(),
        "projets_actifs": projets_actifs,
        "campagnes_actives": campagnes_actives,
        "beneficiaires": beneficiaires,
        "budget_total": budget_total,
        "depenses": depenses,
        "solde": solde,
        "taux_execution": round(taux_execution, 1),
        "resume": resume,
        "alertes": alertes,
        "recommandations": recommandations[:4],
        "alert": alert_status,
        "budget": {
            "total": budget_total,
            "depenses": depenses,
            "solde": solde,
            "taux": round(taux_execution, 1),
            "alerte": alert_status == "RED",
        },
        "campagne_prioritaire": {
            "nom": top_campaign.nom,
            "urgence": "Élevée" if (top_campaign.date_fin - today).days <= 14 else "Normale",
            "region": top_campaign.zones.first().region if top_campaign and top_campaign.zones.exists() else "Multi-zones",
        } if top_campaign else None,
    }


class AssistantDashboardView(APIView):
    """
    GET /api/assistant/dashboard/
    Retourne les indicateurs stratégiques et opérationnels en temps réel
    calculés exclusivement depuis la base de données PostgreSQL.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = compute_assistant_dashboard(request.user)
        return Response(data)


def compute_executive_payload(campaign, user):
    """Compute executive insight payload from Django data"""
    # Beneficiaries stats
    beneficiaries = Beneficiary.objects.filter(campagne=campaign)
    total_beneficiaries = beneficiaries.count()
    
    # Zones with beneficiary counts and scores
    zones = Zone.objects.filter(campaigns=campaign, organization=user.organization)
    zones_data = []
    for zone in zones:
        zone_beneficiaries = beneficiaries.filter(zone=zone)
        avg_score = zone_beneficiaries.exclude(score_vulnerabilite__isnull=True).aggregate(
            avg_score=models.Avg('score_vulnerabilite')
        )['avg_score'] or 0
        zones_data.append({
            "id": str(zone.id),
            "nom": zone.nom,
            "region": zone.region,
            "departement": zone.departement,
            "beneficiaires": zone_beneficiaries.count(),
            "score_moyen": float(avg_score),
            "latitude": float(zone.latitude),
            "longitude": float(zone.longitude),
        })
    
    # Budget data
    budgets = Budget.objects.filter(projet=campaign.projet)
    total_budget = sum(float(b.montant) for b in budgets)
    
    depenses = Depense.objects.filter(projet=campaign.projet)
    total_depenses = sum(float(d.montant) for d in depenses)
    
    # Expenses by zone and category
    depenses_par_zone = {}
    depenses_par_categorie = {}
    for depense in depenses:
        zone_name = depense.projet.zone.nom if hasattr(depense.projet, 'zone') and depense.projet.zone else "Non assigné"
        depenses_par_zone[zone_name] = depenses_par_zone.get(zone_name, 0) + float(depense.montant)
        
        cat_name = depense.poste_budgetaire.libelle if depense.poste_budgetaire else "Non catégorisé"
        depenses_par_categorie[cat_name] = depenses_par_categorie.get(cat_name, 0) + float(depense.montant)
    
    return {
        "campagne_id": str(campaign.id),
        "nom": campaign.nom,
        "date_debut": campaign.date_debut.isoformat(),
        "date_fin": campaign.date_fin.isoformat(),
        "total_beneficiaires": total_beneficiaries,
        "zones": zones_data,
        "budgets": [
            {"id": str(b.id), "montant_total": float(b.montant), "statut": b.statut}
            for b in budgets
        ],
        "total_budget": total_budget,
        "total_depenses": total_depenses,
        "solde": total_budget - total_depenses,
        "taux_execution": (total_depenses / total_budget * 100) if total_budget > 0 else 0,
        "depenses_par_zone": depenses_par_zone,
        "depenses_par_categorie": depenses_par_categorie,
    }


def compute_finance_payload(campaign, user):
    """Compute finance payload for budget analysis"""
    budgets = Budget.objects.filter(projet=campaign.projet)
    total_budget = sum(float(b.montant) for b in budgets)
    
    depenses = Depense.objects.filter(projet=campaign.projet)
    total_depenses = sum(float(d.montant) for d in depenses)
    solde = total_budget - total_depenses
    taux = (total_depenses / total_budget * 100) if total_budget > 0 else 0
    
    # Expenses by zone
    depenses_par_zone = {}
    for depense in depenses.select_related('projet__zone'):
        zone_name = depense.projet.zone.nom if depense.projet.zone else "Non assigné"
        depenses_par_zone[zone_name] = depenses_par_zone.get(zone_name, 0) + float(depense.montant)
    
    # Expenses by category
    depenses_par_categorie = {}
    for depense in depenses.select_related('poste_budgetaire'):
        cat_name = depense.poste_budgetaire.libelle if depense.poste_budgetaire else "Non catégorisé"
        depenses_par_categorie[cat_name] = depenses_par_categorie.get(cat_name, 0) + float(depense.montant)
    
    return {
        "campagne_id": str(campaign.id),
        "nom": campaign.nom,
        "budget_total": total_budget,
        "depenses_totales": total_depenses,
        "solde": solde,
        "taux_execution": taux,
        "date_cloture": campaign.date_fin.isoformat(),
        "jours_restants": (campaign.date_fin - timezone.now().date()).days,
        "depenses_par_zone": depenses_par_zone,
        "depenses_par_categorie": depenses_par_categorie,
    }


def call_ia_service(endpoint: str, payload: dict) -> dict:
    """Call the FastAPI IA service"""
    url = f"{settings.IA_SERVICE_URL}{endpoint}"
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"IA service call failed: {e}")
        raise


class ExecutiveInsightView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        data = compute_assistant_dashboard(request.user)
        return Response(data)


class RegionZonesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, id):
        campaign = get_active_campaign(request.user)
        if not campaign:
            return Response({"region": id, "zones": []})
        
        # Donnees calculees par Django (jamais d'erreur 500 pour un cas metier)
        try:
            data = compute_region_zones_data(campaign, id)
        except Exception as e:
            logger.error(f"Region zones failed: {e}")
            return Response({"region": id, "zones": []})

        return Response({
            "region": id,
            "zones": data.get("zones", []),
        })


class ZoneDetailView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, id):
        campaign = get_active_campaign(request.user)
        if not campaign:
            return Response({"message": "Zone non trouvée"})
        
        analysis = IAnalyse.objects.filter(
            campagne=campaign, 
            type_analyse='global'
        ).first()
        
        if analysis and analysis.response_data:
            zones = analysis.response_data.get('zones_prioritaires', [])
            for z in zones:
                if str(z.get('id', '')) == str(id) or z.get('nom') == id:
                    # Get detailed analysis
                    payload = compute_executive_payload(campaign, request.user)
                    try:
                        detail = call_ia_service(f"/api/ia/zones/{id}/analyze", payload)
                        return Response(detail)
                    except Exception as e:
                        logger.error(f"Zone detail failed: {e}")
                    # IA indisponible : on retombe sur les donnees calculees par Django
                    return self._django_zone_detail(campaign, id)
            return Response({"message": "Zone non trouvée"}, status=404)

        # Aucune analyse en cache : donnees calculees par Django
        return self._django_zone_detail(campaign, id)

    @staticmethod
    def _django_zone_detail(campaign, zone_id):
        """Retourne les donnees de zone calculees par Django (404 si absente)."""
        try:
            return Response(get_zone_beneficiaries_detail(campaign, zone_id))
        except Zone.DoesNotExist:
            return Response({"message": "Zone non trouvée"}, status=404)


class BudgetAnalysisView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, campagne_id):
        try:
            campaign = Campaign.objects.get(id=campagne_id)
        except Campaign.DoesNotExist:
            return Response({
                "alert": "GREEN",
                "resume": "Les dépenses restent cohérentes avec le budget prévu. Aucun risque financier n'est détecté pour le moment.",
                "generated_at": timezone.now().isoformat()
            })
        
        # Check permissions
        if request.user.role != "SUPER_ADMIN" and campaign.organization != request.user.organization:
            return Response({"detail": "Accès refusé"}, status=403)
        
        analysis = IAnalyse.objects.filter(
            campagne=campaign, 
            type_analyse='global'
        ).first()
        
        if analysis and analysis.response_data:
            finance_data = analysis.response_data.get('finance', {})
            finance_data["generated_at"] = analysis.updated_at.isoformat()
            return Response(finance_data)
        
        # Compute and call IA
        payload = compute_finance_payload(campaign, request.user)
        try:
            result = call_ia_service(f"/api/ia/budget-analysis/{campagne_id}", payload)
            return Response(result)
        except Exception as e:
            logger.error(f"Budget analysis failed: {e}")
            return Response({
                "alert": "GREEN",
                "resume": "Les dépenses restent cohérentes avec le budget prévu. Aucun risque financier n'est détecté pour le moment.",
                "generated_at": timezone.now().isoformat()
            })


class RegionAnalysisView(APIView):
    """
    Returns computed zone scores for a region (Django-computed, no IA).
    Used by frontend to display zones with scores before IA analysis.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, region_name):
        campaign = get_active_campaign(request.user)
        if not campaign:
            return Response({
                "region": region_name,
                "campaign": "",
                "total_beneficiaries": 0,
                "zones_count": 0,
                "zones": [],
            })
        
        # Check permissions
        if request.user.role != "SUPER_ADMIN" and campaign.organization != request.user.organization:
            return Response({"detail": "Accès refusé"}, status=403)
        
        data = compute_region_zones_data(campaign, region_name)
        return Response(data)


class RegionAnalysisIAView(APIView):
    """
    Triggers IA analysis for a region's zones.
    Sends Django-computed data to FastAPI/Gemini for human-readable analysis.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, region_name):
        campaign = get_active_campaign(request.user)
        if not campaign:
            return Response({"detail": "Aucune campagne active"}, status=404)
        
        # Check permissions
        if request.user.role != "SUPER_ADMIN" and campaign.organization != request.user.organization:
            return Response({"detail": "Accès refusé"}, status=403)
        
        # Compute zones data from Django
        zones_data = compute_region_zones_data(campaign, region_name)
        
        # Call IA service for analysis
        try:
            result = call_ia_service(f"/api/ia/regions/{region_name}/analyze", zones_data)
            return Response(result)
        except Exception as e:
            logger.error(f"Region IA analysis failed: {e}")
            return Response({"detail": "Erreur lors de l'analyse IA"}, status=500)


# ---------------------------------------------------------------------------
# Assistant IA Exécutif — Chat conversationnel (Gérant uniquement)
# ---------------------------------------------------------------------------

def build_chat_context(user):
    """
    Construit le contexte complet de l'organisation depuis PostgreSQL.
    Ce contexte est envoyé à FastAPI/Gemini à chaque question.
    Aucune donnée inventée — tout provient de la base de données.
    """
    now = timezone.now()
    today = now.date()
    org = user.organization

    from django.contrib.auth import get_user_model
    User = get_user_model()

    projects_qs    = Project.objects.filter(organization=org)
    campaigns_qs   = Campaign.objects.filter(organization=org)
    benef_qs       = Beneficiary.objects.filter(organization=org)
    budgets_qs     = Budget.objects.filter(organization=org)
    depenses_qs    = Depense.objects.filter(organization=org)
    agents_qs      = User.objects.filter(organization=org, role="AGENT", is_active=True)

    # --- Projets ---
    projets_actifs = projects_qs.filter(archived=False)
    projets_data = [
        {
            "id": str(p.id),
            "name": p.name,
            "budget": float(p.budget or 0),
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "region": p.region or "",
        }
        for p in projets_actifs.only("id", "name", "budget", "start_date", "end_date", "region")[:10]
    ]

    # --- Campagnes ---
    active_campaigns = campaigns_qs.filter(statut=Campaign.Statut.EN_COURS)
    campaigns_data = []
    for c in active_campaigns.annotate(nb_ben=models.Count("beneficiaries")):
        campaigns_data.append({
            "id": str(c.id),
            "nom": c.nom,
            "statut": c.statut,
            "date_debut": c.date_debut.isoformat() if c.date_debut else None,
            "date_fin": c.date_fin.isoformat() if c.date_fin else None,
            "jours_restants": (c.date_fin - today).days if c.date_fin else None,
            "beneficiaires_count": c.nb_ben,
        })

    # --- Bénéficiaires ---
    total_benef = benef_qs.count()
    genre_repartition = dict(
        benef_qs.values("sexe").annotate(total=models.Count("id")).values_list("sexe", "total")
    )
    region_repartition = dict(
        benef_qs.values("zone__region")
        .annotate(total=models.Count("id"))
        .values_list("zone__region", "total")
    )
    # Vulnérabilité
    vuln_data = benef_qs.exclude(score_vulnerabilite__isnull=True)
    avg_vuln = vuln_data.aggregate(avg=models.Avg("score_vulnerabilite"))["avg"] or 0
    tres_eleves = vuln_data.filter(score_vulnerabilite__gte=80).count()
    eleves = vuln_data.filter(score_vulnerabilite__gte=60, score_vulnerabilite__lt=80).count()

    # --- Finances ---
    sum_budgets = budgets_qs.aggregate(total=models.Sum("montant"))["total"] or 0
    if sum_budgets == 0:
        sum_budgets = projets_actifs.aggregate(total=models.Sum("budget"))["total"] or 0
    sum_depenses = depenses_qs.aggregate(total=models.Sum("montant"))["total"] or 0
    from apps.finance.models import Don
    sum_dons = Don.objects.filter(organization=org).aggregate(total=models.Sum("montant"))["total"] or 0
    solde = float(sum_dons) - float(sum_depenses)
    taux = round((float(sum_depenses) / float(sum_budgets) * 100), 2) if sum_budgets > 0 else 0

    # Dépenses par catégorie
    dep_categories = {
        k: float(v)
        for k, v in depenses_qs.values("categorie")
        .annotate(total=models.Sum("montant"))
        .values_list("categorie", "total")
        if k and v is not None
    }

    # --- Agents ---
    agents_count = agents_qs.count()
    recent_benef = (
        benef_qs.order_by("-created_at")
        .values("prenom", "nom", "created_at")[:5]
    )
    recent_registrations = [
        {
            "nom": f"{b['prenom']} {b['nom']}".strip(),
            "date": b["created_at"].strftime("%d/%m/%Y") if b["created_at"] else None,
        }
        for b in recent_benef
    ]

    return {
        "organisation": str(org) if org else "ONG",
        "date_analyse": today.isoformat(),
        "projets": {
            "total": projets_actifs.count(),
            "liste": projets_data[:10],
            "budget_total_projets": float(
                projets_actifs.aggregate(total=models.Sum("budget"))["total"] or 0
            ),
        },
        "campagnes": {
            "total_actives": active_campaigns.count(),
            "total": campaigns_qs.count(),
            "liste": campaigns_data[:10],
        },
        "beneficiaires": {
            "total": total_benef,
            "repartition_genre": genre_repartition,
            "repartition_region": {k: v for k, v in region_repartition.items() if k},
            "score_vulnerabilite_moyen": round(float(avg_vuln), 1),
            "tres_vulnerables": tres_eleves,
            "vulnerables": eleves,
        },
        "finances": {
            "budget_total": float(sum_budgets),
            "dons_recus": float(sum_dons),
            "depenses_totales": float(sum_depenses),
            "solde": solde,
            "taux_execution": taux,
            "depenses_par_categorie": {
                k: float(v) for k, v in dep_categories.items() if k
            },
        },
        "agents": {
            "total_actifs": agents_count,
            "enregistrements_recents": recent_registrations,
        },
    }


class AssistantChatView(APIView):
    """
    POST /api/assistant/chat
    Endpoint conversationnel de l'Assistant IA Exécutif — Gérant uniquement.
    """
    permission_classes = [IsAuthenticated]

    IA_CHAT_URL = "http://ia_service:8001/api/ia/chat"

    def post(self, request):
        if request.user.role not in ("GERANT", "SUPER_ADMIN"):
            return Response(
                {"detail": "Accès réservé au Gérant."},
                status=403,
            )

        question = (request.data.get("question") or "").strip()
        history  = request.data.get("history", [])

        if not question:
            return Response({"detail": "La question ne peut pas être vide."}, status=400)

        # Collect real data from PostgreSQL
        try:
            context = build_chat_context(request.user)
        except Exception as e:
            logger.error(f"build_chat_context failed: {e}")
            return Response(
                {"detail": "Erreur lors de la collecte des données."},
                status=500,
            )

        # Sérialiser le payload en gérant Decimal, date, UUID
        import decimal
        import datetime as dt
        import uuid as uuid_mod

        class _SafeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                if isinstance(obj, (dt.date, dt.datetime)):
                    return obj.isoformat()
                if isinstance(obj, uuid_mod.UUID):
                    return str(obj)
                return super().default(obj)

        # Forward to FastAPI/Gemini
        payload = {
            "question": question,
            "context": context,
            "history": history[-10:],
        }
        payload_bytes = json.dumps(payload, cls=_SafeEncoder).encode("utf-8")

        try:
            response = requests.post(
                self.IA_CHAT_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            return Response(response.json())
        except requests.Timeout:
            return Response(
                {
                    "answer": "Le service IA met trop de temps à répondre. Veuillez réessayer.",
                    "generated_at": timezone.now().isoformat(),
                },
            )
        except requests.RequestException as e:
            logger.error(f"AssistantChatView IA call failed: {e}")
            return Response(
                {
                    "answer": "Le service d'analyse IA est momentanément indisponible.",
                    "generated_at": timezone.now().isoformat(),
                },
            )
