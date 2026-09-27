import logging
import requests
from django.conf import settings
from celery import shared_task
from django.utils import timezone
from django.db import models

from apps.campaigns.models import Campaign
from apps.beneficiaries.models import Beneficiary
from apps.zones.models import Zone
from apps.finance.models import Depense, Budget
from apps.ia.models import IAnalyse

logger = logging.getLogger(__name__)


def compute_executive_payload(campaign):
    """Compute executive insight payload from Django data"""
    # Beneficiaries stats
    beneficiaries = Beneficiary.objects.filter(campagne=campaign)
    total_beneficiaries = beneficiaries.count()
    
    # Zones with beneficiary counts and scores
    zones = Zone.objects.filter(campaigns=campaign, organization=campaign.organization)
    zones_data = []
    for zone in zones:
        zone_beneficiaries = beneficiaries.filter(zone=zone)
        avg_score = zone_beneficiaries.exclude(score_vulnerabilite__isnull=True).aggregate(
            avg_score=models.Avg('score_vulnerabilite')
        )['avg_score'] or 0
        zones_data.append({
            "id": str(zone.id),
            "nom": zone.nom,
            "region": zone.region,
            "departement": zone.departement,
            "beneficiaires": zone_beneficiaries.count(),
            "score_moyen": float(avg_score),
            "latitude": float(zone.latitude),
            "longitude": float(zone.longitude),
        })
    
    # Budget data
    budgets = Budget.objects.filter(projet=campaign.projet)
    total_budget = sum(float(b.montant_total) for b in budgets)
    
    depenses = Depense.objects.filter(projet=campaign.projet)
    total_depenses = sum(float(d.montant) for d in depenses)
    
    # Expenses by zone and category
    depenses_par_zone = {}
    depenses_par_categorie = {}
    for depense in depenses:
        zone_name = depense.projet.zone.nom if hasattr(depense.projet, 'zone') and depense.projet.zone else "Non assigné"
        depenses_par_zone[zone_name] = depenses_par_zone.get(zone_name, 0) + float(depense.montant)
        
        cat_name = depense.poste_budgetaire.libelle if depense.poste_budgetaire else "Non catégorisé"
        depenses_par_categorie[cat_name] = depenses_par_categorie.get(cat_name, 0) + float(depense.montant)
    
    return {
        "campagne_id": str(campaign.id),
        "nom": campaign.nom,
        "date_debut": campaign.date_debut.isoformat(),
        "date_fin": campaign.date_fin.isoformat(),
        "total_beneficiaires": total_beneficiaries,
        "zones": zones_data,
        "budgets": [
            {"id": str(b.id), "montant_total": float(b.montant_total), "statut": b.statut}
            for b in budgets
        ],
        "total_budget": total_budget,
        "total_depenses": total_depenses,
        "solde": total_budget - total_depenses,
        "taux_execution": (total_depenses / total_budget * 100) if total_budget > 0 else 0,
        "depenses_par_zone": depenses_par_zone,
        "depenses_par_categorie": depenses_par_categorie,
    }


def compute_finance_payload(campaign):
    """Compute finance payload for budget analysis"""
    budgets = Budget.objects.filter(projet=campaign.projet)
    total_budget = sum(float(b.montant_total) for b in budgets)
    
    depenses = Depense.objects.filter(projet=campaign.projet)
    total_depenses = sum(float(d.montant) for d in depenses)
    solde = total_budget - total_depenses
    taux = (total_depenses / total_budget * 100) if total_budget > 0 else 0
    
    # Expenses by zone
    depenses_par_zone = {}
    for depense in depenses.select_related('projet__zone'):
        zone_name = depense.projet.zone.nom if depense.projet.zone else "Non assigné"
        depenses_par_zone[zone_name] = depenses_par_zone.get(zone_name, 0) + float(depense.montant)
    
    # Expenses by category
    depenses_par_categorie = {}
    for depense in depenses.select_related('poste_budgetaire'):
        cat_name = depense.poste_budgetaire.libelle if depense.poste_budgetaire else "Non catégorisé"
        depenses_par_categorie[cat_name] = depenses_par_categorie.get(cat_name, 0) + float(depense.montant)
    
    return {
        "campagne_id": str(campaign.id),
        "nom": campaign.nom,
        "budget_total": total_budget,
        "depenses_totales": total_depenses,
        "solde": solde,
        "taux_execution": taux,
        "date_cloture": campaign.date_fin.isoformat(),
        "jours_restants": (campaign.date_fin - timezone.now().date()).days,
        "depenses_par_zone": depenses_par_zone,
        "depenses_par_categorie": depenses_par_categorie,
    }


