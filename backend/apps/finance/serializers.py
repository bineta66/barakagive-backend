import os
from rest_framework import serializers
from .models import Budget, Don, Depense, Justification, Bailleur, Partenaire


# =========================
# BUDGET
# =========================
class BudgetSerializer(serializers.ModelSerializer):
    projet_nom = serializers.CharField(source="projet.name", read_only=True)
    responsable_nom = serializers.SerializerMethodField()
    date_creation = serializers.DateTimeField(source="created_at", read_only=True)
    solde = serializers.ReadOnlyField()
    taux_execution = serializers.ReadOnlyField()

    def get_responsable_nom(self, obj):
        if obj.created_by:
            return getattr(obj.created_by, "full_name", None) or obj.created_by.email
        return "Responsable Finance"

    class Meta:
        model = Budget
        fields = "__all__"
        read_only_fields = (
            "id",
            "organization",
            "created_by",
            "created_at",
            "updated_at",
            "solde",
            "taux_execution",
            "projet_nom",
            "responsable_nom",
            "date_creation",
        )

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le montant doit être supérieur à 0."
            )
        return value

    def validate_date(self, value):
        if value is None:
            raise serializers.ValidationError("La date est obligatoire.")
        return value

    def validate_source_financement(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "La source de financement est obligatoire."
            )
        return value.strip()


# =========================
# DON
# =========================
class DonSerializer(serializers.ModelSerializer):
    # projet_nom via budget → safe si budget est null
    projet_nom = serializers.SerializerMethodField(read_only=True)
    campagne_nom = serializers.SerializerMethodField(read_only=True)
    budget_source = serializers.CharField(
        source="budget.source_financement",
        read_only=True,
        default=None,
    )

    def get_projet_nom(self, obj):
        try:
            return obj.budget.projet.name if obj.budget else None
        except Exception:
            return None

    def get_campagne_nom(self, obj):
        try:
            return obj.campagne.nom if obj.campagne else None
        except Exception:
            return None

    class Meta:
        model = Don
        fields = "__all__"
        read_only_fields = (
            "id",
            "reference",
            "organization",
            "created_by",
            "created_at",
            "updated_at",
            "projet_nom",
            "campagne_nom",
            "budget_source",
        )

    def validate_bailleur(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError(
                "Le nom du bailleur est obligatoire."
            )
        return value.strip()

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le montant doit être supérieur à 0."
            )
        return value

    def validate_date(self, value):
        if value is None:
            raise serializers.ValidationError("La date est obligatoire.")
        return value

    def validate_moyen_paiement(self, value):
        choix_valides = [c[0] for c in Don.MoyenPaiement.choices]
        if value not in choix_valides:
            raise serializers.ValidationError(
                f"Moyen de paiement invalide. Choisissez parmi : {', '.join(choix_valides)}."
            )
        return value


