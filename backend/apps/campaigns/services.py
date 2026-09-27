from django.db import transaction
from django.utils import timezone


def generate_campaign_code(project):
    """
    Génère le code de campagne au format :
    CMP-YYYY-REG-XXX

    Exemples :
    - CMP-2026-DKR-001
    - CMP-2026-DKR-002

    Args:
        project: Instance de Project

    Returns:
        str: Code de campagne unique
    """
    from apps.campaigns.models import Campaign

    year = timezone.now().year
    region_prefix = project.region[:3].upper() if project.region else "XXX"

    count = Campaign.objects.filter(
        code_campagne__startswith=f"CMP-{year}-{region_prefix}-"
    ).count()

    sequence = count + 1

    return f"CMP-{year}-{region_prefix}-{sequence:03d}"


def validate_zones_for_organization(zone_ids, organization):
    """
    Vérifie que toutes les zones existent et appartiennent à la même ONG.

    Args:
        zone_ids: Liste d'UUID de zones
        organization: Instance d'Organization

    Returns:
        QuerySet: Zones validées

    Raises:
        ValueError: Si une zone n'existe pas ou n'appartient pas à l'ONG
    """
    from apps.zones.models import Zone

    if not zone_ids:
        raise ValueError("Au moins une zone doit être sélectionnée.")

    zones = Zone.objects.filter(id__in=zone_ids, organization=organization)

    if zones.count() != len(zone_ids):
        found_ids = set(str(z.id) for z in zones)
        missing = [zid for zid in zone_ids if str(zid) not in found_ids]
        raise ValueError(
            f"Certaines zones n'existent pas ou n'appartiennent pas à votre ONG : {missing}"
        )

    return zones


def validate_project_for_chef_projet(project, user):
    """
    Vérifie que le projet existe, appartient à la même ONG
    et que le chef de projet est affecté à ce projet.

    Args:
        project: Instance de Project
        user: Instance de User (CHEF_PROJET)

    Returns:
        Project: Le projet validé

    Raises:
        ValueError: Si les conditions ne sont pas remplies
    """
    if not project:
        raise ValueError("Le projet spécifié n'existe pas.")

    if project.organization != user.organization:
        raise ValueError("Le projet n'appartient pas à votre ONG.")

    if project.chef_projet != user:
        raise ValueError("Vous n'êtes pas le chef de projet de ce projet.")

    return project


def validate_dates(date_debut, date_fin):
    """
    Vérifie que date_fin est postérieure à date_debut.

    Args:
        date_debut: Date de début
        date_fin: Date de fin

    Raises:
        ValueError: Si date_fin <= date_debut
    """
    if date_debut and date_fin and date_fin <= date_debut:
        raise ValueError("La date de fin doit être postérieure à la date de début.")


