"""
validators.py — Validateurs centralisés BarakaGive360

Usage dans les serializers :
    from apps.common.validators import (
        validate_nom, validate_email, validate_phone_senegal,
        validate_password_strong, validate_montant, validate_date_fin,
        validate_description, validate_adresse,
    )
"""
import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

# ─── Expressions régulières ───────────────────────────────────────────────────

# Nom / Prénom : lettres (latin + accents africains), espaces, tiret, apostrophe
NOM_REGEX = re.compile(r"^[a-zA-ZÀ-ÿ\s'\-]{2,50}$")

# Nom long (ONG, projet, campagne)
NOM_LONG_REGEX = re.compile(r"^.{3,120}$", re.DOTALL)

# Email
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

# Téléphone sénégalais : 9 chiffres, préfixes 70/75/76/77/78
PHONE_LOCAL_REGEX = re.compile(r"^(70|75|76|77|78)[0-9]{7}$")
# Avec indicatif optionnel
PHONE_REGEX = re.compile(r"^(\+221\s?)?(70|75|76|77|78)[0-9]{7}$")

# Mot de passe fort
PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&_\-#^])[A-Za-z\d@$!%*?&_\-#^]{8,}$"
)

# ─── Fonctions de validation ──────────────────────────────────────────────────

def validate_nom(value):
    """Valide un nom ou prénom (2–50 chars, lettres/espaces/tiret/apostrophe)."""
    v = (value or "").strip()
    if not v:
        raise ValidationError(_("Ce champ est obligatoire."))
    if not NOM_REGEX.match(v):
        raise ValidationError(
            _("Le nom doit contenir entre 2 et 50 caractères "
              "(lettres, espaces, tiret, apostrophe uniquement).")
        )
    return v


def validate_nom_long(value):
    """Valide un nom d'ONG, de projet ou de campagne (3–120 chars)."""
    v = (value or "").strip()
    if not v:
        raise ValidationError(_("Ce champ est obligatoire."))
    if len(v) < 3 or len(v) > 120:
        raise ValidationError(
            _("Ce champ doit contenir entre 3 et 120 caractères.")
        )
    return v


def validate_email(value):
    """Valide un email (format + longueur max 100)."""
    v = (value or "").strip().lower()
    if not v:
        raise ValidationError(_("L'email est obligatoire."))
    if len(v) > 100:
        raise ValidationError(_("L'email ne peut pas dépasser 100 caractères."))
    if not EMAIL_REGEX.match(v):
        raise ValidationError(
            _("Veuillez saisir une adresse email valide (ex: contact@ong.sn).")
        )
    return v


def validate_phone_senegal(value):
    """
    Valide un numéro de téléphone sénégalais.
    Accepte : 771234567, +221771234567, +221 77 123 45 67
    Préfixes autorisés : 70, 75, 76, 77, 78
    """
    v = (value or "").strip().replace(" ", "").replace("-", "")
    if not v:
        raise ValidationError(_("Le numéro de téléphone est obligatoire."))
    # Normaliser : enlever +221 ou 221 en tête
    local = re.sub(r"^(\+221|221)", "", v)
    if not PHONE_LOCAL_REGEX.match(local):
        raise ValidationError(
            _("Numéro invalide. Format Sénégal attendu : "
              "70, 75, 76, 77 ou 78 suivi de 7 chiffres (ex: 771234567).")
        )
    return v


def validate_password_strong(value):
    """
    Valide un mot de passe fort :
    - Au moins 8 caractères
    - Au moins 1 majuscule
    - Au moins 1 minuscule
    - Au moins 1 chiffre
    - Au moins 1 caractère spécial (@$!%*?&_-#^)
    """
    if not value:
        raise ValidationError(_("Le mot de passe est obligatoire."))
    if len(value) < 8:
        raise ValidationError(_("Le mot de passe doit contenir au moins 8 caractères."))
    if not PASSWORD_REGEX.match(value):
        raise ValidationError(
            _("Le mot de passe doit contenir au moins : "
              "1 majuscule, 1 minuscule, 1 chiffre et 1 caractère spécial (@$!%*?&_-#^).")
        )
    return value


def validate_montant(value):
    """Valide un montant FCFA (1 à 999 999 999)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise ValidationError(_("Veuillez saisir un montant valide."))
    if n <= 0:
        raise ValidationError(_("Le montant doit être supérieur à 0 FCFA."))
    if n > 999_999_999:
        raise ValidationError(_("Le montant ne peut pas dépasser 999 999 999 FCFA."))
    return value


def validate_pourcentage(value):
    """Valide un pourcentage entier (0–100)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValidationError(_("La valeur doit être un entier."))
    if n < 0 or n > 100:
        raise ValidationError(_("La valeur doit être un entier entre 0 et 100."))
    return n


def validate_date_fin(date_fin, date_debut):
    """Valide que date_fin >= date_debut."""
    if date_fin and date_debut and date_fin < date_debut:
        raise ValidationError(
            _("La date de fin doit être égale ou postérieure à la date de début.")
        )
    return date_fin


def validate_description(value):
    """Valide une description (optionnelle, max 500 chars)."""
    if value and len(value) > 500:
        raise ValidationError(_("La description ne peut pas dépasser 500 caractères."))
    return value


def validate_adresse(value):
    """Valide une adresse (optionnelle, max 255 chars)."""
    if value and len(value) > 255:
        raise ValidationError(_("L'adresse ne peut pas dépasser 255 caractères."))
    return value