# =========================
# DEPENSE
# =========================
class DepenseSerializer(serializers.ModelSerializer):
    # projet_nom via budget → safe si budget est null
    projet_nom = serializers.SerializerMethodField(read_only=True)
    campagne_nom = serializers.SerializerMethodField(read_only=True)

    def get_projet_nom(self, obj):
        try:
            return obj.budget.projet.name if obj.budget else None
        except Exception:
            return None

    def get_campagne_nom(self, obj):
        try:
            return obj.campagne.nom if obj.campagne else None
        except Exception:
            return None

    region = serializers.PrimaryKeyRelatedField(
        queryset=__import__("apps.zones.models", fromlist=["Region"]).Region.objects.all(),
        required=False,
        allow_null=True,
    )
    budget = serializers.PrimaryKeyRelatedField(
        queryset=Budget.objects.all(),
        required=False,
        allow_null=True,
    )
    campagne = serializers.PrimaryKeyRelatedField(
        queryset=__import__("apps.campaigns.models", fromlist=["Campaign"]).Campaign.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Depense
        fields = "__all__"
        read_only_fields = (
            "id",
            "reference",
            "organization",
            "created_by",
            "created_at",
            "updated_at",
            "projet_nom",
            "campagne_nom",
            "region_nom",
        )

    def to_internal_value(self, data):
        data = data.copy() if hasattr(data, "copy") else dict(data)

        # 1. Nettoyer budget et campagne (convertir "" en None pour éviter erreur UUID)
        if "budget" in data and not data.get("budget"):
            data["budget"] = None
        if "campagne" in data and not data.get("campagne"):
            data["campagne"] = None

        # 2. S'assurer que les régions existent
        from apps.zones.models import Region
        from django.contrib.gis.geos import Polygon
        if not Region.objects.exists():
            poly = Polygon(((0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)))
            for nom in ["Dakar", "Diourbel", "Fatick", "Kaffrine", "Kaolack", "Kédougou", "Kolda", "Louga", "Matam", "Saint-Louis", "Sédhiou", "Tambacounda", "Thiès", "Ziguinchor"]:
                Region.objects.get_or_create(nom=nom, defaults={"geometrie": poly})

        # 3. Assurer un ID de région valide
        reg_id = data.get("region")
        if reg_id:
            try:
                if not Region.objects.filter(pk=reg_id).exists():
                    first_reg = Region.objects.first()
                    data["region"] = first_reg.id if first_reg else None
            except Exception:
                first_reg = Region.objects.first()
                data["region"] = first_reg.id if first_reg else None
        else:
            first_reg = Region.objects.first()
            data["region"] = first_reg.id if first_reg else None

        return super().to_internal_value(data)

    def validate_montant(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Le montant doit être supérieur à 0."
            )
        return value

    def validate_categorie(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("La catégorie est obligatoire.")
        return value.strip()

    def validate_date(self, value):
        if value is None:
            raise serializers.ValidationError("La date est obligatoire.")
        return value

    region_nom = serializers.SerializerMethodField(read_only=True)

    def get_region_nom(self, obj):
        try:
            return obj.region.nom if obj.region else None
        except Exception:
            return None

    def validate_region(self, value):
        return value


# =========================
# BAILLEUR
# =========================
class BailleurSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bailleur
        fields = (
            "id", "nom", "type", "email", "telephone", "adresse", "actif",
            "organization", "created_at", "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def validate_nom(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Le nom du bailleur est obligatoire.")
        return value.strip()


# =========================
# PARTENAIRE
# =========================
class PartenaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = Partenaire
        fields = (
            "id", "nom", "domaine", "email", "telephone", "adresse", "actif",
            "organization", "created_at", "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")


# =========================
# JUSTIFICATION
# =========================

# Extensions acceptées → type_fichier normalisé
EXTENSIONS_ACCEPTEES = {
    "pdf":  "pdf",
    "jpg":  "jpg",
    "jpeg": "jpg",   # normalisation : jpeg → jpg
    "png":  "png",
}

def detecter_type_fichier(fichier):
    """Détecte le type de fichier à partir de son extension."""
    if not fichier:
        return ""
    ext = os.path.splitext(fichier.name)[1].lower().lstrip(".")
    return EXTENSIONS_ACCEPTEES.get(ext, ext[:20])


class JustificationSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = Justification
        fields = (
            "id",
            "depense",
            "fichier",
            "type_fichier",
            "statut",
            "uploaded_by",
            "created_at",
            "updated_at",
            "url",
        )
        read_only_fields = (
            "id",
            "depense",
            "uploaded_by",
            "created_at",
            "updated_at",
            "url",
        )

    def get_url(self, obj):
        request = self.context.get("request")
        if not obj.fichier:
            return None
        if request:
            return request.build_absolute_uri(obj.fichier.url)
        return obj.fichier.url

    def validate_fichier(self, value):
        # Taille max 10 Mo
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "Le fichier ne doit pas dépasser 10 Mo."
            )
        # Format accepté
        ext = os.path.splitext(value.name)[1].lower().lstrip(".")
        if ext not in EXTENSIONS_ACCEPTEES:
            raise serializers.ValidationError(
                f"Format non accepté : .{ext}. Utilisez PDF, JPG ou PNG."
            )
        return value

    def validate(self, attrs):
        # Auto-détecter type_fichier si non fourni ou vide
        fichier = attrs.get("fichier")
        type_fichier = attrs.get("type_fichier", "").strip()

        if fichier and not type_fichier:
            attrs["type_fichier"] = detecter_type_fichier(fichier)

        # Vérifier que type_fichier n'est pas vide après tentative de détection
        if not attrs.get("type_fichier"):
            raise serializers.ValidationError({
                "type_fichier": "Le type de fichier est requis (ex: pdf, jpg, png)."
            })

        return attrs
