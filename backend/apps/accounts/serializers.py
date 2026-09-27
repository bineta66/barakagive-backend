from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import User
from apps.common.validators import (
    validate_nom,
    validate_email,
    validate_phone_senegal,
    validate_password_strong,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id", "first_name", "last_name", "email", "phone",
            "role", "organization", "status", "is_active",
            "must_change_password", "date_joined",
        ]
        read_only_fields = ["id", "organization", "date_joined"]


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "role"]

    def validate_first_name(self, value):
        try:
            return validate_nom(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_last_name(self, value):
        try:
            return validate_nom(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_email(self, value):
        try:
            v = validate_email(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))
        if User.objects.filter(email=v).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return v

    def validate_phone(self, value):
        if not value:
            return value
        try:
            return validate_phone_senegal(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_role(self, value):
        roles_autorises = [User.Role.CHEF_PROJET, User.Role.FINANCE, User.Role.AGENT]
        if value not in roles_autorises:
            raise serializers.ValidationError(
                "Le Gérant peut uniquement créer un Chef de projet, un Responsable Finance ou un Agent Terrain."
            )
        return value


class ActivateAccountSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            return validate_password_strong(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Les mots de passe ne correspondent pas."}
            )
        return attrs


class RegisterAuthSerializer(serializers.Serializer):
    organization_name = serializers.CharField(max_length=200)
    organization_acronym = serializers.CharField(max_length=50, required=False, allow_blank=True)
    organization_email = serializers.EmailField()
    organization_phone = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=100, default="Sénégal")
    region = serializers.CharField(max_length=100)
    address = serializers.CharField(max_length=255)
    organization_description = serializers.CharField(required=False, allow_blank=True)
    logo = serializers.ImageField(required=False, allow_null=True)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=20)

    def validate_first_name(self, value):
        try:
            return validate_nom(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_last_name(self, value):
        try:
            return validate_nom(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_email(self, value):
        try:
            return validate_email(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate_phone(self, value):
        if not value:
            return value
        try:
            return validate_phone_senegal(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate(self, attrs):
        from apps.accounts.models import User
        from apps.organizations.models import Organization
        if User.objects.filter(email=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Cet email est déjà utilisé."})
        if Organization.objects.filter(email=attrs["organization_email"]).exists():
            raise serializers.ValidationError({"organization_email": "Cet email ONG est déjà utilisé."})
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        try:
            return validate_password_strong(value)
        except Exception as e:
            raise serializers.ValidationError(str(e))

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Les mots de passe ne correspondent pas."}
            )
        return attrs


class ResendActivationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class AgentListSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "phone", "full_name", "role"]
        read_only_fields = fields

    def get_full_name(self, obj):
        return obj.full_name