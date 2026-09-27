from rest_framework import generics, status, serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response

from drf_spectacular.utils import extend_schema

from .models import User
from .serializers import (
    UserSerializer,
    CreateUserSerializer,
    ActivateAccountSerializer,
    RegisterAuthSerializer,
    ChangePasswordSerializer,
    ResendActivationSerializer,
    AgentListSerializer,
)
from .permissions import (
    IsAccountActive,
    IsGerant,
    IsChefProjet,
    IsSuperAdmin,
)
from .services import (
    create_user_by_manager,
    activate_account,
    register_organization_and_gerant,
    change_password,
    resend_activation,
)


@extend_schema(tags=["Accounts"], summary="Activer un compte")
class ActivateAccountView(generics.GenericAPIView):
    """
    Activation du compte avec le token reçu.
    """
    serializer_class = ActivateAccountSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token = request.query_params.get("token")
        if not token:
            return Response({"detail": "Le token est obligatoire."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = activate_account(token=token, password=None)
        except (ValidationError, ValueError) as exc:
            return Response({"detail": getattr(exc, "detail", str(exc))}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Compte activé avec succès.", "user": UserSerializer(user).data})

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            activate_account(
                token=serializer.validated_data["token"],
                password=serializer.validated_data["password"],
            )
        except ValidationError as e:
            detail = e.detail
            if isinstance(detail, list):
                detail = detail[0]
            return Response(
                {"detail": detail},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"message": "Compte activé avec succès."},
            status=status.HTTP_200_OK,
        )


class RegisterAuthView(generics.GenericAPIView):
    serializer_class = RegisterAuthSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization, user = register_organization_and_gerant(serializer.validated_data)
        return Response({
            "message": "Votre inscription a été enregistrée. Consultez votre email pour activer le compte.",
            "organization": {"id": organization.id, "name": organization.name, "status": organization.status},
            "gerant": {"email": user.email, "status": user.status},
        }, status=status.HTTP_201_CREATED)


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = change_password(
            request.user,
            serializer.validated_data["current_password"],
            serializer.validated_data["new_password"],
        )
        return Response({"message": "Mot de passe modifié avec succès.", "user": UserSerializer(user).data})


class ResendActivationView(generics.GenericAPIView):
    serializer_class = ResendActivationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resend_activation(serializer.validated_data["email"])
        return Response({"message": "Un nouvel email d'activation a été envoyé."})


@extend_schema(tags=["Accounts"], summary="Liste des utilisateurs")
class UserListView(generics.ListAPIView):
    """
    Le Gérant consulte les utilisateurs de son ONG.
    """
    serializer_class = UserSerializer
    permission_classes = [
        IsAuthenticated,
        IsAccountActive,
        IsGerant,
    ]

    def get_queryset(self):
        return User.objects.filter(
            organization=self.request.user.organization
        ).order_by("first_name")


@extend_schema(tags=["Accounts"], summary="Créer un utilisateur")
class UserCreateView(generics.CreateAPIView):
    """
    Le Gérant crée un Chef de projet,
    un Responsable Finance ou un Agent.
    """
    serializer_class = CreateUserSerializer
    permission_classes = [
        IsAuthenticated,
        IsAccountActive,
        IsGerant,
    ]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = create_user_by_manager(
            organization=request.user.organization,
            first_name=serializer.validated_data["first_name"],
            last_name=serializer.validated_data["last_name"],
            email=serializer.validated_data["email"],
            phone=serializer.validated_data["phone"],
            role=serializer.validated_data["role"],
        )

        return Response(
            {
                "message": "Invitation envoyée avec succès.",
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Accounts"], summary="Profil de l'utilisateur connecté")
class MeView(generics.RetrieveAPIView):
    """
    Retourne le profil de l'utilisateur actuellement authentifié.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


@extend_schema(tags=["Accounts"], summary="Détail et mise à jour d'un collaborateur (activation/désactivation)")
class UserDetailView(generics.RetrieveUpdateAPIView):
    """
    Le Gérant consulte le détail d'un utilisateur de son ONG
    et peut l'activer ou le désactiver (suspendre).
    """
    serializer_class = UserSerializer
    permission_classes = [
        IsAuthenticated,
        IsAccountActive,
        IsGerant,
    ]

    def get_queryset(self):
        return User.objects.filter(
            organization=self.request.user.organization
        )

    def patch(self, request, *args, **kwargs):
        user = self.get_object()
        new_status = request.data.get("status")
        is_active = request.data.get("is_active")

        if new_status:
            if new_status not in [User.Status.ACTIVE, User.Status.SUSPENDED, User.Status.INVITED]:
                return Response(
                    {"detail": "Statut invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.status = new_status
            if new_status == User.Status.SUSPENDED:
                user.is_active = False
            elif new_status == User.Status.ACTIVE:
                user.is_active = True

        if is_active is not None:
            user.is_active = bool(is_active)
            if not user.is_active:
                user.status = User.Status.SUSPENDED
            elif user.status == User.Status.SUSPENDED:
                user.status = User.Status.ACTIVE

        user.save()
        return Response(UserSerializer(user).data)


@extend_schema(tags=["Accounts"], summary="Liste des agents terrain de l'ONG")
class AgentListView(generics.ListAPIView):
    """
    Liste les agents terrain (et chefs de projet) de la même ONG,
    pour l'affectation d'une campagne par le chef de projet.
    """

    serializer_class = AgentListSerializer
    permission_classes = [IsAuthenticated, IsAccountActive, IsChefProjet]

    def get_queryset(self):
        return User.objects.filter(
            organization=self.request.user.organization,
            role__in=[User.Role.AGENT, User.Role.CHEF_PROJET],
            is_active=True,
        ).order_by("last_name", "first_name")

# Serializer pour le Super Admin avec infos complètes de l'ONG
class GerantWithOrganizationSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    region = serializers.SerializerMethodField()
    status_ong = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "organization",
            "region",
            "status_ong",
            "status",
            "is_active",
            "must_change_password",
            "date_joined",
        ]

    def get_organization(self, obj):
        if obj.organization:
            return {
                "id": obj.organization.id,
                "name": obj.organization.name,
                "acronym": obj.organization.acronym,
                "email": obj.organization.email,
                "phone": obj.organization.phone,
            }
        return None

    def get_region(self, obj):
        return obj.organization.region if obj.organization else None

    def get_status_ong(self, obj):
        return obj.organization.status if obj.organization else None


@extend_schema(tags=["Accounts"], summary="Liste des gérunts (Super Admin)")
class GerantListView(generics.ListAPIView):
    """
    Liste de tous les gérunts de toutes les ONG. Réservé au Super Admin.
    """
    serializer_class = GerantWithOrganizationSerializer
    permission_classes = [IsAuthenticated, IsAccountActive, IsSuperAdmin]

    def get_queryset(self):
        return User.objects.filter(
            role=User.Role.GERANT,
            organization__isnull=False,
        ).select_related('organization').order_by('organization__name', 'last_name', 'first_name')