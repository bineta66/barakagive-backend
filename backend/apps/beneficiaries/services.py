import logging

from django.db import transaction

logger = logging.getLogger(__name__)

from .models import FormResponse


@transaction.atomic
def enregistrer_reponse(
    *,
    beneficiary,
    formulaire_id,
    question_id,
    value_boolean=None,
    value_text=None,
    value_number=None,
    value_date=None,
    value_json=None,
):
    """
    Crée ou met à jour la réponse d'un bénéficiaire.
    Le calcul du score sera déclenché après l'enregistrement.
    """
    reponse, _ = FormResponse.objects.update_or_create(
        beneficiary=beneficiary,
        question_id=question_id,
        defaults={
            "formulaire_id": formulaire_id,
            "value_boolean": value_boolean,
            "value_text": value_text,
            "value_number": value_number,
            "value_date": value_date,
            "value_json": value_json,
        },
    )

    return reponse


from decimal import Decimal, InvalidOperation
from django.db import transaction


YES_VALUES = {
    "oui",
    "yes",
    "true",
    "1",
    "vrai",
    "on",
}


def _normaliser_valeur(reponse):
    """
    Retourne la valeur d'une réponse sous forme de texte comparable.
    """
    if reponse.value_boolean is not None:
        return "true" if reponse.value_boolean else "false"

    if reponse.value_text is not None:
        return reponse.value_text.strip().lower()

    if reponse.value_number is not None:
        return str(reponse.value_number).strip().lower()

    if reponse.value_json is not None:
        return str(reponse.value_json).strip().lower()

    return ""


def _reponse_est_vulnerable(reponse, critere):
    valeur = _normaliser_valeur(reponse)
    valeurs_vulnerables = {
        str(item).strip().lower()
        for item in (critere.vulnerable_values or [])
    }

    if valeurs_vulnerables:
        if critere.vulnerable_operator in {"equals", "in", "contains"}:
            return valeur in valeurs_vulnerables

    return valeur in YES_VALUES


def _get_project_from_campaign(campagne):
    """
    Adapte automatiquement le nom de la relation Campaign -> Project.
    Le projet peut être exposé sous 'projet' ou 'project'.
    """
    if hasattr(campagne, "projet") and campagne.projet:
        return campagne.projet

    if hasattr(campagne, "project") and campagne.project:
        return campagne.project

    if hasattr(campagne, "projet_id") and campagne.projet_id:
        return campagne.projet

    if hasattr(campagne, "project_id") and campagne.project_id:
        return campagne.project

    raise AttributeError(
        "Campaign doit avoir une relation 'projet' ou 'project' vers Project."
    )


@transaction.atomic
def recalculer_score_beneficiaire(beneficiary):
    """
    Calcule et enregistre le score de vulnérabilité d'un bénéficiaire.
    """
    return update_vulnerability_score(beneficiary).score_vulnerabilite


from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from apps.campaigns.models import Campaign, CampagneAffectation
from apps.zones.models import Zone
from apps.forms.models import Formulaire, FormField
from .models import Beneficiary, FormResponse


class BeneficiaryError(Exception):
    """Exception personnalisée pour les erreurs de bénéficiaire."""
    pass


def build_zone_ranking(campaign):
    """
    Construit le classement des zones pour une campagne.

    Args:
        campaign: Instance de Campaign

    Returns:
        list[dict]: Classement des zones avec score_total, beneficiaires_prioritaires, top5
    """
    beneficiaries = Beneficiary.objects.filter(
        campagne=campaign
    ).select_related("zone").prefetch_related("responses__question").order_by("-score_vulnerabilite")

    zones_data = {}
    for beneficiary in beneficiaries:
        zone_nom = beneficiary.zone.nom if beneficiary.zone else "Inconnue"
        if zone_nom not in zones_data:
            zones_data[zone_nom] = {
                "nom": zone_nom,
                "score_total": Decimal("0"),
                "beneficiaires": [],
            }
        score = beneficiary.score_vulnerabilite or Decimal("0")
        zones_data[zone_nom]["score_total"] += score
        zones_data[zone_nom]["beneficiaires"].append({
            "id": str(beneficiary.id),
            "nom": f"{beneficiary.prenom} {beneficiary.nom}",
            "score": int(score),
            "raisons": _extraire_raisons(beneficiary),
        })

    classement = []
    for zone_nom, data in zones_data.items():
        beneficiaires_tries = sorted(
            data["beneficiaires"],
            key=lambda b: b["score"],
            reverse=True,
        )
        top5 = beneficiaires_tries[:5]
        classement.append({
            "nom": data["nom"],
            "score_total": int(data["score_total"]),
            "beneficiaires_prioritaires": len([b for b in data["beneficiaires"] if b["score"] >= 70]),
            "top5": top5,
        })

    classement.sort(key=lambda z: z["score_total"], reverse=True)
    return classement


def _extraire_raisons(beneficiary):
    """
    Extrait les raisons de priorisation d'un bénéficiaire à partir de ses réponses.
    """
    raisons = []
    try:
        responses = beneficiary.responses.select_related("question").all()
        for response in responses:
            valeur = _extraire_valeur_reponse(response)
            if _est_reponse_vulnerable(valeur):
                label = response.question.label
                valeur_lisible = _formatter_valeur(response, valeur)
                if valeur_lisible:
                    raisons.append(f"{label} : {valeur_lisible}")
                else:
                    raisons.append(label)
    except Exception:
        pass
    return raisons[:3]


