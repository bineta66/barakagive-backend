from django.core import signing
from django.utils.translation import gettext_lazy as _

# Salt spécifique à BarakaGive360
INVITATION_SALT = "barakagive.invitation.salt"


def generate_invitation_token(user):
    """
    Génère un token d'activation pour un utilisateur invité.
    """

    if not user.last_invited_at:
        raise ValueError(
            "L'utilisateur doit avoir une date d'invitation."
        )

    payload = {
        "user_id": user.id,
        "invited_at": user.last_invited_at.isoformat(),
    }

    return signing.dumps(
        payload,
        salt=INVITATION_SALT,
    )


def verify_invitation_token(token, max_age=60 * 60 * 24 * 7):
    """
    Vérifie le token (7 jours).
    """

    try:
        payload = signing.loads(
            token,
            salt=INVITATION_SALT,
            max_age=max_age,
        )
        return payload

    except signing.SignatureExpired:
        raise ValueError(
            _("Le lien d'activation a expiré.")
        )

    except signing.BadSignature:
        raise ValueError(
            _("Le lien d'activation est invalide.")
        )