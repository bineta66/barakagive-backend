from django.db.models import Sum, Q
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
import requests
import logging

logger = logging.getLogger(__name__)

from .models import Budget, Don, Depense, Justification, Bailleur, Partenaire
from .serializers import (
    BudgetSerializer,
    DonSerializer,
    DepenseSerializer,
    JustificationSerializer,
    BailleurSerializer,
    PartenaireSerializer,
)
from .permissions import FinancePermission
from .services import prepare_budget_analysis


# -------------------------------------------------------------------
# Pagination personnalisée
# -------------------------------------------------------------------
class FinancePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# -------------------------------------------------------------------
# Filtre Organisation
# -------------------------------------------------------------------
class FinanceQuerysetMixin:
    def get_queryset(self):
        queryset = self.queryset
        # Si l'utilisateur a une organisation, filtrer par organisation
        if self.request.user.organization:
            queryset = queryset.filter(organization=self.request.user.organization)
        # Pour GERANT, SUPER_ADMIN et FINANCE sans organisation, retourner tout
        elif self.request.user.role in ["GERANT", "SUPER_ADMIN", "FINANCE"]:
            queryset = queryset
        else:
            queryset = queryset.none()
        return queryset


# -------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------
class FinanceDashboardView(APIView):
    permission_classes = [FinancePermission]

    def get(self, request):
        org = request.user.organization

        if org is None:
            return Response({
                "budget_total": 0,
                "dons_recus": 0,
                "depenses_totales": 0,
                "solde": 0,
                "taux_execution": 0,
            })

        budget_total = (
            Budget.objects.filter(organization=org)
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        dons_total = (
            Don.objects.filter(organization=org)
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        depenses_total = (
            Depense.objects.filter(organization=org)
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        solde = dons_total - depenses_total

        taux = 0
        if budget_total > 0:
            taux = round((depenses_total / budget_total) * 100, 2)

        return Response({
            "budget_total": budget_total,
            "dons_recus": dons_total,
            "depenses_totales": depenses_total,
            "solde": solde,
            "taux_execution": taux,
        })


# -------------------------------------------------------------------
# Budgets
# -------------------------------------------------------------------
class BudgetListCreateView(FinanceQuerysetMixin, generics.ListCreateAPIView):
    queryset = Budget.objects.select_related("projet")
    serializer_class = BudgetSerializer
    permission_classes = [FinancePermission]

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user,
        )


class BudgetDetailView(FinanceQuerysetMixin,
                       generics.RetrieveUpdateDestroyAPIView):
    queryset = Budget.objects.all()
    serializer_class = BudgetSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"


# -------------------------------------------------------------------
# Dons
# -------------------------------------------------------------------
class DonListCreateView(FinanceQuerysetMixin, generics.ListCreateAPIView):
    queryset = Don.objects.select_related(
        "budget__projet", "campagne", "budget"
    )
    serializer_class = DonSerializer
    permission_classes = [FinancePermission]

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user,
        )


class DonDetailView(FinanceQuerysetMixin,
                    generics.RetrieveUpdateDestroyAPIView):
    queryset = Don.objects.all()
    serializer_class = DonSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"


# -------------------------------------------------------------------
# Dépenses
# -------------------------------------------------------------------
class DepenseListCreateView(FinanceQuerysetMixin,
                            generics.ListCreateAPIView):
    queryset = Depense.objects.select_related("budget__projet", "campagne").prefetch_related("justifications")
    serializer_class = DepenseSerializer
    permission_classes = [FinancePermission]

    def perform_create(self, serializer):
        region = serializer.validated_data.get("region")
        if not region:
            from apps.zones.models import Region
            from django.contrib.gis.geos import Polygon
            if not Region.objects.exists():
                poly = Polygon(((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)))
                Region.objects.create(nom="Dakar", geometrie=poly)
            region = Region.objects.first()
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user,
            region=region,
        )


class DepenseDetailView(FinanceQuerysetMixin,
                        generics.RetrieveUpdateDestroyAPIView):
    queryset = Depense.objects.all()
    serializer_class = DepenseSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"