def _formatter_valeur(response, valeur):
    """
    Formate la valeur d'une réponse pour l'afficher dans les raisons.
    """
    if valeur is None:
        return None

    if isinstance(valeur, bool):
        return "Oui" if valeur else "Non"

    if isinstance(valeur, (int, float)):
        return str(valeur)

    if isinstance(valeur, str):
        texte = valeur.strip()
        return texte or None

    if isinstance(valeur, list):
        if not valeur:
            return None
        return ", ".join(str(v) for v in valeur)

    if isinstance(valeur, dict):
        return str(valeur)

    return str(valeur)


def validate_agent_permissions(user, campaign, zone, formulaire):
    """
    Vérifie que l'agent a les droits pour créer un bénéficiaire.

    Args:
        user: Utilisateur connecté (AGENT)
        campaign: Instance de Campaign
        zone: Instance de Zone
        formulaire: Instance de Formulaire

    Raises:
        BeneficiaryError: Si une vérification échoue
    """
    if user.role != "AGENT":
        raise BeneficiaryError("Seul un Agent terrain peut créer un bénéficiaire.")

    if not user.organization:
        raise BeneficiaryError("Vous n'appartenez à aucune ONG.")

    if campaign.organization != user.organization:
        raise BeneficiaryError("La campagne n'appartient pas à votre ONG.")

    # Un agent peut etre affecte a plusieurs zones d'une meme campagne.
    assigned_zones = list(
        CampagneAffectation.objects.filter(
            campagne=campaign,
            agent=user,
        ).values_list("zone", flat=True)
    )
    if not assigned_zones:
        raise BeneficiaryError("Vous n'êtes pas affecté à cette campagne.")

    if zone.organization != user.organization:
        raise BeneficiaryError("La zone n'appartient pas à votre ONG.")

    if zone not in campaign.zones.all():
        raise BeneficiaryError("La zone ne fait pas partie de cette campagne.")

    # La zone doit correspondre a l'une des affectations de l'agent.
    if zone.nom not in set(assigned_zones):
        raise BeneficiaryError("La zone ne correspond pas à votre affectation.")

    if formulaire.campagne != campaign:
        raise BeneficiaryError("Le formulaire n'appartient pas à cette campagne.")

    if formulaire.statut != Formulaire.Statut.PUBLIE:
        raise BeneficiaryError("Le formulaire doit être publié pour être utilisé.")


def check_duplicate_in_campaign(campaign, telephone, nom, prenom, date_naissance, exclude_id=None):
    """
    Vérifie si un bénéficiaire existe déjà dans la campagne.

    Règle : téléphone en priorité, sinon nom + prénom + date_naissance.

    Args:
        campaign: Instance de Campaign
        telephone: Téléphone du bénéficiaire
        nom: Nom
        prenom: Prénom
        date_naissance: Date de naissance
        exclude_id: ID à exclure (pour mise à jour)

    Returns:
        Beneficiary or None: Le doublon trouvé ou None
    """
    queryset = Beneficiary.objects.filter(campagne=campaign)

    if exclude_id:
        queryset = queryset.exclude(id=exclude_id)

    # Priorité 1 : téléphone
    duplicate = queryset.filter(telephone=telephone).first()
    if duplicate:
        return duplicate

    # Priorité 2 : nom + prénom + date_naissance
    duplicate = queryset.filter(
        nom__iexact=nom,
        prenom__iexact=prenom,
        date_naissance=date_naissance,
    ).first()

    return duplicate


def check_sync_duplicate(local_id, device_id):
    """
    Vérifie si un bénéficiaire avec ce local_id + device_id existe déjà
    (pour éviter les doublons de synchronisation hors ligne).

    Args:
        local_id: UUID local
        device_id: ID du dispositif

    Returns:
        Beneficiary or None
    """
    return Beneficiary.objects.filter(
        local_id=local_id,
        device_id=device_id,
    ).first()


def store_response(beneficiary, formulaire, question, value):
    """
    Stocke une réponse selon le type de question.

    Args:
        beneficiary: Instance de Beneficiary
        formulaire: Instance de Formulaire
        question: Instance de FormField
        value: Valeur brute (JSON)

    Returns:
        FormResponse: La réponse créée
    """
    response_data = {
        "beneficiary": beneficiary,
        "formulaire": formulaire,
        "question": question,
    }

    field_type = question.type

    if field_type in [FormField.TypeChoices.TEXT, FormField.TypeChoices.PHONE, FormField.TypeChoices.TEXTAREA]:
        response_data["value_text"] = str(value) if value is not None else ""

    elif field_type == FormField.TypeChoices.SELECT:
        response_data["value_text"] = str(value) if value is not None else ""

    elif field_type == FormField.TypeChoices.CHECKBOX:
        if isinstance(value, list):
            response_data["value_json"] = value
        else:
            response_data["value_json"] = [value] if value else []

    elif field_type == FormField.TypeChoices.YES_NO:
        if isinstance(value, bool):
            response_data["value_boolean"] = value
        elif isinstance(value, str):
            response_data["value_boolean"] = value.lower() in ["true", "oui", "yes", "1"]
        else:
            response_data["value_boolean"] = bool(value)

    elif field_type == FormField.TypeChoices.NUMBER:
        try:
            response_data["value_number"] = Decimal(str(value))
        except (ValueError, TypeError):
            response_data["value_number"] = Decimal("0")

    elif field_type == FormField.TypeChoices.DATE:
        if isinstance(value, str):
            from datetime import datetime
            try:
                response_data["value_date"] = datetime.strptime(value, "%Y-%m-%d").date()
            except ValueError:
                pass

    elif field_type == FormField.TypeChoices.GPS:
        # Les coordonnées GPS sont stockées dans Beneficiary, pas dans FormResponse
        # On crée quand même une entrée pour la traçabilité
        response_data["value_json"] = {"latitude": None, "longitude": None}

    return FormResponse.objects.create(**response_data)