@transaction.atomic
def create_campaign(validated_data, user):
    """
    Crée une campagne avec toutes les validations métier.

    Args:
        validated_data: Données validées (projet, nom, description, zone_ids, date_debut, date_fin)
        user: Utilisateur connecté (CHEF_PROJET)

    Returns:
        Campaign: La campagne créée

    Raises:
        ValueError: Si une validation échoue
    """
    from apps.projects.models import Project
    from apps.campaigns.models import Campaign, CampagneAffectation
    from apps.accounts.models import User

    projet_id = validated_data.get("projet_id")
    nom = validated_data.get("nom")
    description = validated_data.get("description")
    zone_ids = validated_data.get("zone_ids", [])
    date_debut = validated_data.get("date_debut")
    date_fin = validated_data.get("date_fin")
    agent_assignments = validated_data.get("agents", [])

    if not projet_id:
        raise ValueError("L'ID du projet est obligatoire.")

    try:
        project = Project.objects.get(id=projet_id)
    except Project.DoesNotExist:
        raise ValueError("Le projet spécifié n'existe pas.")

    if user.role == User.Role.SUPER_ADMIN:
        organization = project.organization
    else:
        validate_project_for_chef_projet(project, user)
        organization = user.organization

    validate_zones_for_organization(zone_ids, organization)
    validate_dates(date_debut, date_fin)

    code_campagne = generate_campaign_code(project)

    campaign = Campaign.objects.create(
        projet=project,
        organization=organization,
        nom=nom,
        code_campagne=code_campagne,
        description=description,
        date_debut=date_debut,
        date_fin=date_fin,
        created_by=user,
    )

    if zone_ids:
        zones = validate_zones_for_organization(zone_ids, organization)
        campaign.zones.set(zones)

    # Un agent peut etre affecte a plusieurs zones : le meme agent_id peut
    # donc apparaitre plusieurs fois, avec une zone differente a chaque fois.
    # On refuse uniquement les doublons (agent, zone) strictement identiques.
    seen_pairs = set()
    for item in agent_assignments:
        key = (str(item["agent_id"]), (item.get("zone") or "").strip())
        if key in seen_pairs:
            raise ValueError(
                f"L'agent {key[0]} est déj\u00e0 affecté à la zone '{key[1]}'."
            )
        seen_pairs.add(key)

    agent_ids = [str(item["agent_id"]) for item in agent_assignments]

    numeric_agent_ids = []
    for aid in agent_ids:
        if aid.isdigit():
            numeric_agent_ids.append(int(aid))
        else:
            raise ValueError(f"Identifiant agent invalide : {aid}")

    agents = {
        str(agent.id): agent
        for agent in User.objects.filter(
            id__in=numeric_agent_ids,
            organization=organization,
        )
    }

    missing_ids = [aid for aid in agent_ids if aid not in agents]
    if missing_ids:
        raise ValueError(f"Agents introuvables : {missing_ids}")

    for assignment in agent_assignments:
        agent_id = str(assignment["agent_id"])
        agent = agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent introuvable : {agent_id}")

        # Une affectation est creee par zone affectee a l'agent.
        zone_names = list(assignment.get("zones") or [])
        if not zone_names:
            fallback = (assignment.get("zone") or "").strip()
            if fallback:
                zone_names = [fallback]
        if not zone_names:
            zone_names = [
                campaign.zones.values_list("nom", flat=True).first() or ""
            ]

        for zone_name in zone_names:
            if zone_name and not campaign.zones.filter(nom=zone_name).exists():
                raise ValueError(
                    f"La zone '{zone_name}' ne fait pas partie de la campagne."
                )
            CampagneAffectation.objects.create(
                campagne=campaign,
                agent=agent,
                zone=zone_name,
                objectif_beneficiaires=assignment["objectif"],
                created_by=user,
            )

    return campaign

@transaction.atomic
def assign_agent_zones(campaign, agent, zone_names, objectif=0, user=None):
    """
    Affecte un agent terrain a une ou plusieurs zones d'une campagne.

    Cette fonction est idempotente : les zones deja affectees sont conservees,
    les nouvelles sont creees. Les affectations existantes non listees sont
    supprimees (l'appel definit l'ensemble des zones de l'agent).

    Args:
        campaign: Instance de Campaign
        agent: Instance de User (role AGENT)
        zone_names: Iterable de noms de zones
        objectif: Objectif de beneficiaires (applique a chaque zone)
        user: Utilisateur a l'origine de l'operation

    Returns:
        list[CampagneAffectation]: Les affectations de l'agent pour la campagne

    Raises:
        ValueError: Si l'agent ou une zone est invalide
    """
    from apps.accounts.models import User
    from apps.campaigns.models import CampagneAffectation

    if agent.role != User.Role.AGENT:
        raise ValueError("Seul un agent terrain peut etre affecte a des zones.")

    if agent.organization != campaign.organization:
        raise ValueError("L'agent n'appartient pas a l'ONG de la campagne.")

    # Nettoyage / deduplication des noms de zones
    cleaned = []
    for name in zone_names or []:
        name = (name or "").strip()
        if name and name not in cleaned:
            cleaned.append(name)

    if not cleaned:
        raise ValueError("Au moins une zone doit etre affectee a l'agent.")

    # Toutes les zones doivent faire partie de la campagne
    campaign_zone_names = list(campaign.zones.values_list("nom", flat=True))
    invalid = [n for n in cleaned if n not in campaign_zone_names]
    if invalid:
        raise ValueError(
            f"Ces zones ne font pas partie de la campagne : {invalid}"
        )

    existing = {
        a.zone: a
        for a in CampagneAffectation.objects.filter(
            campagne=campaign, agent=agent
        )
    }

    # Supprimer les affectations qui ne sont plus demandees
    for zone_name, affectation in existing.items():
        if zone_name not in cleaned:
            affectation.delete()

    # Creer / mettre a jour les affectations demandees
    for zone_name in cleaned:
        affectation = existing.get(zone_name)
        if affectation is None:
            CampagneAffectation.objects.create(
                campagne=campaign,
                agent=agent,
                zone=zone_name,
                objectif_beneficiaires=objectif,
                created_by=user or agent,
            )
        elif affectation.objectif_beneficiaires != objectif:
            affectation.objectif_beneficiaires = objectif
            affectation.save(update_fields=["objectif_beneficiaires"])

    return list(
        CampagneAffectation.objects.filter(campagne=campaign, agent=agent)
    )
