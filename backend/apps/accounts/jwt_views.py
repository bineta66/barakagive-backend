from django.utils import timezone

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed

from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


class JWTLoginSerializer(TokenObtainPairSerializer):

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["role"] = user.role
        token["organization"] = (
            user.organization.id if user.organization else None
        )

        return token

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except Exception:
            raise AuthenticationFailed(
                "Email ou mot de passe incorrect."
            )

        user = self.user

        if not user.is_active:
            raise AuthenticationFailed(
                "Votre compte n'est pas encore activé. Vérifiez votre email pour le lien d'activation."
            )

        if user.status != User.Status.ACTIVE:
            if user.status == User.Status.SUSPENDED:
                raise AuthenticationFailed(
                    "Votre compte a été suspendu. Contactez votre administrateur."
                )
            raise AuthenticationFailed(
                "Votre compte n'est pas encore activé. Vérifiez votre email pour le lien d'activation."
            )

        data["user"] = {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "organization": (
                user.organization.id if user.organization else None
            ),
            "must_change_password": user.must_change_password,
        }
        data["must_change_password"] = user.must_change_password

        return data


class JWTLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = JWTLoginSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = serializer.user
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

        return response


class LogoutView(APIView):

    def post(self, request):
        refresh = request.data.get("refresh")

        if not refresh:
            return Response(
                {"detail": "Refresh token requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except Exception:
            return Response(
                {"detail": "Token invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Déconnexion réussie."},
            status=status.HTTP_200_OK,
        )