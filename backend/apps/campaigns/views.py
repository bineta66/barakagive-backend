from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from apps.projects.models import Project
from apps.zones.models import Zone
from .models import Campaign
from .serializers import (
    AgentZonesAssignmentSerializer,
    CampagneAffectationSerializer,
    CampaignListSerializer,
    CampaignDetailSerializer,
    CampaignCreateSerializer,
    CampaignUpdateSerializer,
)
from .permissions import (
    IsChefProjetOrGerant,
    IsChefProjetOnly,
    CanManageCampaign,
)
from .services import (
    create_campaign,
    validate_zones_for_organization,
    validate_dates,
    validate_project_for_chef_projet,
)


@extend_schema(tags=["Campagnes"])
class CampaignListCreateView(APIView):
    """
    GET /api/campaigns/ - Liste des campagnes de l'ONG
    POST /api/campaigns/ - Création d'une campagne (CHEF_PROJET uniquement)
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsChefProjetOnly()]
        return [IsAuthenticated(), IsChefProjetOrGerant()]

    @extend_schema(
        responses={200: CampaignListSerializer(many=True)},
    )
    def get(self, request):
        """Liste les campagnes de l'ONG de l'utilisateur connecté."""
        campaigns = Campaign.objects.select_related(
            "projet", "created_by"
        ).prefetch_related(
            "zones"
        ).order_by("-created_at")

        if request.user.role != "SUPER_ADMIN":
            campaigns = campaigns.filter(organization=request.user.organization)
        if request.user.role == "AGENT":
            campaigns = campaigns.filter(affectations__agent=request.user).distinct()

        serializer = CampaignListSerializer(campaigns, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=CampaignCreateSerializer,
        responses={201: CampaignDetailSerializer},
    )
    def post(self, request):
        """
        Crée une nouvelle campagne.

        Vérifications effectuées :
         Authentification JWT
         Rôle = CHEF_PROJET
         Projet existe, appartient à la même ONG, chef de projet affecté
         Zones existent, appartiennent à la même ONG, au moins une zone
        date_fin > date_debut
        """
        serializer = CampaignCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            campaign = create_campaign(serializer.validated_data, request.user)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        detail_serializer = CampaignDetailSerializer(campaign)
        return Response(
            {
                "id": campaign.id,
                "code_campagne": campaign.code_campagne,
                "message": "Campagne créée avec succès.",
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Campagnes"])
class CampaignDetailView(APIView):
    """
    GET /api/campaigns/{id}/ - Détail d'une campagne
    PATCH /api/campaigns/{id}/ - Modification (CHEF_PROJET uniquement)
    DELETE /api/campaigns/{id}/ - Suppression (CHEF_PROJET uniquement)
    """

    def get_object(self, pk, user):
        try:
            queryset = Campaign.objects.select_related(
                "projet", "created_by", "organization"
            ).prefetch_related(
                "zones"
            ).filter(pk=pk)
            if user.role != "SUPER_ADMIN":
                queryset = queryset.filter(organization=user.organization)
            if user.role == "AGENT":
                # Un agent peut avoir plusieurs affectations (une par zone),
                # d'ou le distinct pour eviter les doublons de jointure.
                queryset = queryset.filter(affectations__agent=user).distinct()
            return queryset.get()
        except (Campaign.DoesNotExist, Campaign.MultipleObjectsReturned):
            return None

    def get_permissions(self):
        if self.request.method in ["PATCH", "DELETE"]:
            return [IsAuthenticated(), IsChefProjetOnly(), CanManageCampaign()]
        return [IsAuthenticated(), IsChefProjetOrGerant()]

    @extend_schema(
        responses={200: CampaignDetailSerializer},
    )
    def get(self, request, pk):
        """Retourne le détail complet d'une campagne."""
        campaign = self.get_object(pk, request.user)
        if not campaign:
            return Response(
                {"detail": "Campagne non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CampaignDetailSerializer(campaign)
        return Response(serializer.data)

    @extend_schema(
        request=CampaignUpdateSerializer,
        responses={200: CampaignDetailSerializer},
    )
    def patch(self, request, pk):
        """
        Met à jour une campagne.
        Champs modifiables : nom, description, zone_ids, date_debut, date_fin
        Non modifiables : code_campagne, organization, created_by, projet
        """
        campaign = self.get_object(pk, request.user)
        if not campaign:
            return Response(
                {"detail": "Campagne non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, campaign)

        serializer = CampaignUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        if "nom" in validated_data:
            campaign.nom = validated_data["nom"]

        if "description" in validated_data:
            campaign.description = validated_data["description"]

        if "zone_ids" in validated_data:
            zone_ids = validated_data["zone_ids"]
            try:
                zones = validate_zones_for_organization(zone_ids, request.user.organization)
                campaign.zones.set(zones)
            except ValueError as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if "date_debut" in validated_data or "date_fin" in validated_data:
            new_date_debut = validated_data.get("date_debut", campaign.date_debut)
            new_date_fin = validated_data.get("date_fin", campaign.date_fin)
            try:
                validate_dates(new_date_debut, new_date_fin)
            except ValueError as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            campaign.date_debut = new_date_debut
            campaign.date_fin = new_date_fin

        campaign.save()

        detail_serializer = CampaignDetailSerializer(campaign)
        return Response(detail_serializer.data)

    @extend_schema(
        responses={204: None},
    )
    def delete(self, request, pk):
        """Supprime une campagne (CHEF_PROJET uniquement)."""
        campaign = self.get_object(pk, request.user)
        if not campaign:
            return Response(
                {"detail": "Campagne non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, campaign)

        campaign.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

@extend_schema(tags=["Campagnes"])
class CampaignAgentZonesView(APIView):
    """
    GET /api/campaigns/{pk}/agents/zones/
    PUT /api/campaigns/{pk}/agents/zones/

    GET : liste les affectations de la campagne, regroupees par agent.
    PUT : affecte un agent terrain a une ou plusieurs zones de la campagne.
    Corps attendu :
        {"agent_id": 42, "zones": ["Dakar Nord", "Dakar Sud"], "objectif": 50}

    L'appel definit l'ensemble des zones de l'agent : les zones absentes de la
    liste voient leur affectation supprimee.
    """

    permission_classes = [IsChefProjetOrGerant, CanManageCampaign]

    def get(self, request, pk):
        # Liste les affectations de la campagne, regroupees par agent.
        # Un agent peut intervenir dans plusieurs zones.
        campaign = CampaignDetailView().get_object(pk, request.user)
        if not campaign:
            return Response(
                {"detail": "Campagne non trouvée."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, campaign)

        from apps.campaigns.models import CampagneAffectation
        affectations = (
            CampagneAffectation.objects
            .filter(campagne=campaign)
            .select_related("agent")
            .order_by("agent__last_name", "agent__first_name", "zone")
        )

        par_agent = {}
        for affectation in affectations:
            agent = affectation.agent
            key = str(agent.id)
            if key not in par_agent:
                par_agent[key] = {
                    "agent": {
                        "id": str(agent.id),
                        "full_name": agent.full_name,
                        "email": agent.email,
                    },
                    "zones": [],
                    "objectif": affectation.objectif_beneficiaires,
                    "statut": affectation.statut,
                }
            par_agent[key]["zones"].append(affectation.zone)

        zones_campagne = list(
            campaign.zones.values_list("nom", flat=True).order_by("nom")
        )

        return Response(
            {
                "campagne": str(campaign.id),
                "zones_campagne": zones_campagne,
                "affectations": list(par_agent.values()),
            }
        )

    def put(self, request, pk):
        from apps.accounts.models import User
        from .services import assign_agent_zones

        campaign = CampaignDetailView().get_object(pk, request.user)
        if not campaign:
            return Response(
                {"detail": "Campagne non trouvée."},
                status=status.HTTP_404_NOT_FOUND,
            )

        self.check_object_permissions(request, campaign)

        serializer = AgentZonesAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            agent = User.objects.get(
                id=data["agent_id"],
                organization=campaign.organization,
            )
        except User.DoesNotExist:
            return Response(
                {"detail": "Agent introuvable dans cette ONG."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            affectations = assign_agent_zones(
                campaign=campaign,
                agent=agent,
                zone_names=data["zones"],
                objectif=data.get("objectif", 0),
                user=request.user,
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "agent": {
                    "id": agent.id,
                    "full_name": agent.full_name,
                    "email": agent.email,
                },
                "zones": [a.zone for a in affectations],
                "affectations": CampagneAffectationSerializer(
                    affectations, many=True
                ).data,
            }
        )