# -------------------------------------------------------------------
# Justifications
# -------------------------------------------------------------------
class JustificationListCreateView(generics.ListCreateAPIView):
    serializer_class = JustificationSerializer
    permission_classes = [FinancePermission]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return Justification.objects.filter(
            depense_id=self.kwargs["depense_id"],
            depense__organization=self.request.user.organization,
        )

    def perform_create(self, serializer):
        serializer.save(
            depense_id=self.kwargs["depense_id"],
            uploaded_by=self.request.user,
        )


class JustificationDetailView(generics.DestroyAPIView):
    serializer_class = JustificationSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"

    def get_queryset(self):
        return Justification.objects.filter(
            depense__organization=self.request.user.organization
        )


# -------------------------------------------------------------------
# Assistant IA
# -------------------------------------------------------------------
class BudgetAnalysisView(APIView):
    permission_classes = [FinancePermission]

    FASTAPI_URL = "http://ia_service:8001/api/ia/budget-analysis"

    def get(self, request, campaign_id):

        financial_data = prepare_budget_analysis(campaign_id)

        try:
            response = requests.post(
                self.FASTAPI_URL,
                json=financial_data,
                timeout=8,
            )

            response.raise_for_status()

            return Response({
                "financial_data": financial_data,
                "ia_analysis": response.json(),
            })

        except requests.RequestException:
            return Response(
                {
                    "financial_data": financial_data,
                    "ia_analysis": None,
                    "message": "Service IA indisponible",
                },
                status=status.HTTP_200_OK,
            )


# -------------------------------------------------------------------
# Bailleurs
# -------------------------------------------------------------------
class BailleurListCreateView(FinanceQuerysetMixin, generics.ListCreateAPIView):
    queryset = Bailleur.objects.all()
    serializer_class = BailleurSerializer
    permission_classes = [FinancePermission]

    def perform_create(self, serializer):
        org = self.request.user.organization
        if org is None and self.request.user.role in ["SUPER_ADMIN", "GERANT"]:
            from apps.organizations.models import Organization
            org = Organization.objects.first()
        serializer.save(organization=org)


class BailleurDetailView(FinanceQuerysetMixin,
                         generics.RetrieveUpdateDestroyAPIView):
    queryset = Bailleur.objects.all()
    serializer_class = BailleurSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"


# -------------------------------------------------------------------
# Partenaires
# -------------------------------------------------------------------
class PartenaireListCreateView(FinanceQuerysetMixin, generics.ListCreateAPIView):
    queryset = Partenaire.objects.all()
    serializer_class = PartenaireSerializer
    permission_classes = [FinancePermission]

    def perform_create(self, serializer):
        org = self.request.user.organization
        if org is None and self.request.user.role in ["SUPER_ADMIN", "GERANT"]:
            from apps.organizations.models import Organization
            org = Organization.objects.first()
        serializer.save(organization=org)


class PartenaireDetailView(FinanceQuerysetMixin,
                           generics.RetrieveUpdateDestroyAPIView):
    queryset = Partenaire.objects.all()
    serializer_class = PartenaireSerializer
    permission_classes = [FinancePermission]
    lookup_field = "id"


# -------------------------------------------------------------------
# Assistant IA Finance — Chat conversationnel
# -------------------------------------------------------------------
import json
import decimal
import datetime as dt
import uuid as uuid_mod
import logging

logger = logging.getLogger(__name__)


