import uuid
from datetime import date, timedelta
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import CustomUser
from apps.organizations.models import Organization
from apps.projects.models import Project
from apps.campaigns.models import Campaign
from apps.zones.models import Zone
from apps.beneficiaries.models import Beneficiary
from apps.finance.models import Don, Budget, Depense
from apps.ia.views import compute_assistant_dashboard


class AssistantDashboardTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.org = Organization.objects.create(
            name="ONG Solidarité Sénégal",
            email="contact@solidarite.sn",
            phone="+221771234567",
        )
        self.gerant = CustomUser.objects.create_user(
            username="gerant_test",
            email="gerant@solidarite.sn",
            password="Password123!",
            role="GERANT",
            organization=self.org,
            first_name="Amadou",
            last_name="Ba",
        )
        self.chef_projet = CustomUser.objects.create_user(
            username="cp_test",
            email="cp@solidarite.sn",
            password="Password123!",
            role="CHEF_PROJET",
            organization=self.org,
        )
        self.finance_user = CustomUser.objects.create_user(
            username="fin_test",
            email="fin@solidarite.sn",
            password="Password123!",
            role="FINANCE",
            organization=self.org,
        )

        # Create Project
        self.project = Project.objects.create(
            name="Programme Vivres & Santé",
            description="Assistance alimentaire et médicale",
            region="Kaolack",
            objectif="Secourir 500 familles",
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=60),
            budget=50000000.0,
            chef_projet=self.chef_projet,
            responsable_finance=self.finance_user,
            organization=self.org,
            created_by=self.gerant,
        )

        # Create Zone
        self.zone = Zone.objects.create(
            nom="Zone Kaolack Centre",
            region="Kaolack",
            departement="Kaolack",
            latitude=14.137,
            longitude=-16.073,
            location="SRID=4326;POINT(-16.073 14.137)",
            rayon=5000,
            organization=self.org,
            created_by=self.gerant,
        )

        # Create Campaign
        self.campaign = Campaign.objects.create(
            projet=self.project,
            organization=self.org,
            nom="Distribution Alimentaire Kaolack",
            description="Distribution mensuelle de kits",
            date_debut=timezone.now().date() - timedelta(days=10),
            date_fin=timezone.now().date() + timedelta(days=5),
            statut=Campaign.Statut.EN_COURS,
            created_by=self.chef_projet,
        )
        self.campaign.zones.add(self.zone)

        # Create Beneficiaries
        self.ben1 = Beneficiary.objects.create(
            campagne=self.campaign,
            zone=self.zone,
            organization=self.org,
            nom="Diop",
            prenom="Fatou",
            telephone="+221770001122",
            sexe="F",
            date_naissance=date(1985, 4, 12),
            latitude=14.138,
            longitude=-16.072,
            local_id=uuid.uuid4(),
            device_id="DEV-001",
            score_vulnerabilite=85.0,
            created_by=self.gerant,
        )
        self.ben2 = Beneficiary.objects.create(
            campagne=self.campaign,
            zone=self.zone,
            organization=self.org,
            nom="Fall",
            prenom="Mamadou",
            telephone="+221770001133",
            sexe="M",
            date_naissance=date(1978, 1, 25),
            latitude=14.139,
            longitude=-16.071,
            local_id=uuid.uuid4(),
            device_id="DEV-001",
            score_vulnerabilite=60.0,
            created_by=self.gerant,
        )

        # Create Finance: Bailleur, Don, Budget, Poste, Depense
        self.bailleur = Bailleur.objects.create(
            organization=self.org,
            nom="Fondation Espoir",
            created_by=self.gerant,
        )
        self.don = Don.objects.create(
            organization=self.org,
            bailleur=self.bailleur,
            projet=self.project,
            montant=50000000.0,
            date_reception=timezone.now().date() - timedelta(days=20),
        )
        self.budget = Budget.objects.create(
            organization=self.org,
            projet=self.project,
            don=self.don,
            montant_total=50000000.0,
            statut=Budget.Status.APPROUVE,
            created_by=self.finance_user,
        )
        self.depense = Depense.objects.create(
            organization=self.org,
            projet=self.project,
            categorie="Alimentation",
            montant=15000000.0,
            date=timezone.now().date() - timedelta(days=5),
            statut=Depense.Status.APPROUVE,
            created_by=self.finance_user,
        )

    def test_compute_assistant_dashboard(self):
        data = compute_assistant_dashboard(self.gerant)
        self.assertEqual(data["projets_actifs"], 1)
        self.assertEqual(data["campagnes_actives"], 1)
        self.assertEqual(data["beneficiaires"], 2)
        self.assertEqual(data["budget_total"], 50000000.0)
        self.assertEqual(data["depenses"], 15000000.0)
        self.assertEqual(data["solde"], 35000000.0)
        self.assertIn("Kaolack", data["resume"])
        self.assertIsInstance(data["alertes"], list)
        self.assertIsInstance(data["recommandations"], list)
        self.assertIn("generated_at", data)

    def test_api_endpoint_assistant_dashboard(self):
        self.client.force_authenticate(user=self.gerant)
        response = self.client.get("/api/assistant/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["projets_actifs"], 1)
        self.assertEqual(data["campagnes_actives"], 1)
        self.assertEqual(data["beneficiaires"], 2)
        self.assertEqual(data["budget_total"], 50000000.0)
        self.assertEqual(data["depenses"], 15000000.0)
        self.assertEqual(data["solde"], 35000000.0)

    def test_unauthenticated_access(self):
        response = self.client.get("/api/assistant/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
