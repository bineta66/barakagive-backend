from django.utils import timezone
from django.db import transaction, models

from apps.campaigns.models import Campaign
from apps.projects.models import Project
from .models import Formulaire, FormField


class FormulaireError(Exception):
    """Exception personnalisée pour les erreurs de formulaire."""
    pass


def validate_campaign_for_chef_projet(campaign, user):
    """
    Vérifie que la campagne existe, appartient à la même ONG
    et que le chef de projet est autorisé sur le projet de cette campagne.

    Args:
        campaign: Instance de Campaign
        user: Instance de User (CHEF_PROJET)

    Returns:
        Campaign: La campagne validée

    Raises:
        FormulaireError: Si les conditions ne sont pas remplies
    """
    if not campaign:
        raise FormulaireError("La campagne spécifiée n'existe pas.")

    if campaign.organization != user.organization:
        raise FormulaireError("La campagne n'appartient pas à votre ONG.")

    if campaign.projet.chef_projet != user:
        raise FormulaireError("Vous n'êtes pas le chef de projet de cette campagne.")

    return campaign


def create_formulaire(validated_data, user):
    """
    Crée un formulaire avec ses questions.

    Args:
        validated_data: Données validées (campagne_id, nom, description, fields)
        user: Utilisateur connecté (CHEF_PROJET)

    Returns:
        Formulaire: Le formulaire créé

    Raises:
        FormulaireError: Si une validation échoue
    """
    campagne_id = validated_data.get("campagne_id")
    nom = validated_data.get("nom")
    description = validated_data.get("description", "")
    fields_data = validated_data.get("fields", [])

    if not campagne_id:
        raise FormulaireError("L'ID de la campagne est obligatoire.")

    try:
        campaign = Campaign.objects.select_related("projet", "organization").get(id=campagne_id)
    except Campaign.DoesNotExist:
        raise FormulaireError("La campagne spécifiée n'existe pas.")

    validate_campaign_for_chef_projet(campaign, user)

    with transaction.atomic():
        formulaire = Formulaire.objects.create(
            campagne=campaign,
            organization=user.organization,
            nom=nom,
            description=description,
            created_by=user,
            version=1,
            statut=Formulaire.Statut.BROUILLON,
        )

        for idx, field_data in enumerate(fields_data):
            ordre = field_data.get("ordre", idx + 1)
            FormField.objects.create(
                formulaire=formulaire,
                label=field_data["label"],
                type=field_data["type"],
                obligatoire=field_data.get("obligatoire", False),
                ordre=ordre,
                placeholder=field_data.get("placeholder", ""),
                options=field_data.get("options"),
            )

    return formulaire


def update_formulaire(formulaire, validated_data, user):
    """
    Met à jour un formulaire (nom, description, statut).

    Args:
        formulaire: Instance de Formulaire
        validated_data: Données validées
        user: Utilisateur connecté

    Returns:
        Formulaire: Le formulaire mis à jour
    """
    if "nom" in validated_data:
        formulaire.nom = validated_data["nom"]

    if "description" in validated_data:
        formulaire.description = validated_data["description"]

    if "statut" in validated_data:
        formulaire.statut = validated_data["statut"]

    formulaire.save()
    return formulaire


def publish_formulaire(formulaire, user):
    """
    Publie un formulaire (statut BROUILLON -> PUBLIE).

    Conditions :
    - Au moins une question
    - Statut actuel = BROUILLON

    Args:
        formulaire: Instance de Formulaire
        user: Utilisateur connecté

    Returns:
        Formulaire: Le formulaire publié

    Raises:
        FormulaireError: Si les conditions ne sont pas remplies
    """
    if formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Seul un formulaire en brouillon peut être publié.")

    if formulaire.fields.count() == 0:
        raise FormulaireError("Le formulaire doit contenir au moins une question pour être publié.")

    formulaire.statut = Formulaire.Statut.PUBLIE
    formulaire.save()
    return formulaire