def build_finance_chat_context(user):
    """
    Collecte toutes les données financières réelles depuis PostgreSQL.
    Aucune donnée fictive — tout provient de la base de données.
    """
    from django.utils import timezone
    from django.db.models import Sum, Count, Avg
    from apps.campaigns.models import Campaign

    org  = user.organization
    now  = timezone.now()
    today = now.date()

    # ── Budgets ──────────────────────────────────────────────────────
    budgets_qs = Budget.objects.filter(organization=org).select_related("projet")
    budget_total = budgets_qs.aggregate(total=Sum("montant"))["total"] or 0

    budgets_data = [
        {
            "id":               str(b.id),
            "projet":           b.projet.name if b.projet else "—",
            "montant":          float(b.montant),
            "statut":           b.statut,
            "source":           b.source_financement,
            "date":             b.date.isoformat() if b.date else None,
            "total_dons":       float(b.total_dons),
            "total_depenses":   float(b.total_depenses),
            "solde":            float(b.solde),
            "taux_execution":   float(b.taux_execution),
        }
        for b in budgets_qs[:15]
    ]

    # ── Dons ─────────────────────────────────────────────────────────
    dons_qs     = Don.objects.filter(organization=org)
    dons_total  = dons_qs.aggregate(total=Sum("montant"))["total"] or 0

    dons_data = [
        {
            "reference":        d.reference,
            "bailleur":         d.bailleur,
            "montant":          float(d.montant),
            "moyen_paiement":   d.moyen_paiement,
            "date":             d.date.isoformat() if d.date else None,
            "campagne":         d.campagne.nom if d.campagne else None,
        }
        for d in dons_qs.order_by("-date")[:10]
    ]

    # ── Dépenses ─────────────────────────────────────────────────────
    depenses_qs    = Depense.objects.filter(organization=org)
    depenses_total = depenses_qs.aggregate(total=Sum("montant"))["total"] or 0

    dep_par_categorie = {
        k: float(v)
        for k, v in depenses_qs.values("categorie")
        .annotate(total=Sum("montant"))
        .values_list("categorie", "total")
        if k and v is not None
    }

    dep_par_region = {
        k: float(v)
        for k, v in depenses_qs.values("region__nom")
        .annotate(total=Sum("montant"))
        .values_list("region__nom", "total")
        if k and v is not None
    }

    dep_par_statut = dict(
        depenses_qs.values("statut")
        .annotate(nb=Count("id"))
        .values_list("statut", "nb")
    )

    # Dépenses des 14 derniers jours vs 14 précédents (détection accélération)
    from datetime import timedelta
    cutoff_14  = today - timedelta(days=14)
    cutoff_28  = today - timedelta(days=28)
    dep_14j    = float(depenses_qs.filter(date__gte=cutoff_14)
                       .aggregate(t=Sum("montant"))["t"] or 0)
    dep_14_28j = float(depenses_qs.filter(date__gte=cutoff_28, date__lt=cutoff_14)
                       .aggregate(t=Sum("montant"))["t"] or 0)

    # ── Justificatifs ─────────────────────────────────────────────────
    just_qs = Justification.objects.filter(depense__organization=org)
    total_just     = just_qs.count()
    conformes      = just_qs.filter(statut="CONFORME").count()
    a_verifier     = just_qs.filter(statut="A_VERIFIER").count()
    non_conformes  = just_qs.filter(statut="NON_CONFORME").count()

    taux_conformite = round((conformes / total_just * 100), 1) if total_just > 0 else 0

    # Dépenses sans aucun justificatif
    depenses_sans_just = int(
        depenses_qs.annotate(nb_just=Count("justifications"))
        .filter(nb_just=0).count()
    )

    # ── Campagnes ─────────────────────────────────────────────────────
    campaigns_actives = Campaign.objects.filter(
        organization=org, statut=Campaign.Statut.EN_COURS
    )
    campaigns_data = [
        {
            "id":             str(c.id),
            "nom":            c.nom,
            "date_debut":     c.date_debut.isoformat() if c.date_debut else None,
            "date_fin":       c.date_fin.isoformat() if c.date_fin else None,
            "jours_restants": (c.date_fin - today).days if c.date_fin else None,
        }
        for c in campaigns_actives[:10]
    ]

    # ── Calculs globaux ───────────────────────────────────────────────
    solde = float(dons_total) - float(depenses_total)
    taux  = round((float(depenses_total) / float(budget_total) * 100), 2) if budget_total > 0 else 0

    return {
        "organisation":     str(org) if org else "ONG",
        "date_analyse":     today.isoformat(),
        "finances": {
            "budget_total":              float(budget_total),
            "dons_recus":                float(dons_total),
            "depenses_totales":          float(depenses_total),
            "solde":                     solde,
            "taux_execution":            taux,
            "depenses_par_categorie":    dep_par_categorie,
            "depenses_par_region":       dep_par_region,
            "depenses_par_statut":       dep_par_statut,
            "depenses_14_derniers_jours": dep_14j,
            "depenses_14_28_jours":       dep_14_28j,
        },
        "budgets": {
            "total":  int(budgets_qs.count()),
            "liste":  budgets_data,
        },
        "dons": {
            "total":  int(dons_qs.count()),
            "recents": dons_data,
        },
        "justificatifs": {
            "total":              total_just,
            "conformes":          conformes,
            "a_verifier":         a_verifier,
            "non_conformes":      non_conformes,
            "taux_conformite":    taux_conformite,
            "depenses_sans_just": depenses_sans_just,
        },
        "campagnes": {
            "total_actives":  int(campaigns_actives.count()),
            "liste":          campaigns_data,
        },
    }