def create_beneficiary_with_responses(validated_data, user):
    """
    Crée un bénéficiaire et ses réponses en une seule transaction.
    Gère la détection de doublons et la séparation automatique des données.

    Args:
        validated_data: Données validées du serializer
        user: Utilisateur connecté (AGENT)

    Returns:
        tuple: (beneficiary, responses, is_duplicate)

    Raises:
        BeneficiaryError: Si une validation échoue
    """
    campagne_id = validated_data["campagne_id"]
    formulaire_id = validated_data["formulaire_id"]
    zone_id = validated_data["zone_id"]
    local_id = validated_data["local_id"]
    device_id = validated_data["device_id"]
    beneficiary_data = validated_data["beneficiary"]
    responses_data = validated_data["responses"]

    # Récupérer les objets
    try:
        campaign = Campaign.objects.select_related("projet", "organization").get(id=campagne_id)
    except Campaign.DoesNotExist:
        raise BeneficiaryError("La campagne spécifiée n'existe pas.")

    try:
        zone = Zone.objects.get(id=zone_id)
    except Zone.DoesNotExist:
        raise BeneficiaryError("La zone spécifiée n'existe pas.")

    try:
        formulaire = Formulaire.objects.select_related("campagne", "organization").get(id=formulaire_id)
    except Formulaire.DoesNotExist:
        raise BeneficiaryError("Le formulaire spécifié n'existe pas.")

    # Vérifications de permissions
    validate_agent_permissions(user, campaign, zone, formulaire)

    # Vérifier doublon de synchronisation (local_id + device_id)
    sync_duplicate = check_sync_duplicate(local_id, device_id)
    if sync_duplicate:
        raise BeneficiaryError("Ce bénéficiaire a déjà été synchronisé depuis ce dispositif.")

    # Extraire les données personnelles
    telephone = beneficiary_data["telephone"]
    nom = beneficiary_data["nom"]
    prenom = beneficiary_data["prenom"]
    date_naissance = beneficiary_data["date_naissance"]

    # Vérifier doublon dans la campagne
    duplicate = check_duplicate_in_campaign(
        campaign, telephone, nom, prenom, date_naissance
    )
    if duplicate:
        raise BeneficiaryError("Ce bénéficiaire est déjà inscrit dans cette campagne.")

    # Créer le bénéficiaire et les réponses
    with transaction.atomic():
        beneficiary = Beneficiary.objects.create(
            campagne=campaign,
            zone=zone,
            organization=user.organization,
            nom=nom,
            prenom=prenom,
            telephone=telephone,
            sexe=beneficiary_data["sexe"],
            date_naissance=date_naissance,
            latitude=beneficiary_data["latitude"],
            longitude=beneficiary_data["longitude"],
            local_id=local_id,
            device_id=device_id,
            created_by=user,
            sync_status=Beneficiary.SyncStatus.SYNCED,
        )

        # Récupérer toutes les questions du formulaire
        questions = {str(q.id): q for q in formulaire.fields.all()}

        # Créer les réponses
        created_responses = []
        for resp_data in responses_data:
            question_id = str(resp_data["question_id"])
            value = resp_data["value"]

            if question_id not in questions:
                raise BeneficiaryError(f"Question {question_id} non trouvée dans ce formulaire.")

            question = questions[question_id]
            response = store_response(beneficiary, formulaire, question, value)
            created_responses.append(response)

        beneficiary = update_vulnerability_score(beneficiary)

    return beneficiary, created_responses, False


def update_beneficiary(beneficiary, validated_data, user):
    """
    Met à jour les informations personnelles d'un bénéficiaire.

    Args:
        beneficiary: Instance de Beneficiary
        validated_data: Données validées
        user: Utilisateur connecté

    Returns:
        Beneficiary: Le bénéficiaire mis à jour
    """
    # Vérifier les permissions
    if user.role == "AGENT" and beneficiary.created_by != user:
        raise BeneficiaryError("Vous ne pouvez modifier que vos propres bénéficiaires.")

    if beneficiary.organization != user.organization:
        raise BeneficiaryError("Ce bénéficiaire n'appartient pas à votre ONG.")

    # Vérifier doublon si téléphone changé
    if "telephone" in validated_data and validated_data["telephone"] != beneficiary.telephone:
        duplicate = check_duplicate_in_campaign(
            beneficiary.campagne,
            validated_data["telephone"],
            validated_data.get("nom", beneficiary.nom),
            validated_data.get("prenom", beneficiary.prenom),
            validated_data.get("date_naissance", beneficiary.date_naissance),
            exclude_id=beneficiary.id,
        )
        if duplicate:
            raise BeneficiaryError("Un autre bénéficiaire avec ce téléphone existe déjà dans cette campagne.")

    for field, value in validated_data.items():
        setattr(beneficiary, field, value)

    beneficiary.save()
    return beneficiary


