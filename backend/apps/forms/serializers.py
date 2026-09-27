from rest_framework import serializers

from .models import Formulaire, FormField


class FormFieldSerializer(serializers.ModelSerializer):
    """Sérialiseur pour les questions d'un formulaire."""

    class Meta:
        model = FormField
        fields = [
            "id",
            "label",
            "type",
            "obligatoire",
            "ordre",
            "placeholder",
            "options",
        ]
        read_only_fields = ["id"]


class FormFieldCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création d'une question."""

    label = serializers.CharField(max_length=300)
    type = serializers.ChoiceField(choices=FormField.TypeChoices.choices)
    obligatoire = serializers.BooleanField(default=False)
    ordre = serializers.IntegerField(min_value=0, required=False)
    placeholder = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    options = serializers.JSONField(required=False, allow_null=True)

    def validate_label(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Le label de la question est obligatoire.")
        return value

    def validate(self, attrs):
        field_type = attrs.get("type")
        options = attrs.get("options")

        if field_type in [FormField.TypeChoices.SELECT, FormField.TypeChoices.CHECKBOX] and not options:
            raise serializers.ValidationError({
                "options": "Les types SELECT et CHECKBOX nécessitent des options."
            })

        if field_type not in [FormField.TypeChoices.SELECT, FormField.TypeChoices.CHECKBOX] and options:
            raise serializers.ValidationError({
                "options": "Les options ne sont autorisées que pour les types SELECT et CHECKBOX."
            })

        return attrs


class FormFieldUpdateSerializer(serializers.Serializer):
    """Sérialiseur pour la mise à jour d'une question."""

    label = serializers.CharField(max_length=300, required=False)
    type = serializers.ChoiceField(choices=FormField.TypeChoices.choices, required=False)
    obligatoire = serializers.BooleanField(required=False)
    ordre = serializers.IntegerField(min_value=0, required=False)
    placeholder = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)
    options = serializers.JSONField(required=False, allow_null=True)

    def validate_label(self, value):
        if value is not None and (not value or not value.strip()):
            raise serializers.ValidationError("Le label de la question ne peut pas être vide.")
        return value

    def validate(self, attrs):
        field_type = attrs.get("type")
        options = attrs.get("options")

        if field_type in [FormField.TypeChoices.SELECT, FormField.TypeChoices.CHECKBOX] and options is not None and not options:
            raise serializers.ValidationError({
                "options": "Les types SELECT et CHECKBOX nécessitent des options."
            })

        if field_type and field_type not in [FormField.TypeChoices.SELECT, FormField.TypeChoices.CHECKBOX] and options:
            raise serializers.ValidationError({
                "options": "Les options ne sont autorisées que pour les types SELECT et CHECKBOX."
            })

        return attrs


class FormulaireListSerializer(serializers.ModelSerializer):
    """Sérialiseur pour la liste des formulaires."""

    campagne = serializers.SerializerMethodField()
    questions_count = serializers.SerializerMethodField()

    class Meta:
        model = Formulaire
        fields = [
            "id",
            "nom",
            "campagne",
            "version",
            "statut",
            "questions_count",
        ]

    def get_campagne(self, obj):
        return {
            "id": obj.campagne.id,
            "code_campagne": obj.campagne.code_campagne,
            "nom": obj.campagne.nom,
        }

    def get_questions_count(self, obj):
        return obj.fields.count()


class FormulaireDetailSerializer(serializers.ModelSerializer):
    """Sérialiseur pour le détail d'un formulaire avec toutes ses questions."""

    campagne = serializers.SerializerMethodField()
    fields = FormFieldSerializer(many=True, read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Formulaire
        fields = [
            "id",
            "nom",
            "description",
            "campagne",
            "version",
            "statut",
            "fields",
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

    def get_created_by(self, obj):
        return {
            "id": obj.created_by.id,
            "email": obj.created_by.email,
            "full_name": obj.created_by.full_name,
            "role": obj.created_by.role,
        }


class FormulaireCreateSerializer(serializers.Serializer):
    """Sérialiseur pour la création d'un formulaire avec ses questions."""

    campagne_id = serializers.UUIDField()
    nom = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    fields = FormFieldCreateSerializer(many=True, required=False, default=list)

    def validate_nom(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Le nom du formulaire est obligatoire.")
        return value

    def validate_fields(self, value):
        if value:
            ordres = [f.get("ordre", 0) for f in value]
            if len(ordres) != len(set(ordres)):
                raise serializers.ValidationError("Les ordres des questions doivent être uniques.")
        return value


class FormulaireUpdateSerializer(serializers.Serializer):
    """Sérialiseur pour la mise à jour d'un formulaire (nom, description, statut)."""

    nom = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    statut = serializers.ChoiceField(choices=Formulaire.Statut.choices, required=False)

    def validate_nom(self, value):
        if value is not None and (not value or not value.strip()):
            raise serializers.ValidationError("Le nom du formulaire ne peut pas être vide.")
        return value


class ReorderQuestionsSerializer(serializers.Serializer):
    """Sérialiseur pour le réordonnancement des questions."""

    questions = serializers.ListField(
        child=serializers.DictField(
            child=serializers.CharField(),
        ),
        min_length=1,
    )

    def validate_questions(self, value):
        for q in value:
            if "id" not in q or "ordre" not in q:
                raise serializers.ValidationError("Chaque question doit avoir 'id' et 'ordre'.")
            try:
                int(q["ordre"])
            except (ValueError, TypeError):
                raise serializers.ValidationError("L'ordre doit être un entier.")
        return value


class DuplicateQuestionSerializer(serializers.Serializer):
    """Sérialiseur pour la duplication d'une question (vide, tout dans l'URL)."""
    pass