def call_ia_service(endpoint: str, payload: dict) -> dict:
    """Call the FastAPI IA service"""
    url = f"{settings.IA_SERVICE_URL}{endpoint}"
    try:
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"IA service call failed: {e}")
        raise


@shared_task
def run_ia_analyses():
    """Cron job: runs every 6 hours for each ACTIVE campaign"""
    active_campaigns = Campaign.objects.filter(statut=Campaign.Statut.EN_COURS)
    updated = 0
    
    for campaign in active_campaigns:
        try:
            # Compute payloads
            executive_payload = compute_executive_payload(campaign)
            finance_payload = compute_finance_payload(campaign)
            
            # Call IA service for all analyses
            combined_payload = {
                **executive_payload,
                **finance_payload,
            }
            
            response = requests.post(
                f"{settings.IA_SERVICE_URL}/api/ia/analyze-all",
                json=combined_payload,
                timeout=120
            )
            
            if response.status_code == 200:
                data = response.json()
                IAnalyse.objects.update_or_create(
                    campagne=campaign,
                    type_analyse='global',
                    defaults={'response_data': data}
                )
                updated += 1
                logger.info(f"IA analysis completed for campaign {campaign.id}")
            else:
                logger.error(f"IA service failed for campaign {campaign.id}: {response.text}")
                
        except Exception as e:
            logger.error(f"Error calling IA service for campaign {campaign.id}: {e}")
            
    logger.info(f"IA analyses complete. updated={updated}")
    return updated

@shared_task
def index_data_for_rag():
    """Extracts data from Django and sends it to FastAPI /api/ia/index to fill ChromaDB."""
    documents = []
    metadatas = []
    ids = []
    
    # 1. Index Campaigns
    campaigns = Campaign.objects.all()
    for camp in campaigns:
        budgets = Budget.objects.filter(projet=camp.projet)
        total_budget = sum(float(b.montant_total) for b in budgets)
        depenses = Depense.objects.filter(projet=camp.projet)
        total_depenses = sum(float(d.montant) for d in depenses)
        
        doc_text = f"Campagne: {camp.nom}\nDescription: {camp.description}\n"
        doc_text += f"Date début: {camp.date_debut} Date fin: {camp.date_fin}\n"
        doc_text += f"Budget total: {total_budget} FCFA. Dépenses totales: {total_depenses} FCFA.\n"
        
        documents.append(doc_text)
        metadatas.append({"type": "campaign", "id": str(camp.id), "nom": camp.nom})
        ids.append(f"campaign_{camp.id}")
        
    # 2. Index Zones
    zones = Zone.objects.all()
    for zone in zones:
        beneficiaires_count = Beneficiary.objects.filter(zone=zone).count()
        doc_text = f"Zone d'intervention: {zone.nom}\nRégion: {zone.region}\nDépartement: {zone.departement}\n"
        doc_text += f"Nombre de bénéficiaires: {beneficiaires_count}\n"
        if zone.description:
            doc_text += f"Détails: {zone.description}\n"
            
        documents.append(doc_text)
        metadatas.append({"type": "zone", "id": str(zone.id), "region": zone.region})
        ids.append(f"zone_{zone.id}")

    if not documents:
        return "No data to index"
        
    payload = {
        "documents": documents,
        "metadatas": metadatas,
        "ids": ids
    }
    
    try:
        url = f"{settings.IA_SERVICE_URL}/api/ia/index"
        response = requests.post(url, json=payload, timeout=60)
        response.raise_for_status()
        logger.info(f"RAG data indexed successfully: {response.json()}")
        return response.json()
    except Exception as e:
        logger.error(f"Failed to index RAG data: {e}")
        return str(e)