def sync_pending_beneficiaries(pending_data_list, user):
    """
    Synchronise une liste de bénéficiaires en attente (mode hors ligne).
    Chaque bénéficiaire est traité dans sa propre transaction.

    Args:
        pending_data_list: Liste de données de bénéficiaires
        user: Utilisateur connecté (AGENT)

    Returns:
        dict: Résultat de la synchronisation {synced, duplicates, failed, details}
    """
    results = {
        "synced": 0,
        "duplicates": 0,
        "failed": 0,
        "details": [],
    }

    for data in pending_data_list:
        try:
            with transaction.atomic():
                beneficiary, responses, is_duplicate = create_beneficiary_with_responses(data, user)

            if is_duplicate:
                results["duplicates"] += 1
                results["details"].append({
                    "local_id": str(data["local_id"]),
                    "status": "DUPLICATE",
                    "beneficiary_id": str(beneficiary.id),
                })
            else:
                results["synced"] += 1
                results["details"].append({
                    "local_id": str(data["local_id"]),
                    "status": "SYNCED",
                    "beneficiary_id": str(beneficiary.id),
                })

        except BeneficiaryError as e:
            results["failed"] += 1
            results["details"].append({
                "local_id": str(data.get("local_id", "unknown")),
                "status": "FAILED",
                "error": str(e),
            })
        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "local_id": str(data.get("local_id", "unknown")),
                "status": "FAILED",
                "error": f"Erreur inattendue : {str(e)}",
            })

    return results


def _find_response_for_criterion(criterion, responses_by_qid, responses_by_label, all_responses, index=None):
    """
    Associe un critère de projet à la réponse correspondante du bénéficiaire :
    1. Par question_id (si relié explicitement)
    2. Par correspondance du libellé de la question et du nom du critère (insensible à la casse/accents)
    3. Par inclusion de texte (sous-chaîne)
    4. Par ordre d'index si les nombres d'éléments coïncident
    """
    if criterion.question_id and str(criterion.question_id) in responses_by_qid:
        return responses_by_qid[str(criterion.question_id)]

    crit_norm = normalize_region_name(criterion.nom)
    if crit_norm and crit_norm in responses_by_label:
        return responses_by_label[crit_norm]

    if crit_norm:
        for lbl_norm, resp in responses_by_label.items():
            if crit_norm in lbl_norm or lbl_norm in crit_norm:
                return resp

    if index is not None and 0 <= index < len(all_responses):
        return all_responses[index]

    return None


def calculate_vulnerability_score(beneficiary):
    """
    Calcule le score de vulnérabilité d'un bénéficiaire selon les critères du projet.

    Règles métier :
    - Chaque critère du projet a un poids (ex: 30, 25, 20, 15, 10 → total 100).
    - Si la réponse du bénéficiaire pour ce critère est "Oui" / vulnérable → on ajoute le poids.
    - Score final = somme des poids cochés (entre 0 et 100).
    """
    from decimal import Decimal

    try:
        campagne = getattr(beneficiary, "campagne", None)
        if not campagne:
            return Decimal("0")

        project = _get_project_from_campaign(campagne)
        if not project:
            return Decimal("0")

        criteria = list(project.criteres.filter(actif=True).select_related("question").order_by("id"))
        if not criteria:
            return Decimal("0")

        responses = list(beneficiary.responses.select_related("question").all())
        if not responses:
            return Decimal("0")

        responses_by_qid = {
            str(r.question_id): r for r in responses if r.question_id
        }
        responses_by_label = {
            normalize_region_name(r.question.label): r for r in responses if r.question and r.question.label
        }

        score = Decimal("0")

        for idx, criterion in enumerate(criteria):
            response = _find_response_for_criterion(
                criterion,
                responses_by_qid,
                responses_by_label,
                responses,
                index=idx,
            )
            if response and _evaluate_vulnerability(response, criterion):
                score += Decimal(str(criterion.poids or 0))

        return min(score, Decimal("100")).quantize(Decimal("0.01"))

    except Exception as e:
        logger.error(f"Score calculation failed for beneficiary {beneficiary.id}: {e}")
        return Decimal("0")


def _evaluate_vulnerability(response, criterion) -> bool:
    """
    Évalue si une réponse indique une vulnérabilité pour le critère donné.
    """
    if response is None:
        return False

    valeur = _extraire_valeur_reponse(response)
    if valeur is None:
        return False

    # 1. Si valeur booléenne
    if isinstance(valeur, bool):
        if criterion.vulnerable_values:
            val_str = "oui" if valeur else "non"
            return _check_vulnerability(val_str, criterion.vulnerable_values, getattr(criterion, "vulnerable_operator", "contains") or "contains")
        return valeur is True

    # 2. Si configuration spécifique sur le critère
    if criterion.vulnerable_values and criterion.vulnerable_operator:
        return _check_vulnerability(valeur, criterion.vulnerable_values, criterion.vulnerable_operator)

    # 3. Logique par défaut (détection des réponses positives / Oui)
    return _default_vulnerability_check(response)


def _check_vulnerability(valeur, vulnerable_values, operator) -> bool:
    """Vérifie la vulnérabilité selon l'opérateur et les valeurs configurées."""
    if valeur is None:
        return False

    val_str = str(valeur).strip().lower()
    vuln_lowered = [str(v).strip().lower() for v in vulnerable_values]

    if operator == "equals":
        return val_str in vuln_lowered or (val_str in {"oui", "true", "1", "yes"} and any(v in {"oui", "true", "1", "yes"} for v in vuln_lowered))

    if operator == "contains":
        return any(v in val_str or val_str in v for v in vuln_lowered)

    if operator == "in":
        return val_str in vuln_lowered

    if operator == "lt":
        try:
            return float(valeur) < float(vulnerable_values[0])
        except (ValueError, TypeError, IndexError):
            return False

    if operator == "gt":
        try:
            return float(valeur) > float(vulnerable_values[0])
        except (ValueError, TypeError, IndexError):
            return False

    return val_str in vuln_lowered


