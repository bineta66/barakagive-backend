from rest_framework import serializers

from apps.campaigns.models import Campaign
from apps.zones.models import Zone
from apps.forms.models import Formulaire, FormField
from .models import Beneficiary, FormResponse


class FormResponseCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création d'une réponse (format simplifié pour le frontend)."""

    question_id = serializers.UUIDField()
    value = serializers.JSONField(help_text="Valeur brute, le backend la répartit selon le type de question")


class FormResponseSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la lecture d'une réponse."""

    question = serializers.SerializerMethodField()

    class Meta:
        model = FormResponse
        fields = [
            "id",
            "question",
            "value_text",
            "value_number",
            "value_boolean",
            "value_date",
            "value_json",
            "created_at",
        ]

    def get_question(self, obj):
        return {
            "id": obj.question.id,
            "label": obj.question.label,
            "type": obj.question.type,
        }


class BeneficiaryCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création d'un bénéficiaire avec ses réponses (un seul JSON)."""

    campagne_id = serializers.UUIDField()
    formulaire_id = serializers.UUIDField()
    zone_id = serializers.UUIDField()
    local_id = serializers.UUIDField()
    device_id = serializers.CharField(max_length=100)

    beneficiary = serializers.DictField(
        child=serializers.CharField(),
        help_text="Informations personnelles du bénéficiaire"
    )

    responses = FormResponseCreateSerializer(many=True)

    def validate_beneficiary(self, value):
        required_fields = ["nom", "prenom", "telephone", "sexe", "date_naissance", "latitude", "longitude"]
        for field in required_fields:
            if field not in value or not value[field]:
                raise serializers.ValidationError(f"Le champ '{field}' est obligatoire.")

        # Validation nom
        from apps.common.validators import validate_nom, validate_phone_senegal, NOM_REGEX
        nom = (value.get("nom") or "").strip()
        if not NOM_REGEX.match(nom):
            raise serializers.ValidationError(
                "Le nom doit contenir entre 2 et 50 caractères (lettres, espaces, tiret, apostrophe)."
            )

        prenom = (value.get("prenom") or "").strip()
        if not NOM_REGEX.match(prenom):
            raise serializers.ValidationError(
                "Le prénom doit contenir entre 2 et 50 caractères (lettres, espaces, tiret, apostrophe)."
            )

        # Validation téléphone
        try:
            validate_phone_senegal(value.get("telephone", ""))
        except Exception as e:
            raise serializers.ValidationError(str(e))

        # Validation date de naissance
        from datetime import date
        try:
            dob = value.get("date_naissance")
            if dob:
                d = date.fromisoformat(dob)
                if d >= date.today():
                    raise serializers.ValidationError(
                        "La date de naissance doit être dans le passé."
                    )
        except ValueError:
            raise serializers.ValidationError("La date de naissance est invalide (format attendu : YYYY-MM-DD).")

        return value


class BeneficiaryUpdateSerializer(serializers.Serializer):
    """Sérialiseur pour la mise à jour des informations personnelles."""

    nom = serializers.CharField(max_length=100, required=False)
    prenom = serializers.CharField(max_length=100, required=False)
    telephone = serializers.CharField(max_length=20, required=False)
    sexe = serializers.ChoiceField(choices=Beneficiary.Sexe.choices, required=False)
    date_naissance = serializers.DateField(required=False)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False)

    def validate_telephone(self, value):
        if value is not None and not value.strip():
            raise serializers.ValidationError("Le téléphone ne peut pas être vide.")
        return value


class BeneficiaryListSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la liste des bénéficiaires, incluant les réponses détaillées."""

    campagne = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    responses = FormResponseSerializer(many=True, read_only=True)

    class Meta:
        model = Beneficiary
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "sexe",
            "date_naissance",
            "campagne",
            "zone",
            "score_vulnerabilite",
            "sync_status",
            "created_by",
            "created_at",
            "responses",
        ]

    def get_campagne(self, obj):
        return {
            "id": obj.campagne.id,
            "code_campagne": obj.campagne.code_campagne,
            "nom": obj.campagne.nom,
        }

    def get_zone(self, obj):
        return {
            "id": obj.zone.id,
            "nom": obj.zone.nom,
        }

    def get_created_by(self, obj):
        return {
            "id": obj.created_by.id,
            "email": obj.created_by.email,
            "full_name": obj.created_by.full_name,
        }


class BeneficiaryDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le détail d'un bénéficiaire avec ses réponses."""

    campagne = serializers.SerializerMethodField()
    zone = serializers.SerializerMethodField()
    formulaire = serializers.SerializerMethodField()
    responses = FormResponseSerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Beneficiary
        fields = [
            "id",
            "nom",
            "prenom",
            "telephone",
            "sexe",
            "date_naissance",
            "latitude",
            "longitude",
            "local_id",
            "device_id",
            "campagne",
            "zone",
            "formulaire",
            "score_vulnerabilite",
            "sync_status",
            "responses",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_campagne(self, obj):
        return {
            "id": obj.campagne.id,
            "code_campagne": obj.campagne.code_campagne,
            "nom": obj.campagne.nom,
            "projet": {
                "id": obj.campagne.projet.id,
                "code": obj.campagne.projet.code,
                "name": obj.campagne.projet.name,
            },
        }

    def get_zone(self, obj):
        return {
            "id": obj.zone.id,
            "nom": obj.zone.nom,
            "region": obj.zone.region,
            "departement": obj.zone.departement,
        }

    def get_formulaire(self, obj):
        if hasattr(obj, '_formulaire_id'):
            return {"id": obj._formulaire_id}
        # Récupérer le formulaire via les réponses
        if obj.responses.exists():
            return {"id": obj.responses.first().formulaire.id}
        return None

    def get_created_by(self, obj):
        return {
            "id": obj.created_by.id,
            "email": obj.created_by.email,
            "full_name": obj.created_by.full_name,
            "role": obj.created_by.role,
        }


class BeneficiarySyncSerializer(serializers.Serializer):
    """Sérialiseur pour la réponse de synchronisation."""

    synced = serializers.IntegerField()
    duplicates = serializers.IntegerField()
    failed = serializers.IntegerField()
    details = serializers.ListField(child=serializers.DictField(), required=False)