from datetime import date

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.projects.models import Project
from .agent_views import AgentCampaignListView
from .views import CampaignAgentZonesView
from .models import Campaign, CampagneAffectation


class CampagneAffectationTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(
            name="ONG Test",
            email="ong-test@example.com",
            phone="+221770000",
            address="Dakar",
            region="Dakar",
            country="Sénégal",
            intervention_domain="Solidarité",
        )
        self.chef = User.objects.create_user(
            email="chef@example.com",
            password="password123",
            first_name="Chef",
            last_name="Projet",
            role=User.Role.CHEF_PROJET,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=self.organization,
        )
        self.agent = User.objects.create_user(
            email="agent@example.com",
            password="password123",
            first_name="Agent",
            last_name="Terrain",
            role=User.Role.AGENT,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=self.organization,
        )
        self.project = Project.objects.create(
            name="Projet test",
            description="Projet test",
            region="Dakar",
            objectif="Collecte",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            chef_projet=self.chef,
            responsable_finance=self.chef,
            organization=self.organization,
            created_by=self.chef,
        )
        self.assigned = Campaign.objects.create(
            projet=self.project,
            organization=self.organization,
            nom="Campagne assignée",
            code_campagne="CMP-TEST-001",
            description="Test",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            created_by=self.chef,
        )
        self.unassigned = Campaign.objects.create(
            projet=self.project,
            organization=self.organization,
            nom="Campagne non assignée",
            code_campagne="CMP-TEST-002",
            description="Test",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            created_by=self.chef,
        )
        CampagneAffectation.objects.create(
            campagne=self.assigned,
            agent=self.agent,
            zone="Dakar Nord",
            objectif_beneficiaires=20,
            created_by=self.chef,
        )

    def test_agent_ne_voit_que_ses_campagnes(self):
        request = APIRequestFactory().get("/api/agent/campagnes/")
        force_authenticate(request, user=self.agent)
        response = AgentCampaignListView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["nom"] for item in response.data], ["Campagne assignée"])

    def test_affectation_unique_par_campagne_et_agent(self):
        # Un doublon strict (campagne, agent, zone) doit etre refuse.
        with self.assertRaises(IntegrityError):
            CampagneAffectation.objects.create(
                campagne=self.assigned,
                agent=self.agent,
                zone="Dakar Nord",
                objectif_beneficiaires=10,
                created_by=self.chef,
            )


class AgentZonesMultiTests(TestCase):
    """Un agent peut intervenir dans plusieurs zones de la meme campagne."""

    def setUp(self):
        self.organization = Organization.objects.create(
            name="ONG Multi",
            email="ong-multi@example.com",
            phone="+221770000001",
            address="Kaolack",
            region="Kaolack",
            country="Sénégal",
            intervention_domain="Solidarité",
        )
        self.chef = User.objects.create_user(
            email="chef-multi@example.com",
            password="password123",
            first_name="Chef",
            last_name="Multi",
            role=User.Role.CHEF_PROJET,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=self.organization,
        )
        self.agent = User.objects.create_user(
            email="agent-multi@example.com",
            password="password123",
            first_name="Agent",
            last_name="Multi",
            role=User.Role.AGENT,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=self.organization,
        )
        self.project = Project.objects.create(
            name="Projet multi",
            description="Projet multi",
            region="Kaolack",
            objectif="Collecte",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            chef_projet=self.chef,
            responsable_finance=self.chef,
            organization=self.organization,
            created_by=self.chef,
        )
        self.campaign = Campaign.objects.create(
            projet=self.project,
            organization=self.organization,
            nom="Campagne multi",
            code_campagne="CMP-MULTI-001",
            description="Test",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            created_by=self.chef,
        )

    def test_agent_peut_avoir_plusieurs_zones(self):
        # Trois affectations (une par zone) autorisees pour le meme agent.
        for zone in ["Kaolack Centre", "Médina", "Ndorong"]:
            CampagneAffectation.objects.create(
                campagne=self.campaign,
                agent=self.agent,
                zone=zone,
                objectif_beneficiaires=10,
                created_by=self.chef,
            )

        zones = list(
            CampagneAffectation.objects
            .filter(campagne=self.campaign, agent=self.agent)
            .values_list("zone", flat=True)
        )
        self.assertEqual(len(zones), 3)
        self.assertIn("Kaolack Centre", zones)
        self.assertIn("Médina", zones)
        self.assertIn("Ndorong", zones)

    def test_get_affectations_groupees_par_agent(self):
        # Le GET retourne les zones regroupees par agent.
        for zone in ["Kaolack Centre", "Médina"]:
            CampagneAffectation.objects.create(
                campagne=self.campaign,
                agent=self.agent,
                zone=zone,
                objectif_beneficiaires=10,
                created_by=self.chef,
            )

        request = APIRequestFactory().get(
            f"/api/campaigns/{self.campaign.id}/agents/zones/"
        )
        force_authenticate(request, user=self.chef)
        response = CampaignAgentZonesView.as_view()(request, self.campaign.id)

        self.assertEqual(response.status_code, 200)
        affectations = response.data["affectations"]
        self.assertEqual(len(affectations), 1)
        self.assertEqual(affectations[0]["agent"]["id"], str(self.agent.id))
        self.assertCountEqual(affectations[0]["zones"], ["Kaolack Centre", "Médina"])