def _default_vulnerability_check(response) -> bool:
    """Logique par défaut pour détecter une réponse affirmative / vulnérable."""
    if response.value_boolean is not None:
        return response.value_boolean is True

    if response.value_number is not None:
        val = float(response.value_number)
        return val == 1.0 or val > 0

    if response.value_text is not None and response.value_text != "":
        texte = str(response.value_text).lower().strip()
        if texte in {"oui", "yes", "true", "1", "vrai", "on", "ok"}:
            return True
        vulnerable_keywords = {
            "oui", "yes", "true", "1", "handicap", "malade", "maladie",
            "faible", "très faible", "tres faible", "sans emploi", "chomeur",
            "sans soutien", "manque", "fragile", "difficulte", "besoins",
            "moins de 5", "moins de 5 ans", "enfant", "personne âgée",
            "personne agee", "foyer nombreux", "veuf", "veuve", "orphelin",
            "déplacé", "deplace", "réfugié", "refugie", "sans abri",
            "sans domicile", "chronique", "grave", "critique", "severe",
            "analphabete", "non scolarise", "sans revenu", "pauvre"
        }
        return any(kw in texte for kw in vulnerable_keywords)

    if response.value_json is not None:
        val_json = response.value_json
        if isinstance(val_json, bool):
            return val_json is True
        val_str = str(val_json).lower().strip()
        return any(k in val_str for k in ["oui", "yes", "true", "1", "vrai"])

    return False


def _extraire_valeur_reponse(response):
    """
    Extrait la valeur lisible d'une FormResponse.
    """
    if response.value_boolean is not None:
        return response.value_boolean
    if response.value_number is not None:
        return response.value_number
    if response.value_text is not None and response.value_text != "":
        return response.value_text
    if response.value_json is not None:
        return response.value_json
    if response.value_date is not None:
        return response.value_date
    return None


def _est_reponse_vulnerable(valeur):
    """
    Détermine si une valeur indique une vulnérabilité.
    """
    if valeur is None:
        return False

    if isinstance(valeur, bool):
        return valeur is True

    if isinstance(valeur, (int, float, Decimal)):
        return float(valeur) == 1.0 or float(valeur) > 0

    texte = str(valeur).lower().strip()
    if texte in {"oui", "yes", "true", "1", "vrai", "on", "ok"}:
        return True
    valeurs_vulnerables = [
        "oui", "true", "1", "handicap", "malade", "maladie",
        "faible", "très faible", "tres faible", "sans emploi",
        "moins de 5", "moins de 5 ans", "enfant", "personne âgée",
        "personne agee", "foyer nombreux", "veuf", "orphelin",
        "déplacé", "deplace", "réfugié", "refugie", "sans abri",
        "sans domicile", "chronique", "grave", "critique",
    ]
    return any(v in texte for v in valeurs_vulnerables)


def update_vulnerability_score(beneficiary):
    """
    Met à jour le score de vulnérabilité d'un bénéficiaire.
    Args:
        beneficiary: Instance de Beneficiary
    Returns:
        Beneficiary: Le bénéficiaire avec score mis à jour
    """
    score = calculate_vulnerability_score(beneficiary)
    beneficiary.score_vulnerabilite = score
    beneficiary.save(update_fields=["score_vulnerabilite", "updated_at"])
    return beneficiary


# Alias pour compatibilité avec les vues
update_ai_score = update_vulnerability_score


# ─────────────────────────────────────────────────────────────────────────────
# Carte des Priorités — Calcul des scores par région
# ─────────────────────────────────────────────────────────────────────────────

def _get_niveau_et_couleur(score):
    """Retourne le niveau et la couleur selon le score."""
    score_int = int(score or 0)
    if score_int >= 80:
        return "Très élevée", "red"
    elif score_int >= 60:
        return "Élevée", "orange"
    elif score_int >= 40:
        return "Moyenne", "yellow"
    else:
        return "Faible", "green"


def normalize_region_name(value):
    # Normalise un nom de region pour des comparaisons fiables.
    # Zone.region / Project.region sont des champs texte libres : « Thiès »,
    # « Thies », « SAINT-LOUIS », « saint louis »... alors que la carte SVG
    # (GeoJSON) utilise des noms normalises. Sans normalisation, un clic sur
    # « Thiès » ne retrouve aucune zone saisie « Thies ».
    # Retourne : sans accents, minuscules, tirets/underscores -> espaces.
    import unicodedata
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    space = chr(32)
    text = text.replace("-", space).replace("_", space)
    return " ".join(text.lower().split())


def _region_variants(region_name):
    # Retourne les variantes de saisie probables d'un nom de region.
    normalized = normalize_region_name(region_name)
    if not normalized:
        return []
    return [
        value
        for value in {region_name, normalized, normalized.title(), normalized.capitalize()}
        if value
    ]


def _generer_summary(region_name, zones, total_beneficiaires):
    """
    Génère automatiquement un résumé intelligent de la région.

    Args:
        region_name: Nom de la région
        zones: Liste de zones triées par score décroissant (chaque zone est un dict)
        total_beneficiaires: Nombre total de bénéficiaires dans la région

    Returns:
        str: Résumé textuel formaté
    """
    nb_zones = len(zones)
    zone_labels = {1: "zone", "plural": "zones"}
    label_zone = zone_labels[1] if nb_zones == 1 else zone_labels["plural"]

    summary = (
        f"La région de {region_name} regroupe {total_beneficiaires} bénéficiaire"
        f"{'s' if total_beneficiaires > 1 else ''} répartis dans {nb_zones} {label_zone}."
    )

    if zones:
        zone_top = zones[0]
        score_top = zone_top.get("score_moyen", 0)
        if score_top >= 60:
            summary += (
                f" {zone_top['nom']} présente le score moyen le plus élevé"
                f" ({score_top}/100) et constitue la première priorité d'intervention."
            )
        elif score_top >= 40:
            summary += (
                f" {zone_top['nom']} est la zone la plus prioritaire avec un score"
                f" de {score_top}/100."
            )

        # Mentionner les zones urgentes suivantes
        urgentes = [z for z in zones[1:3] if z.get("score_moyen", 0) >= 40]
        if urgentes:
            noms = " et ".join(z["nom"] for z in urgentes)
            verb = "nécessitent" if len(urgentes) > 1 else "nécessite"
            summary += f" {noms} {verb} également une intervention dans les prochains jours."

    return summary

