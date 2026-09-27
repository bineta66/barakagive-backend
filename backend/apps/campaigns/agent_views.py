from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

from apps.beneficiaries.models import Beneficiary
from apps.beneficiaries.serializers import BeneficiaryCreateSerializer, BeneficiaryDetailSerializer
from apps.beneficiaries.services import BeneficiaryError, create_beneficiary_with_responses
from apps.forms.models import Formulaire
from apps.forms.serializers import FormulaireDetailSerializer
from apps.zones.models import Zone
from .models import Campaign, CampagneAffectation
from .serializers import AgentCampagneSerializer, AgentDashboardSerializer


class AgentOnly(IsAuthenticated):
    """Permission locale réservée aux agents terrain actifs."""

    def has_permission(self, request, view):
        return super().has_permission(request, view) and request.user.role == "AGENT" and request.user.can_login


def assigned_campaign_or_404(pk, user):
    campaign = get_object_or_404(
        Campaign.objects.select_related("projet").prefetch_related("affectations"),
        pk=pk,
    )
    if not campaign.affectations.filter(agent=user).exists():
        raise PermissionDenied("Vous n'êtes pas affecté à cette campagne.")
    return campaign


class AgentCampaignListView(APIView):
    permission_classes = [AgentOnly]

    def get(self, request):
        campaigns = (
            Campaign.objects.filter(affectations__agent=request.user)
            .select_related("projet")
            .prefetch_related("affectations")
            .annotate(
                collectes=Count(
                    "beneficiaries",
                    filter=Q(beneficiaries__created_by=request.user),
                    distinct=True,
                )
            )
            .distinct()
        )
        context = {"agent": request.user}
        return Response(
            AgentCampagneSerializer(campaigns, many=True, context=context).data
        )


class AgentDashboardView(APIView):
    permission_classes = [AgentOnly]

    def get(self, request):
        today = timezone.now().date()
        assignments = CampagneAffectation.objects.filter(
            agent=request.user,
            campagne__date_debut__lte=today,
            campagne__date_fin__gte=today,
        )
        beneficiaries = Beneficiary.objects.filter(
            created_by=request.user,
            campagne__affectations__agent=request.user,
        ).distinct()
        objectif_total = assignments.aggregate(total=Sum("objectif_beneficiaires"))["total"] or 0
        count = beneficiaries.count()
        data = {
            "agent": request.user.full_name,
            "campagnes_actives": assignments.values("campagne_id").distinct().count(),
            "beneficiaires_enregistres": count,
            "objectif_total": objectif_total,
            "progression": round((count / objectif_total) * 100, 1) if objectif_total else 0.0,
        }
        return Response(AgentDashboardSerializer(data).data)


class AgentCampaignFormView(APIView):
    permission_classes = [AgentOnly]

    def get(self, request, pk):
        campaign = assigned_campaign_or_404(pk, request.user)
        formulaire = (
            Formulaire.objects.filter(
                campagne=campaign,
                statut=Formulaire.Statut.PUBLIE,
            )
            .prefetch_related("fields")
            .first()
        )
        if not formulaire:
            return Response(
                {"detail": "Aucun formulaire publié pour cette campagne."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(FormulaireDetailSerializer(formulaire).data)


class AgentCampaignBeneficiaryCreateView(APIView):
    permission_classes = [AgentOnly]

    def get(self, request, pk):
        campaign = assigned_campaign_or_404(pk, request.user)
        beneficiaries = Beneficiary.objects.filter(
            campagne=campaign,
            created_by=request.user,
        ).select_related("zone", "campagne").order_by("-created_at")
        return Response(BeneficiaryDetailSerializer(beneficiaries, many=True).data)

    def post(self, request, pk):
        campaign = assigned_campaign_or_404(pk, request.user)
        data = request.data.copy()
        data["campagne_id"] = str(pk)
        if not data.get("zone_id"):
            # Un agent peut etre affecte a plusieurs zones : on retient la
            # premiere affectation comme zone par defaut.
            assigned_zone_names = list(
                campaign.affectations.filter(agent=request.user)
                .values_list("zone", flat=True)
            )
            if assigned_zone_names:
                zone = Zone.objects.filter(
                    organization=request.user.organization,
                    nom=assigned_zone_names[0],
                ).first()
                if zone:
                    data["zone_id"] = str(zone.id)
        serializer = BeneficiaryCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            beneficiary, responses, _ = create_beneficiary_with_responses(
                serializer.validated_data,
                request.user,
            )
        except BeneficiaryError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BeneficiaryDetailSerializer(beneficiary).data, status=status.HTTP_201_CREATED)


class AgentSynchronizationView(APIView):
    permission_classes = [AgentOnly]

    def get(self, request):
        pending = Beneficiary.objects.filter(
            created_by=request.user,
            sync_status=Beneficiary.SyncStatus.PENDING,
        ).count()
        campaigns = AgentCampaignListView().get(request).data
        last_sync = Beneficiary.objects.filter(
            created_by=request.user,
        ).order_by("-updated_at").values_list("updated_at", flat=True).first()
        return Response({
            "last_sync": last_sync,
            "pending": pending,
            "campagnes": campaigns,
        })

    def post(self, request):
        records = request.data if isinstance(request.data, list) else request.data.get("beneficiaires", [])
        synced = []
        errors = []
        for record in records:
            serializer = BeneficiaryCreateSerializer(data=record)
            if not serializer.is_valid():
                errors.append(serializer.errors)
                continue
            try:
                beneficiary, _, _ = create_beneficiary_with_responses(serializer.validated_data, request.user)
                synced.append(str(beneficiary.id))
            except BeneficiaryError as exc:
                errors.append({"detail": str(exc)})
        return Response({"synced": synced, "errors": errors}, status=status.HTTP_200_OK)
