import logging
import unicodedata
from django.db import models
from apps.campaigns.models import Campaign
from apps.zones.models import Zone
from apps.beneficiaries.models import Beneficiary
from apps.beneficiaries.services import _extraire_raisons

logger = logging.getLogger(__name__)


class VulnerabilityLevel:
    TRES_ELEVEE = "TRES_ELEVEE"
    ELEVEE = "ELEVEE"
    MOYENNE = "MOYENNE"
    FAIBLE = "FAIBLE"
    AUCUNE_DONNEE = "AUCUNE_DONNEE"

    @classmethod
    def from_score(cls, score: float) -> str:
        if score >= 80:
            return cls.TRES_ELEVEE
        elif score >= 60:
            return cls.ELEVEE
        elif score >= 40:
            return cls.MOYENNE
        elif score > 0:
            return cls.FAIBLE
        return cls.AUCUNE_DONNEE


def normalize_name(s: str) -> str:
    """Normalize string by removing accents, hyphens and lowercasing."""
    if not s:
        return ""
    nfkd = unicodedata.normalize('NFKD', s)
    no_accent = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return no_accent.replace("-", " ").replace("_", " ").lower().strip()


def compute_region_zones_data(campaign: Campaign, region_name: str) -> dict:
    """
    Compute zones data for a specific region within a campaign (or all regions if empty/all).

    Returns:
        dict with region, campaign, zones list containing:
        - name, score (0-100), beneficiaries count, level, top5 beneficiaries
    """
    # 1. Retrieve organization zones, optionally scoped to the campaign
    zones = Zone.objects.filter(
        organization=campaign.organization
    )
    if campaign.zones.exists():
        zones = zones.filter(campaigns=campaign)
    
    # 2. Filter by region if a specific region is requested
    is_all_regions = not region_name or region_name.lower().strip() in [
        "", "all", "toutes", "toutes les régions", "toutes les regions", "tous"
    ]
    
    if not is_all_regions:
        norm_target = normalize_name(region_name)
        matching_zone_ids = [
            z.id for z in zones if normalize_name(z.region) == norm_target
        ]
        zones = zones.filter(id__in=matching_zone_ids)
    
    zones_data = []
    total_beneficiaries = 0
    for zone in zones.order_by("nom"):
        zone_beneficiaries = Beneficiary.objects.filter(
            campagne=campaign,
            zone=zone,
        )

        beneficiaries_count = zone_beneficiaries.count()
        if beneficiaries_count == 0:
            # Fallback : bénéficiaires de cette zone, toutes campagnes confondues
            zone_beneficiaries = Beneficiary.objects.filter(zone=zone)
            beneficiaries_count = zone_beneficiaries.count()

        total_beneficiaries += beneficiaries_count
        scored = zone_beneficiaries.exclude(score_vulnerabilite__isnull=True)

        if beneficiaries_count > 0:
            avg_score = scored.aggregate(
                avg_score=models.Avg("score_vulnerabilite")
            )["avg_score"] or 0
            score = float(avg_score)
        else:
            score = 0.0
        level = VulnerabilityLevel.from_score(score)

        # Get top 5 beneficiaries with reasons
        top5 = []
        for b in scored.order_by("-score_vulnerabilite")[:5]:
            try:
                raisons = _extraire_raisons(b)
            except Exception:
                raisons = []
            top5.append({
                "id": str(b.id),
                "nom": f"{b.prenom} {b.nom}".strip() or "Bénéficiaire",
                "score": int(float(b.score_vulnerabilite or 0)),
                "vulnerabilite": VulnerabilityLevel.from_score(float(b.score_vulnerabilite or 0)),
                "raisons": raisons,
            })
        
        zones_data.append({
            "id": str(zone.id),
            "zone_id": str(zone.id),
            "nom": zone.nom,
            "name": zone.nom,
            "region": zone.region,
            "departement": zone.departement or zone.nom,
            "score": round(score, 1),
            "score_total": round(score, 1),
            "beneficiaries": beneficiaries_count,
            "beneficiaires": beneficiaries_count,
            "beneficiairesCount": beneficiaries_count,
            "level": level,
            "niveau_urgence": level,
            "top5": top5,
            "top5_beneficiaires": top5,
        })
    
    # Sort zones by score descending, then by beneficiaries count
    zones_data.sort(key=lambda z: (z["score"], z["beneficiaries"]), reverse=True)
    
    display_region = "Toutes les régions" if is_all_regions else region_name
    
    return {
        "region": display_region,
        "campaign": campaign.nom,
        "total_beneficiaries": total_beneficiaries,
        "zones_count": len(zones_data),
        "zones": zones_data,
    }


def compute_all_regions_zones_data(campaign: Campaign) -> dict:
    """
    Compute zones data for all regions in a campaign.
    Used for executive insight and bulk analysis.
    """
    regions = Zone.objects.filter(
        campaigns=campaign,
        organization=campaign.organization
    ).values_list("region", flat=True).distinct()
    
    all_regions_data = []
    total_beneficiaries = 0
    
    for region in regions:
        region_data = compute_region_zones_data(campaign, region)
        all_regions_data.append(region_data)
        total_beneficiaries += region_data["total_beneficiaries"]
    
    all_regions_data.sort(key=lambda r: max((z["score"] for z in r["zones"]), default=0), reverse=True)
    
    return {
        "campaign_id": str(campaign.id),
        "campaign": campaign.nom,
        "total_beneficiaries": total_beneficiaries,
        "regions": all_regions_data,
    }


def get_zone_beneficiaries_detail(campaign: Campaign, zone_id: str) -> dict:
    """
    Get detailed beneficiaries data for a specific zone.
    """
    zone = Zone.objects.get(id=zone_id, campaigns=campaign)
    
    beneficiaries = Beneficiary.objects.filter(
        campagne=campaign,
        zone=zone
    ).exclude(score_vulnerabilite__isnull=True).order_by("-score_vulnerabilite")
    
    top5 = []
    for b in beneficiaries[:5]:
        top5.append({
            "nom": b.nom,
            "prenom": b.prenom,
            "score": float(b.score_vulnerabilite),
            "vulnerabilite": VulnerabilityLevel.from_score(float(b.score_vulnerabilite)),
        })
    
    return {
        "zone_id": str(zone.id),
        "zone_name": zone.nom,
        "region": zone.region,
        "departement": zone.departement,
        "beneficiaries_count": beneficiaries.count(),
        "top5_beneficiaries": top5,
    }