def _generer_observations(region_name, zones, total_beneficiaires):
    # Genere une liste d'observations factuelles a partir des donnees calculees.
    observations = []
    if not zones:
        return observations
    tres_elevees = [
        b
        for z in zones
        for b in z.get("beneficiaires", [])
        if (b.get("score") or 0) >= 80
    ]
    if tres_elevees:
        observations.append(
            f"{len(tres_elevees)} bénéficiaire"
            f"{'s sont classés' if len(tres_elevees) > 1 else ' est classé'} "
            "Très élevée."
        )

    zone_top = zones[0]
    observations.append(
        f"{zone_top['nom']} concentre la vulnérabilité la plus forte "
        f"(score moyen {zone_top.get('score_moyen', 0)}/100)."
    )

    if len(zones) > 1:
        zone_2 = zones[1]
        observations.append(
            f"{zone_2['nom']} représente la deuxième zone prioritaire "
            f"(score moyen {zone_2.get('score_moyen', 0)}/100)."
        )

    return observations

def _generer_recommandations(region_name, zones, total_beneficiaires):
    # Genere des recommandations actionnables, sans justification detaillee.
    recommandations = []
    if not zones:
        return [
            "Programmer une collecte terrain dans cette région.",
        ]

    zone_top = zones[0]
    recommandations.append(
        f"Prioriser les distributions à {zone_top['nom']}."
    )

    if len(zones) > 1:
        recommandations.append(
            f"Renforcer l'équipe terrain à {zones[1]['nom']}."
        )

    recommandations.append(
        "Mettre à jour les bénéficiaires avant la prochaine mission."
    )

    return recommandations


def _get_criteres_beneficiaire(beneficiary, criteria_list):
    """
    Retourne la liste des critères avec la réponse et les points obtenus
    pour un bénéficiaire donné (utilisé par la Carte des Priorités).

    Args:
        beneficiary: Instance de Beneficiary (avec responses prefetched)
        criteria_list: Liste des critères actifs du projet

    Returns:
        list[dict]: [{nom, reponse, points, poids_max, obtenu}]
    """
    responses = list(beneficiary.responses.select_related("question").all())
    responses_by_qid = {
        str(r.question_id): r for r in responses if r.question_id
    }
    responses_by_label = {
        normalize_region_name(r.question.label): r for r in responses if r.question and r.question.label
    }

    criteres_detail = []
    for idx, criterion in enumerate(criteria_list):
        response = _find_response_for_criterion(
            criterion,
            responses_by_qid,
            responses_by_label,
            responses,
            index=idx,
        )
        if response:
            is_vulnerable = _evaluate_vulnerability(response, criterion)
            points = criterion.poids if is_vulnerable else 0

            # Formatter la réponse lisible
            valeur = _extraire_valeur_reponse(response)
            if isinstance(valeur, bool):
                reponse_lisible = "Oui" if valeur else "Non"
            elif valeur is None:
                reponse_lisible = "—"
            else:
                reponse_lisible = str(valeur)
        else:
            is_vulnerable = False
            points = 0
            reponse_lisible = "—"

        criteres_detail.append({
            "nom": criterion.nom,
            "reponse": reponse_lisible,
            "points": points,
            "poids_max": criterion.poids,
            "obtenu": is_vulnerable,
        })

    return criteres_detail


def _calculer_age(date_naissance):
    """Calcule l'âge à partir de la date de naissance."""
    from django.utils import timezone as tz
    today = tz.now().date()
    try:
        age = today.year - date_naissance.year - (
            (today.month, today.day) < (date_naissance.month, date_naissance.day)
        )
        return age
    except Exception:
        return None


def region_exists_in_project(project, region_name):
    """
    Indique si une region existe pour un projet donne.

    Une region est consideree comme existante si au moins une zone du projet
    (ou un beneficiaire du projet) lui est rattachee, ou si elle correspond
    a la region declaree du projet.
    """
    region_normalized = normalize_region_name(region_name)
    if not region_normalized:
        return False
    # 1) La region declaree sur le projet
    if normalize_region_name(project.region) == region_normalized:
        return True
    variants = _region_variants(region_name)
    # 2) Une zone portee par un beneficiaire du projet dans cette region
    #    (on reste centre sur le projet et non sur toute l'organisation).
    if Beneficiary.objects.filter(
        campagne__projet=project,
        zone__region__in=variants,
    ).exists():
        return True
    # 3) Fallback : une zone de l'organisation correspond au nom, pour afficher
    #    une region declaree mais encore sans beneficiaire.
    return Zone.objects.filter(
        organization=project.organization,
        region__in=variants,
    ).exists()


