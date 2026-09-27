from datetime import date
from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.projects.models import Project
from apps.zones.models import Zone
from .views import ProjectRegionsView, RegionPrioritiesView

class CartePrioritesTests(TestCase):
    """Tests des endpoints de la Carte des Priorites."""

    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(
            name="ONG Baraka",
            email="baraka-test@example.com",
            phone="+221770000",
            address="Dakar",
            region="Dakar",
            country="Senegal",
            intervention_domain="Solidarite",
        )
        cls.chef = User.objects.create_user(
            email="chef-carte@example.com",
            password="password123",
            first_name="Chef",
            last_name="Carte",
            role=User.Role.CHEF_PROJET,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=cls.organization,
        )
        cls.project = Project.objects.create(
            name="Projet Carte",
            description="Projet de test de la carte",
            region="Dakar",
            objectif="Collecte",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            chef_projet=cls.chef,
            responsable_finance=cls.chef,
            organization=cls.organization,
            created_by=cls.chef,
        )

    def _get(self, view_cls, url, *args):
        request = APIRequestFactory().get(url)
        force_authenticate(request, user=self.chef)
        return view_cls.as_view()(request, *args)

    def test_regions_retourne_200_meme_sans_beneficiaire(self):
        """Projet sans aucun beneficiaire : 200 + liste vide, jamais 500."""
        response = self._get(
            ProjectRegionsView,
            f"/api/projets/{self.project.pk}/regions/",
            self.project.pk,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_regions_projet_inexistant_renvoie_404(self):
        response = self._get(
            ProjectRegionsView,
            "/api/projets/999/regions/",
            999,
        )
        self.assertEqual(response.status_code, 404)

    def test_priorites_region_sans_beneficiaire_renvoie_200(self):
        """La region existe (declared sur le projet) mais n'a aucun beneficiaire."""
        response = self._get(
            RegionPrioritiesView,
            f"/api/projets/{self.project.pk}/regions/Dakar/priorites/",
            self.project.pk,
            "Dakar",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total_beneficiaires"], 0)
        self.assertEqual(response.data["score_region"], 0)
        self.assertEqual(response.data["zones"], [])

    def test_priorites_region_inconnue_renvoie_404(self):
        response = self._get(
            RegionPrioritiesView,
            f"/api/projets/{self.project.pk}/regions/RegionInexistante/priorites/",
            self.project.pk,
            "RegionInexistante",
        )
        self.assertEqual(response.status_code, 404)

    def test_priorites_projet_inexistant_renvoie_404(self):
        response = self._get(
            RegionPrioritiesView,
            "/api/projets/999/regions/Dakar/priorites/",
            999,
            "Dakar",
        )
        self.assertEqual(response.status_code, 404)

    def _make_zone(self, nom, region="Dakar"):
        return Zone.objects.create(
            nom=nom,
            region=region,
            departement="Dakar",
            latitude=14.6928,
            longitude=-17.4467,
            location=Point(-17.4467, 14.6928, srid=4326),
            rayon=1000,
            organization=self.organization,
            created_by=self.chef,
        )

    def test_priorites_retourne_toutes_les_zones_meme_sans_beneficiaire(self):
        # Toutes les zones de la region doivent apparaitre, meme a 0 beneficiaire.
        self._make_zone("Zone Vide A")
        self._make_zone("Zone Vide B")

        response = self._get(
            RegionPrioritiesView,
            f"/api/projets/{self.project.pk}/regions/Dakar/priorites/",
            self.project.pk,
            "Dakar",
        )
        self.assertEqual(response.status_code, 200)

        zones = response.data["zones"]
        noms = {z["nom"] for z in zones}
        self.assertIn("Zone Vide A", noms)
        self.assertIn("Zone Vide B", noms)
        for zone in zones:
            if zone["nom"].startswith("Zone Vide"):
                self.assertEqual(zone["score"], 0)
                self.assertEqual(zone["total_beneficiaires"], 0)
                self.assertEqual(zone["beneficiaires"], [])


class VulnerabilityScoreCalculationTests(TestCase):
    """
    Tests de vérification du calcul du score de vulnérabilité :
    - 1 critère coché (10 pts) -> score = 10
    - 3 critères cochés (60 pts) -> score = 60
    - Tous les critères cochés (100 pts) -> score = 100
    """

    @classmethod
    def setUpTestData(cls):
        from apps.projects.models import ProjectCriteria
        from apps.campaigns.models import Campaign
        from apps.forms.models import Formulaire, FormField
        from apps.beneficiaries.models import Beneficiary, FormResponse
        import uuid

        cls.org = Organization.objects.create(
            name="ONG Test",
            email="ong@test.com",
            phone="+221770001",
            address="Dakar",
            region="Dakar",
            country="Senegal",
            intervention_domain="Humanitaire",
        )
        cls.chef = User.objects.create_user(
            email="chef-test@example.com",
            password="password123",
            first_name="Chef",
            last_name="Test",
            role=User.Role.CHEF_PROJET,
            status=User.Status.ACTIVE,
            is_active=True,
            organization=cls.org,
        )
        cls.zone = Zone.objects.create(
            nom="Zone Test",
            region="Dakar",
            departement="Dakar",
            latitude=14.6928,
            longitude=-17.4467,
            location=Point(-17.4467, 14.6928, srid=4326),
            rayon=1000,
            organization=cls.org,
            created_by=cls.chef,
        )
        cls.project = Project.objects.create(
            name="Projet Score Test",
            description="Test calcul scores",
            region="Dakar",
            objectif="Secours",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            chef_projet=cls.chef,
            responsable_finance=cls.chef,
            organization=cls.org,
            created_by=cls.chef,
        )
        cls.campaign = Campaign.objects.create(
            projet=cls.project,
            organization=cls.org,
            nom="Campagne Test",
            description="Campagne",
            date_debut=date(2026, 1, 1),
            date_fin=date(2026, 12, 31),
            statut=Campaign.Statut.EN_COURS,
        )
        cls.campaign.zones.add(cls.zone)

        cls.formulaire = Formulaire.objects.create(
            campagne=cls.campaign,
            organization=cls.org,
            nom="Formulaire Test",
            statut=Formulaire.Statut.PUBLIE,
            created_by=cls.chef,
        )

        # 5 critères avec poids total = 100 : 30, 25, 20, 15, 10
        criteres_def = [
            ("Sans soutien familial", 30),
            ("Manque de nourriture", 25),
            ("Santé fragile", 20),
            ("Difficulté scolaire", 15),
            ("Besoins spécifiques", 10),
        ]
        cls.fields = []
        cls.criteres = []
        for nom, poids in criteres_def:
            field = FormField.objects.create(
                formulaire=cls.formulaire,
                label=nom,
                type=FormField.TypeChoices.YES_NO,
            )
            critere = ProjectCriteria.objects.create(
                projet=cls.project,
                nom=nom,
                poids=poids,
                question=field,
                created_by=cls.chef,
            )
            cls.fields.append(field)
            cls.criteres.append(critere)

    def _creer_beneficiaire_avec_reponses(self, reponses_bool_list):
        import uuid
        from apps.beneficiaries.models import Beneficiary, FormResponse
        from apps.beneficiaries.services import update_vulnerability_score

        b = Beneficiary.objects.create(
            campagne=self.campaign,
            zone=self.zone,
            organization=self.org,
            nom=f"Nom_{uuid.uuid4().hex[:6]}",
            prenom="Prenom",
            telephone=f"+22177{uuid.uuid4().int % 10000000:07d}",
            sexe=Beneficiary.Sexe.M,
            date_naissance=date(1990, 1, 1),
            latitude=14.69,
            longitude=-17.44,
            local_id=uuid.uuid4(),
            device_id="DEV-TEST",
            created_by=self.chef,
        )
        for field, is_oui in zip(self.fields, reponses_bool_list):
            FormResponse.objects.create(
                beneficiary=b,
                formulaire=self.formulaire,
                question=field,
                value_boolean=is_oui,
                value_text="Oui" if is_oui else "Non",
            )
        return update_vulnerability_score(b)

    def test_un_seul_critere_coche_donne_10(self):
        """Cas 1 : Uniquement le critère 'Besoins spécifiques' (10 pts) coché Oui -> Score = 10"""
        reponses = [False, False, False, False, True]
        beneficiary = self._creer_beneficiaire_avec_reponses(reponses)
        self.assertEqual(int(beneficiary.score_vulnerabilite), 10)

    def test_trois_criteres_coches_donne_60(self):
        """Cas 2 : 3 critères cochés : 30 + 20 + 10 = 60 pts -> Score = 60"""
        reponses = [True, False, True, False, True]
        beneficiary = self._creer_beneficiaire_avec_reponses(reponses)
        self.assertEqual(int(beneficiary.score_vulnerabilite), 60)

    def test_tous_les_criteres_coches_donne_100(self):
        """Cas 3 : Tous les critères cochés Oui -> Score = 100"""
        reponses = [True, True, True, True, True]
        beneficiary = self._creer_beneficiaire_avec_reponses(reponses)
        self.assertEqual(int(beneficiary.score_vulnerabilite), 100)

