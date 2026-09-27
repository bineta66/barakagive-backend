from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from .models import Organization, Subscription
from .serializers import (
    OrganizationSerializer,
    RegisterOrganizationSerializer,
)
from apps.accounts.models import User, ActivationToken
from apps.accounts.tasks import send_invitation_email


def _get_super_admin_emails():
    return list(
        User.objects.filter(role=User.Role.SUPER_ADMIN, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def _send_new_registration_email(organization, manager):
    super_admin_emails = _get_super_admin_emails()
    if not super_admin_emails:
        return

    subject = "Nouvelle demande d'inscription ONG"
    html = f"""
    <h2>Nouvelle demande d'inscription ONG</h2>
    <p>Une nouvelle ONG souhaite rejoindre BarakaGive360.</p>
    <ul>
        <li><strong>Nom ONG :</strong> {organization.name}</li>
        <li><strong>Domaine :</strong> {organization.intervention_domain}</li>
        <li><strong>Gérant :</strong> {manager.first_name} {manager.last_name}</li>
        <li><strong>Email :</strong> {manager.email}</li>
        <li><strong>Téléphone :</strong> {manager.phone}</li>
        <li><strong>Date :</strong> {timezone.now().strftime('%d/%m/%Y %H:%M')}</li>
    </ul>
    """

    for email in super_admin_emails:
        send_invitation_email.delay(
            recipient_email=email,
            first_name="Super Admin",
            activation_link="",
            temporary_password=None,
            subject_override=subject,
            html_override=html,
        )


@extend_schema(tags=["Organisations"], summary="Inscription d'une ONG")
class RegisterOrganizationView(generics.CreateAPIView):
    """
    Inscription publique d'une ONG.
    Crée automatiquement le premier Gérant.
    """

    queryset = Organization.objects.all()
    serializer_class = RegisterOrganizationSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["documents"] = {
            "receipt": self.request.data.get("document_receipt"),
            "ninea": self.request.data.get("document_ninea"),
            "statutes": self.request.data.get("document_statutes"),
        }
        return context

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        organization, manager = serializer.save()

        _send_new_registration_email(organization, manager)

        return Response(
            {
                "message": "Demande envoyée avec succès.",
                "organization": {
                    "id": organization.id,
                    "name": organization.name,
                    "status": organization.status,
                },
                "gerant": {
                    "email": manager.email,
                    "status": manager.status,
                },
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Organisations"], summary="Liste des ONG")
class OrganizationListView(generics.ListAPIView):
    """
    Liste des ONG.
    (Plus tard : accès réservé au Super Admin)
    """

    queryset = Organization.objects.all().order_by("-created_at")
    serializer_class = OrganizationSerializer


class OrganizationDetailView(generics.RetrieveAPIView):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    lookup_field = "pk"


class AdminONGRequestsView(generics.ListAPIView):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.role != User.Role.SUPER_ADMIN:
            return Organization.objects.none()
        return Organization.objects.filter(status=Organization.Status.EN_ATTENTE).order_by("-created_at")


class ApproveONGView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):
        user = request.user
        if user.role != User.Role.SUPER_ADMIN:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            organization = Organization.objects.get(pk=pk, status=Organization.Status.EN_ATTENTE)
        except Organization.DoesNotExist:
            return Response({"detail": "Demande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        organization.status = Organization.Status.ACTIVE
        organization.is_active = True
        organization.save(update_fields=["status", "is_active", "updated_at"])

        Subscription.objects.get_or_create(
            organization=organization,
            defaults={
                "status": Subscription.Status.TRIAL,
                "trial_start": timezone.now().date(),
                "trial_end": timezone.now().date() + timezone.timedelta(days=30),
            },
        )

        manager = organization.users.filter(role=User.Role.GERANT).first()
        if manager:
            token = ActivationToken.objects.create(
                user=manager,
                expires_at=timezone.now() + timezone.timedelta(days=1),
            )
            activation_link = f"{settings.FRONTEND_URL}/activation/{token.id}"
            send_invitation_email.delay(
                recipient_email=manager.email,
                first_name=manager.first_name,
                activation_link=activation_link,
                temporary_password=None,
                subject_override="Votre ONG a été approuvée 🎉",
                html_override=f"""
                <h2>Félicitations {manager.first_name} 🎉</h2>
                <p>Votre ONG <strong>{organization.name}</strong> a été validée par le Super Admin.</p>
                <p>Cliquez sur le bouton ci-dessous pour activer votre compte :</p>
                <p>
                    <a href="{activation_link}"
                       style="background:#744D03; color:white; padding:12px 20px; text-decoration:none; border-radius:6px;">
                       Activer mon compte
                    </a>
                </p>
                <p>Ce lien est valable pendant 24 heures.</p>
                <p>L'équipe BarakaGive</p>
                """,
            )

        return Response({"message": "ONG approuvée.", "organization_id": organization.id})


class RejectONGView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        if user.role != User.Role.SUPER_ADMIN:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            organization = Organization.objects.get(pk=pk, status=Organization.Status.EN_ATTENTE)
        except Organization.DoesNotExist:
            return Response({"detail": "Demande introuvable."}, status=status.HTTP_404_NOT_FOUND)

        organization.status = Organization.Status.REJETEE
        organization.save(update_fields=["status", "updated_at"])

        manager = organization.users.filter(role=User.Role.GERANT).first()
        if manager:
            send_invitation_email.delay(
                recipient_email=manager.email,
                first_name=manager.first_name,
                activation_link=f"{settings.FRONTEND_URL}/connexion",
                temporary_password=None,
                subject_override="Votre demande d'inscription a été rejetée",
                html_override=f"""
                <h2>Bonjour {manager.first_name},</h2>
                <p>Votre demande d'inscription pour l'ONG <strong>{organization.name}</strong> a été rejetée.</p>
                <p>Pour plus d'informations, veuillez contacter le support.</p>
                <p>L'équipe BarakaGive</p>
                """,
            )

        return Response({"message": "ONG rejetée.", "organization_id": organization.id})


class ActivationCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        try:
            token_uuid = token
        except ValueError:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            activation = ActivationToken.objects.select_related("user").get(id=token_uuid)
        except ActivationToken.DoesNotExist:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_404_NOT_FOUND)

        if activation.used:
            return Response({"detail": "Ce lien a déjà été utilisé."}, status=status.HTTP_400_BAD_REQUEST)

        if activation.expires_at < timezone.now():
            return Response({"detail": "Ce lien est expiré."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            "token": str(activation.id),
            "email": activation.user.email,
            "first_name": activation.user.first_name,
        })


class ActivationConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @transaction.atomic
    def post(self, request):
        token = request.data.get("token")
        password = request.data.get("password")

        if not token or not password:
            return Response({"detail": "Token et mot de passe requis."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_uuid = token
        except ValueError:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            activation = ActivationToken.objects.select_related("user").get(id=token_uuid)
        except ActivationToken.DoesNotExist:
            return Response({"detail": "Lien invalide."}, status=status.HTTP_404_NOT_FOUND)

        if activation.used:
            return Response({"detail": "Ce lien a déjà été utilisé."}, status=status.HTTP_400_BAD_REQUEST)

        if activation.expires_at < timezone.now():
            return Response({"detail": "Ce lien est expiré."}, status=status.HTTP_400_BAD_REQUEST)

        user = activation.user
        user.set_password(password)
        user.status = User.Status.ACTIVE
        user.is_active = True
        user.must_change_password = False
        user.save(update_fields=["password", "status", "is_active", "must_change_password"])

        if user.organization:
            user.organization.status = Organization.Status.ACTIVE
            user.organization.is_active = True
            user.organization.save(update_fields=["status", "is_active", "updated_at"])

            Subscription.objects.get_or_create(
                organization=user.organization,
                defaults={
                    "status": Subscription.Status.TRIAL,
                    "trial_start": timezone.now().date(),
                    "trial_end": timezone.now().date() + timezone.timedelta(days=30),
                },
            )

        activation.used = True
        activation.save(update_fields=["used"])

        return Response({"message": "Compte activé avec succès."})