class FinanceAssistantChatView(APIView):
    """
    POST /api/finance/assistant/chat/
    Assistant IA conversationnel pour le Responsable Finance.
    Utilise les vraies données PostgreSQL — aucune donnée fictive.
    """
    permission_classes = [FinancePermission]

    IA_CHAT_URL = "http://ia_service:8001/api/ia/finance-chat"

    def post(self, request):
        question = (request.data.get("question") or "").strip()
        history  = request.data.get("history", [])

        if not question:
            return Response({"detail": "La question ne peut pas être vide."}, status=400)

        try:
            context = build_finance_chat_context(request.user)
        except Exception as e:
            logger.error(f"build_finance_chat_context failed: {e}")
            return Response({"detail": "Erreur lors de la collecte des données financières."}, status=500)

        class _SafeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                if isinstance(obj, (dt.date, dt.datetime)):
                    return obj.isoformat()
                if isinstance(obj, uuid_mod.UUID):
                    return str(obj)
                return super().default(obj)

        payload_bytes = json.dumps(
            {"question": question, "context": context, "history": history[-10:]},
            cls=_SafeEncoder,
        ).encode("utf-8")

        try:
            resp = requests.post(
                self.IA_CHAT_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json"},
                timeout=60,
            )
            resp.raise_for_status()
            return Response(resp.json())
        except requests.Timeout:
            return Response({
                "answer": "Le service IA met trop de temps à répondre. Veuillez réessayer.",
                "generated_at": str(dt.datetime.utcnow().isoformat()) + "Z",
            })
        except requests.RequestException as e:
            logger.error(f"FinanceAssistantChatView IA call failed: {e}")
            return Response({
                "answer": "Le service d'analyse IA est momentanément indisponible.",
                "generated_at": str(dt.datetime.utcnow().isoformat()) + "Z",
            })
# -------------------------------------------------------------------
# Budgets - Approuver (Gérant)
# -------------------------------------------------------------------
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as http_status


class BudgetApprovalView(APIView):
    """
    Vue pour permettre au Gérant d'approuver les budgets en attente.
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == 'GET':
            # Gérant et Super Admin peuvent voir les budgets
            return [perm() for perm in self.permission_classes]
        # Pour POST, seul le Gérant peut approuver/rejeter
        from apps.accounts.permissions import IsGerant
        return [IsGerant()]

    def get(self, request):
        # Le gérant voit les budgets de son organisation
        org = request.user.organization
        budgets = Budget.objects.filter(
            organization=org,
            statut__in=[Budget.Status.BROUILLON, Budget.Status.EN_COURS]
        ).select_related("projet").order_by("-created_at")
        
        from .serializers import BudgetSerializer
        serializer = BudgetSerializer(budgets, many=True)
        return Response(serializer.data)

    def post(self, request):
        """Approuver ou rejeter un budget"""
        budget_id = request.data.get("budget_id")
        action_type = request.data.get("action", "").upper()
        
        if not budget_id:
            return Response(
                {"error": "budget_id est requis"},
                status=http_status.HTTP_400_BAD_REQUEST
            )
        
        # Accepter aussi bien "approve" que "APPROUVER"
        if action_type in ["APPROVE", "APPROUVER"]:
            action_type = "APPROUVER"
        elif action_type in ["REJECT", "REJETER"]:
            action_type = "REJETER"
        
        try:
            budget = Budget.objects.get(id=budget_id, organization=request.user.organization)
        except Budget.DoesNotExist:
            return Response(
                {"error": "Budget non trouvé"},
                status=http_status.HTTP_404_NOT_FOUND
            )
        
        if action_type == "APPROUVER":
            budget.statut = Budget.Status.APPROUVE
            budget.save()
            return Response({"message": "Budget approuvé", "statut": budget.statut})
        elif action_type == "REJETER":
            budget.statut = Budget.Status.BROUILLON
            budget.save()
            return Response({"message": "Budget rejeté", "statut": budget.statut})
        else:
            return Response(
                {"error": f"Action invalide: {action_type}"},
                status=http_status.HTTP_400_BAD_REQUEST
            )