def add_question(formulaire, validated_data, user):
    """
    Ajoute une question à un formulaire.

    Args:
        formulaire: Instance de Formulaire
        validated_data: Données validées de la question
        user: Utilisateur connecté

    Returns:
        FormField: La question créée
    """
    if formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Impossible d'ajouter une question à un formulaire non-brouillon.")

    max_ordre = formulaire.fields.aggregate(models.Max("ordre"))["ordre__max"] or 0
    ordre = validated_data.get("ordre", max_ordre + 1)

    question = FormField.objects.create(
        formulaire=formulaire,
        label=validated_data["label"],
        type=validated_data["type"],
        obligatoire=validated_data.get("obligatoire", False),
        ordre=ordre,
        placeholder=validated_data.get("placeholder", ""),
        options=validated_data.get("options"),
    )

    return question


def update_question(question, validated_data, user):
    """
    Met à jour une question.

    Args:
        question: Instance de FormField
        validated_data: Données validées
        user: Utilisateur connecté

    Returns:
        FormField: La question mise à jour
    """
    if question.formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Impossible de modifier une question d'un formulaire non-brouillon.")

    for field, value in validated_data.items():
        setattr(question, field, value)

    question.save()
    return question


def duplicate_question(question, user):
    """
    Duplique une question dans le même formulaire.

    Args:
        question: Instance de FormField à dupliquer
        user: Utilisateur connecté

    Returns:
        FormField: La nouvelle question dupliquée

    Raises:
        FormulaireError: Si le formulaire n'est pas en brouillon
    """
    if question.formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Impossible de dupliquer une question d'un formulaire non-brouillon.")

    max_ordre = question.formulaire.fields.aggregate(models.Max("ordre"))["ordre__max"] or 0

    new_question = FormField.objects.create(
        formulaire=question.formulaire,
        label=question.label,
        type=question.type,
        obligatoire=question.obligatoire,
        ordre=max_ordre + 1,
        placeholder=question.placeholder,
        options=question.options,
    )

    return new_question


def delete_question(question, user):
    """
    Supprime une question.

    Args:
        question: Instance de FormField
        user: Utilisateur connecté

    Raises:
        FormulaireError: Si le formulaire n'est pas en brouillon
    """
    if question.formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Impossible de supprimer une question d'un formulaire non-brouillon.")

    question.delete()


def reorder_questions(formulaire, questions_data, user):
    """
    Réordonne les questions d'un formulaire.

    Args:
        formulaire: Instance de Formulaire
        questions_data: Liste de dicts {"id": UUID, "ordre": int}
        user: Utilisateur connecté

    Returns:
        QuerySet: Questions réordonnées

    Raises:
        FormulaireError: Si le formulaire n'est pas en brouillon ou IDs invalides
    """
    if formulaire.statut != Formulaire.Statut.BROUILLON:
        raise FormulaireError("Impossible de réordonner les questions d'un formulaire non-brouillon.")

    question_ids = [q["id"] for q in questions_data]
    questions = FormField.objects.filter(id__in=question_ids, formulaire=formulaire)

    if questions.count() != len(question_ids):
        found_ids = set(str(q.id) for q in questions)
        missing = [qid for qid in question_ids if str(qid) not in found_ids]
        raise FormulaireError(f"Questions non trouvées : {missing}")

    with transaction.atomic():
        for q_data in questions_data:
            FormField.objects.filter(id=q_data["id"]).update(ordre=int(q_data["ordre"]))

    return formulaire.fields.all().order_by("ordre")


def get_published_formulaires_for_agent(user):
    """
    Récupère les formulaires publiés accessibles à un agent.
    Un agent ne voit que les formulaires publiés des campagnes de son ONG.

    Args:
        user: Utilisateur connecté (AGENT)

    Returns:
        QuerySet: Formulaires publiés
    """
    return Formulaire.objects.filter(
        organization=user.organization,
        statut=Formulaire.Statut.PUBLIE,
    ).select_related("campagne", "campagne__projet").prefetch_related("fields")