def _get_region_zones(project, region_name):
    # Toutes les zones d'une region pour un projet donne.
    #
    # Sources (dans l'ordre de priorite) :
    #   1) les zones rattachees aux campagnes du projet ;
    #   2) a defaut, les zones de l'ONG dans cette region.
    #
    # Ces zones doivent etre renvoyees meme sans aucun beneficiaire afin que le
    # panneau lateral affiche l'integralite de la region (score 0 / 0 ben.).
    variants = _region_variants(region_name)
    if not variants:
        return []

    from apps.campaigns.models import Campaign
    project_zone_ids = (
        Campaign.objects
        .filter(projet=project)
        .values_list("zones__id", flat=True)
    )
    zones = list(
        Zone.objects
        .filter(id__in=project_zone_ids, region__in=variants)
        .order_by("nom")
    )
    if zones:
        return zones
    # Fallback : aucune campagne/zone rattachee au projet pour cette region.
    return list(
        Zone.objects
        .filter(organization=project.organization, region__in=variants)
        .order_by("nom")
    )


def build_region_priorities(project, region_name):
    """
    Construit les données de priorité pour une région donnée dans un projet.

    Args:
        project: Instance de Project
        region_name: Nom de la région (string)

    Returns:
        dict: {region, summary, score_region, total_beneficiaires, zones}
    """
    # Critères actifs du projet (avec question liée)
    criteria_list = list(
        project.criteres.filter(actif=True).select_related("question")
    )

    # Tous les bénéficiaires du projet dans cette région (matching tolerant :
    # « Thiès » retrouve les zones saisies « Thies »).
    beneficiaries = (
        Beneficiary.objects
        .filter(
            campagne__projet=project,
            zone__region__in=_region_variants(region_name),
        )
        .select_related("zone", "campagne")
        .prefetch_related("responses__question")
        .order_by("-score_vulnerabilite")
    )

    # Toutes les zones de la region (celles rattachees aux campagnes du projet,
    # sinon celles de l'ONG). Elles doivent apparaitre meme sans beneficiaire.
    region_zones = _get_region_zones(project, region_name)

    # Pre-remplissage : une entree par zone de la region (0 beneficiaire par defaut).
    zones_data = {}
    for zone in region_zones:
        zones_data[str(zone.id)] = {
            "id": str(zone.id),
            "nom": zone.nom,
            "scores": [],
            "beneficiaires": [],
        }

    # Regroupement des beneficiaires par zone
    for b in beneficiaries:
        zone = b.zone
        if zone is None:
            # Bénéficiaire orphelin de zone : ignoré, il ne fausse pas les scores
            continue
        zone_id = str(zone.id)
        if zone_id not in zones_data:
            # Beneficiaire rattache a une zone hors du perimetre connu : on la
            # cree a la volee pour ne rien perdre.
            zones_data[zone_id] = {
                "id": zone_id,
                "nom": zone.nom,
                "scores": [],
                "beneficiaires": [],
            }

        score_b = int(b.score_vulnerabilite or 0)
        zones_data[zone_id]["scores"].append(score_b)

        age = _calculer_age(b.date_naissance)
        criteres_detail = _get_criteres_beneficiaire(b, criteria_list)
        niveau_b, _ = _get_niveau_et_couleur(score_b)

        zones_data[zone_id]["beneficiaires"].append({
            "id": str(b.id),
            "nom_complet": f"{b.prenom} {b.nom}",
            "nom": b.nom,
            "prenom": b.prenom,
            "telephone": b.telephone,
            "sexe": b.sexe,
            "age": age,
            "date_naissance": str(b.date_naissance),
            "quartier": b.zone.departement if b.zone else "",
            "region": b.zone.region if b.zone else region_name,
            "zone_nom": b.zone.nom if b.zone else "",
            "score": score_b,
            "niveau": niveau_b,
            "criteres": criteres_detail,
        })

    # Construire la liste des zones triées par score moyen décroissant
    zones_list = []
    for zone_id, data in zones_data.items():
        scores = data["scores"]
        score_moyen = round(sum(scores) / len(scores)) if scores else 0
        niveau_zone, couleur_zone = _get_niveau_et_couleur(score_moyen)

        # Trier les bénéficiaires par score décroissant
        bens_sorted = sorted(data["beneficiaires"], key=lambda x: x["score"], reverse=True)

        zones_list.append({
            "id": zone_id,
            "nom": data["nom"],
            # Alias compatibles avec le contrat JSON attendu (score / beneficiaires).
            "score": score_moyen,
            "beneficiaires_count": len(bens_sorted),
            "score_moyen": score_moyen,
            "niveau": niveau_zone,
            "couleur": couleur_zone,
            "total_beneficiaires": len(bens_sorted),
            "beneficiaires": bens_sorted,
        })

    zones_list.sort(key=lambda z: z["score_moyen"], reverse=True)

    # Score moyen de la région
    all_scores = [b["score"] for z in zones_list for b in z["beneficiaires"]]
    score_region = round(sum(all_scores) / len(all_scores)) if all_scores else 0
    total_beneficiaires = len(all_scores)

    summary = _generer_summary(region_name, zones_list, total_beneficiaires)
    observations = _generer_observations(region_name, zones_list, total_beneficiaires)
    recommandations = _generer_recommandations(region_name, zones_list, total_beneficiaires)
    niveau_region, couleur_region = _get_niveau_et_couleur(score_region)

    return {
        "region": region_name,
        "summary": summary,
        "observations": observations,
        "recommandations": recommandations,
        "score_region": score_region,
        "niveau_region": niveau_region,
        "couleur_region": couleur_region,
        "total_beneficiaires": total_beneficiaires,
        "nb_zones": len(zones_list),
        "zones": zones_list,
    }


def build_all_regions_scores(project):
    """
    Retourne la liste de toutes les régions avec leur score agrégé
    pour coloriser la carte SVG du Sénégal.

    Args:
        project: Instance de Project

    Returns:
        list[dict]: [{region, score, total_beneficiaires, niveau, couleur}]
    """
    from django.db.models import Avg, Count
    # 1) Regions ayant des bénéficiaires collectés sur ce projet (score agrégé)
    result = (
        Beneficiary.objects
        .filter(campagne__projet=project)
        .values("zone__region")
        .annotate(
            score_moyen=Avg("score_vulnerabilite"),
            total=Count("id"),
        )
        .order_by("-score_moyen")
    )

    # Index par nom normalisé pour fusionner sans doublon les variantes de saisie.
    regions_by_key = {}
    for row in result:
        region_name = row["zone__region"] or "Inconnue"
        score = round(row["score_moyen"] or 0)
        niveau, couleur = _get_niveau_et_couleur(score)
        key = normalize_region_name(region_name)
        regions_by_key[key] = {
            "region": region_name,
            "score": score,
            "score_region": score,
            "total_beneficiaires": row["total"],
            "niveau": niveau,
            "couleur": couleur,
        }

    # 2) Regions declarees sur le projet ou portant des zones de l'organisation :
    #    elles doivent apparaître sur la carte même sans bénéficiaire (score 0).
    declared_names = []
    if project.region:
        declared_names.append(project.region)
    declared_names.extend(
        Zone.objects
        .filter(organization=project.organization)
        .values_list("region", flat=True)
        .distinct()
    )

    for region_name in declared_names:
        if not region_name:
            continue
        key = normalize_region_name(region_name)
        if key in regions_by_key:
            continue
        regions_by_key[key] = {
            "region": region_name,
            "score": 0,
            "score_region": 0,
            "total_beneficiaires": 0,
            "niveau": "Aucune donnée",
            "couleur": "grey",
        }

    # Tri : régions avec bénéficiaires d'abord, par score décroissant.
    regions_list = sorted(
        regions_by_key.values(),
        key=lambda r: (r["total_beneficiaires"] == 0, -(r["score"] or 0)),
    )

    return regions_list


def get_zone_beneficiaries_table_data(zone_id, user):
    """
    Retourne la liste complète des bénéficiaires d'une zone avec scores,
    informations personnelles et détails des critères répondus.
    """
    from apps.zones.models import Zone
    from apps.projects.models import Project, ProjectCriteria
    from django.db.models import Q

    zone = Zone.objects.filter(id=zone_id).first()
    if not zone:
        raise BeneficiaryError("Zone introuvable.")

    if user.role != "SUPER_ADMIN" and zone.organization != user.organization:
        raise BeneficiaryError("Cette zone n'appartient pas à votre ONG.")

    beneficiaries = (
        Beneficiary.objects
        .filter(zone=zone)
        .select_related("campagne__projet", "created_by", "zone")
        .prefetch_related("responses__question")
        .order_by("-score_vulnerabilite")
    )

    if user.role == "CHEF_PROJET":
        beneficiaries = beneficiaries.filter(
            Q(campagne__projet__chef_projet=user) | Q(created_by=user)
        )

    # Récupérer les critères des projets concernés
    project_ids = list(
        beneficiaries.exclude(campagne__projet__isnull=True)
        .values_list("campagne__projet_id", flat=True)
        .distinct()
    )
    criteria_list = []
    if project_ids:
        criteria_list = list(
            ProjectCriteria.objects
            .filter(projet_id__in=project_ids, actif=True)
            .select_related("question")
        )

    bens_data = []
    scores = []
    for b in beneficiaries:
        score_val = int(b.score_vulnerabilite or 0)
        scores.append(score_val)
        age = _calculer_age(b.date_naissance)
        niveau, couleur = _get_niveau_et_couleur(score_val)

        # Critères évalués pour ce bénéficiaire
        criteres_detail = _get_criteres_beneficiaire(b, criteria_list)

        # Réponses brutes
        raw_responses = []
        for r in b.responses.all():
            val = _extraire_valeur_reponse(r)
            raw_responses.append({
                "id": str(r.id),
                "question": r.question.label if r.question else "",
                "type": r.question.type if r.question else "text",
                "valeur": val,
            })

        bens_data.append({
            "id": str(b.id),
            "nom": b.nom,
            "prenom": b.prenom,
            "nom_complet": f"{b.prenom} {b.nom}".strip(),
            "telephone": b.telephone,
            "sexe": b.sexe,
            "date_naissance": str(b.date_naissance) if b.date_naissance else "",
            "age": age,
            "quartier": zone.departement or zone.nom,
            "region": zone.region,
            "zone_nom": zone.nom,
            "score": score_val,
            "niveau": niveau,
            "couleur": couleur,
            "criteres": criteres_detail,
            "responses": raw_responses,
            "campagne": {
                "id": str(b.campagne.id),
                "nom": b.campagne.nom,
            } if b.campagne else None,
            "created_at": b.created_at.isoformat() if hasattr(b, "created_at") and b.created_at else "",
        })

    score_moyen = round(sum(scores) / len(scores)) if scores else 0
    niveau_moyen, couleur_moyen = _get_niveau_et_couleur(score_moyen)

    return {
        "zone": {
            "id": str(zone.id),
            "nom": zone.nom,
            "region": zone.region,
            "departement": zone.departement or zone.nom,
            "score_moyen": score_moyen,
            "niveau": niveau_moyen,
            "couleur": couleur_moyen,
            "total_beneficiaires": len(bens_data),
        },
        "beneficiaires": bens_data,
        "criteres_projet": [
            {
                "id": str(c.id),
                "nom": c.nom,
                "poids": c.poids,
                "question": c.question.label if c.question else "",
            }
            for c in criteria_list
        ],
    }