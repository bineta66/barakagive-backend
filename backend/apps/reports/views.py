from datetime import date
from io import BytesIO

from django.db.models import (
    Count, Sum, Avg, Q, F, ExpressionWrapper, DecimalField
)
from django.db.models.functions import TruncMonth
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.projects.models import Project
from apps.campaigns.models import Campaign
from apps.beneficiaries.models import Beneficiary
from apps.finance.models import Budget, Depense, Don
from apps.zones.models import Zone


ALLOWED_ROLES = {"GERANT", "CHEF_PROJET", "FINANCE"}


def _filter_projects(user):
    """Returns queryset of projects visible to the user."""
    org = user.organization
    if user.role == "CHEF_PROJET":
        return Project.objects.filter(chef_projet=user, organization=org, archived=False)
    if user.role == "FINANCE":
        return Project.objects.filter(responsable_finance=user, organization=org, archived=False)
    # GERANT — tous les projets de l'ONG
    return Project.objects.filter(organization=org, archived=False)


def _apply_common_filters(qs_model, user, params):
    """
    Applies project_id, campaign_id, region, and date_debut/date_fin
    to a queryset of the given model (must have 'created_at' or relevant date fields).
    Returns the filtered queryset.
    """
    return qs_model


def _parse_date(val):
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except ValueError:
        return None


# ─────────────────────────────────────────────
# Helper: build Beneficiary base queryset
# ─────────────────────────────────────────────
def _beneficiary_qs(user, params):
    org = user.organization
    qs = Beneficiary.objects.filter(organization=org)

    project_id = params.get("project_id")
    campaign_id = params.get("campaign_id")
    region = params.get("region")
    date_debut = _parse_date(params.get("date_debut"))
    date_fin = _parse_date(params.get("date_fin"))

    if project_id:
        qs = qs.filter(campagne__projet_id=project_id)
    if campaign_id:
        qs = qs.filter(campagne_id=campaign_id)
    if region:
        qs = qs.filter(zone__region=region)
    if date_debut:
        qs = qs.filter(created_at__date__gte=date_debut)
    if date_fin:
        qs = qs.filter(created_at__date__lte=date_fin)

    if user.role == "CHEF_PROJET":
        qs = qs.filter(campagne__projet__chef_projet=user)
    elif user.role == "FINANCE":
        qs = qs.filter(campagne__projet__responsable_finance=user)

    return qs


# ─────────────────────────────────────────────
# Helper: build Depense base queryset
# ─────────────────────────────────────────────
def _depense_qs(user, params):
    org = user.organization
    qs = Depense.objects.filter(organization=org)

    project_id = params.get("project_id")
    date_debut = _parse_date(params.get("date_debut"))
    date_fin = _parse_date(params.get("date_fin"))

    if project_id:
        qs = qs.filter(projet_id=project_id)
    if date_debut:
        qs = qs.filter(date_depense__gte=date_debut)
    if date_fin:
        qs = qs.filter(date_depense__lte=date_fin)

    if user.role == "CHEF_PROJET":
        qs = qs.filter(projet__chef_projet=user)
    elif user.role == "FINANCE":
        qs = qs.filter(projet__responsable_finance=user)

    return qs


# ─────────────────────────────────────────────────────────
# 1.  /api/reports/dashboard/  — Tableau de bord global
# ─────────────────────────────────────────────────────────
class ReportDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        params = request.query_params
        org = user.organization

        projects = _filter_projects(user)
        p_ids = list(projects.values_list("id", flat=True))

        # Campagnes
        campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org)
        c_ids = list(campaigns.values_list("id", flat=True))

        # Bénéficiaires
        beneficiaries = _beneficiary_qs(user, params)

        # Finances
        depenses = _depense_qs(user, params)
        budgets = Budget.objects.filter(projet_id__in=p_ids, organization=org)

        total_budget = budgets.aggregate(s=Sum("montant_total"))["s"] or 0
        total_depenses = depenses.aggregate(s=Sum("montant"))["s"] or 0

        # Taux d'exécution global
        taux_execution = round((float(total_depenses) / float(total_budget) * 100), 1) if total_budget else 0

        # Bénéf par genre
        genre_stats = beneficiaries.values("sexe").annotate(count=Count("id"))
        genre_map = {g["sexe"]: g["count"] for g in genre_stats}

        # Bénéf par mois (12 derniers mois)
        from django.utils import timezone
        twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
        ben_par_mois_qs = (
            beneficiaries.filter(created_at__gte=twelve_months_ago)
            .annotate(mois=TruncMonth("created_at"))
            .values("mois")
            .annotate(count=Count("id"))
            .order_by("mois")
        )
        ben_par_mois = [
            {"mois": item["mois"].strftime("%Y-%m"), "count": item["count"]}
            for item in ben_par_mois_qs
        ]

        # Score moyen de vulnérabilité
        score_moyen = beneficiaries.filter(
            score_vulnerabilite__isnull=False
        ).aggregate(avg=Avg("score_vulnerabilite"))["avg"]

        # Campagnes par statut
        campagnes_statuts = campaigns.values("statut").annotate(count=Count("id"))

        data = {
            "derniere_maj": timezone.now().isoformat(),
            "resume": {
                "total_projets": projects.count(),
                "total_campagnes": campaigns.count(),
                "total_beneficiaires": beneficiaries.count(),
                "budget_total": float(total_budget),
                "total_depenses": float(total_depenses),
                "taux_execution": taux_execution,
                "score_vulnerabilite_moyen": round(float(score_moyen), 2) if score_moyen else None,
            },
            "beneficiaires_par_genre": {
                "M": genre_map.get("M", 0),
                "F": genre_map.get("F", 0),
                "AUTRE": genre_map.get("AUTRE", 0),
            },
            "beneficiaires_par_mois": ben_par_mois,
            "campagnes_par_statut": [
                {"statut": s["statut"], "count": s["count"]}
                for s in campagnes_statuts
            ],
        }
        return Response(data)


# ─────────────────────────────────────────────────────────
# 2.  /api/reports/projets/  — Rapport Projets
# ─────────────────────────────────────────────────────────
class ReportProjetsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        params = request.query_params
        org = user.organization

        projects = _filter_projects(user)

        # Filtre région
        region = params.get("region")
        if region:
            projects = projects.filter(region=region)

        date_debut = _parse_date(params.get("date_debut"))
        date_fin = _parse_date(params.get("date_fin"))
        if date_debut:
            projects = projects.filter(start_date__gte=date_debut)
        if date_fin:
            projects = projects.filter(end_date__lte=date_fin)

        p_ids = list(projects.values_list("id", flat=True))

        # Stats par projet
        projets_data = []
        for project in projects.order_by("-start_date"):
            nb_campagnes = Campaign.objects.filter(projet=project, organization=org).count()
            nb_beneficiaires = Beneficiary.objects.filter(
                campagne__projet=project, organization=org
            ).count()
            budgets = Budget.objects.filter(projet=project, organization=org)
            total_budget = budgets.aggregate(s=Sum("montant_total"))["s"] or 0
            total_depenses = Depense.objects.filter(projet=project, organization=org).aggregate(
                s=Sum("montant")
            )["s"] or 0
            taux = round((float(total_depenses) / float(total_budget) * 100), 1) if total_budget else 0

            # Avancement (dates)
            today = date.today()
            duree_totale = (project.end_date - project.start_date).days or 1
            jours_ecoules = max(0, (today - project.start_date).days)
            avancement_temps = min(100, round(jours_ecoules / duree_totale * 100, 1))

            projets_data.append({
                "id": project.id,
                "code": project.code,
                "nom": project.name,
                "region": project.region,
                "start_date": project.start_date.isoformat(),
                "end_date": project.end_date.isoformat(),
                "nb_campagnes": nb_campagnes,
                "nb_beneficiaires": nb_beneficiaires,
                "budget_total": float(total_budget),
                "total_depenses": float(total_depenses),
                "taux_execution": taux,
                "avancement_temps": avancement_temps,
            })

        # Régions disponibles pour filtre
        all_regions = list(
            _filter_projects(user).values_list("region", flat=True).distinct()
        )

        return Response({
            "projets": projets_data,
            "regions": sorted(set(all_regions)),
        })


# ─────────────────────────────────────────────────────────
# 3.  /api/reports/campagnes/  — Rapport Campagnes
# ─────────────────────────────────────────────────────────
class ReportCampagnesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        params = request.query_params
        org = user.organization

        p_ids = list(_filter_projects(user).values_list("id", flat=True))
        campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org)

        # Filtres
        project_id = params.get("project_id")
        campaign_id = params.get("campaign_id")
        region = params.get("region")
        date_debut = _parse_date(params.get("date_debut"))
        date_fin = _parse_date(params.get("date_fin"))

        if project_id:
            campaigns = campaigns.filter(projet_id=project_id)
        if campaign_id:
            campaigns = campaigns.filter(id=campaign_id)
        if region:
            campaigns = campaigns.filter(projet__region=region)
        if date_debut:
            campaigns = campaigns.filter(date_debut__gte=date_debut)
        if date_fin:
            campaigns = campaigns.filter(date_fin__lte=date_fin)

        campagnes_data = []
        for c in campaigns.select_related("projet").order_by("-date_debut"):
            nb_ben = Beneficiary.objects.filter(campagne=c).count()
            nb_ben_f = Beneficiary.objects.filter(campagne=c, sexe="F").count()
            nb_ben_m = Beneficiary.objects.filter(campagne=c, sexe="M").count()
            nb_zones = c.zones.count()
            nb_agents = c.agents.count()

            # Score moyen
            score_avg = (
                Beneficiary.objects.filter(campagne=c, score_vulnerabilite__isnull=False)
                .aggregate(avg=Avg("score_vulnerabilite"))["avg"]
            )

            campagnes_data.append({
                "id": str(c.id),
                "code": c.code_campagne,
                "nom": c.nom,
                "projet_nom": c.projet.name,
                "projet_region": c.projet.region,
                "statut": c.statut,
                "date_debut": c.date_debut.isoformat(),
                "date_fin": c.date_fin.isoformat(),
                "nb_beneficiaires": nb_ben,
                "nb_femmes": nb_ben_f,
                "nb_hommes": nb_ben_m,
                "nb_zones": nb_zones,
                "nb_agents": nb_agents,
                "score_vulnerabilite_moyen": round(float(score_avg), 2) if score_avg else None,
            })

        return Response({"campagnes": campagnes_data})


# ─────────────────────────────────────────────────────────
# 4.  /api/reports/beneficiaires/  — Rapport Bénéficiaires
# ─────────────────────────────────────────────────────────
class ReportBeneficiairesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        params = request.query_params

        qs = _beneficiary_qs(user, params)

        total = qs.count()
        total_m = qs.filter(sexe="M").count()
        total_f = qs.filter(sexe="F").count()
        score_moyen = qs.filter(score_vulnerabilite__isnull=False).aggregate(
            avg=Avg("score_vulnerabilite")
        )["avg"]

        # Par zone
        par_zone = (
            qs.values("zone__nom", "zone__region")
            .annotate(count=Count("id"), score_moyen=Avg("score_vulnerabilite"))
            .order_by("-count")
        )

        # Distribution du score (tranches)
        tranches = [
            {"label": "0–25", "min": 0, "max": 25},
            {"label": "26–50", "min": 26, "max": 50},
            {"label": "51–75", "min": 51, "max": 75},
            {"label": "76–100", "min": 76, "max": 100},
        ]
        distribution = []
        for t in tranches:
            count = qs.filter(
                score_vulnerabilite__isnull=False,
                score_vulnerabilite__gte=t["min"],
                score_vulnerabilite__lte=t["max"],
            ).count()
            distribution.append({"label": t["label"], "count": count})

        # Par région
        par_region = (
            qs.values("zone__region")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Top 10 bénéficiaires les plus vulnérables
        top_vulnerables = list(
            qs.filter(score_vulnerabilite__isnull=False)
            .select_related("zone", "campagne", "campagne__projet")
            .order_by("-score_vulnerabilite")[:10]
            .values(
                "id", "nom", "prenom", "sexe",
                "score_vulnerabilite",
                "zone__nom", "zone__region",
                "campagne__nom",
            )
        )

        return Response({
            "resume": {
                "total": total,
                "total_hommes": total_m,
                "total_femmes": total_f,
                "score_moyen": round(float(score_moyen), 2) if score_moyen else None,
                "taux_feminisation": round(total_f / total * 100, 1) if total else 0,
            },
            "par_zone": [
                {
                    "zone": z["zone__nom"],
                    "region": z["zone__region"],
                    "count": z["count"],
                    "score_moyen": round(float(z["score_moyen"]), 2) if z["score_moyen"] else None,
                }
                for z in par_zone
            ],
            "par_region": [
                {"region": r["zone__region"] or "Non définie", "count": r["count"]}
                for r in par_region
            ],
            "distribution_score": distribution,
            "top_vulnerables": [
                {
                    "id": str(b["id"]),
                    "nom": f"{b['prenom']} {b['nom']}",
                    "sexe": b["sexe"],
                    "score": float(b["score_vulnerabilite"]),
                    "zone": b["zone__nom"],
                    "region": b["zone__region"],
                    "campagne": b["campagne__nom"],
                }
                for b in top_vulnerables
            ],
        })


# ─────────────────────────────────────────────────────────
# 5.  /api/reports/finance/  — Rapport Financier
# ─────────────────────────────────────────────────────────
class ReportFinanceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        params = request.query_params
        org = user.organization

        p_ids = list(_filter_projects(user).values_list("id", flat=True))

        depenses = _depense_qs(user, params)
        budgets = Budget.objects.filter(projet_id__in=p_ids, organization=org)
        dons = Don.objects.filter(organization=org, projet_id__in=p_ids)

        project_id = params.get("project_id")
        if project_id:
            dons = dons.filter(projet_id=project_id)
            budgets = budgets.filter(projet_id=project_id)

        total_budget = budgets.aggregate(s=Sum("montant_total"))["s"] or 0
        total_depenses = depenses.aggregate(s=Sum("montant"))["s"] or 0
        total_dons = dons.aggregate(s=Sum("montant"))["s"] or 0
        taux_exec = round(float(total_depenses) / float(total_budget) * 100, 1) if total_budget else 0

        # Dépenses par statut
        dep_statuts = (
            depenses.values("statut").annotate(
                count=Count("id"), montant_total=Sum("montant")
            )
        )

        # Dépenses par mois (12 derniers mois)
        from django.utils import timezone as tz
        twelve_months_ago = tz.now() - tz.timedelta(days=365)
        dep_par_mois = (
            depenses.filter(date_depense__gte=twelve_months_ago.date())
            .annotate(mois=TruncMonth("date_depense"))
            .values("mois")
            .annotate(montant=Sum("montant"))
            .order_by("mois")
        )

        # Top postes budgétaires dépensés
        top_postes = (
            depenses.values("poste_budgetaire__libelle")
            .annotate(total=Sum("montant"))
            .order_by("-total")[:10]
        )

        # Dépenses par projet
        dep_par_projet = (
            depenses.values("projet__name", "projet__code")
            .annotate(total=Sum("montant"))
            .order_by("-total")
        )

        return Response({
            "resume": {
                "budget_total": float(total_budget),
                "total_depenses": float(total_depenses),
                "montant_restant": float(total_budget) - float(total_depenses),
                "total_dons": float(total_dons),
                "taux_execution": taux_exec,
            },
            "depenses_par_statut": [
                {
                    "statut": s["statut"],
                    "count": s["count"],
                    "montant": float(s["montant_total"] or 0),
                }
                for s in dep_statuts
            ],
            "depenses_par_mois": [
                {
                    "mois": item["mois"].strftime("%Y-%m"),
                    "montant": float(item["montant"] or 0),
                }
                for item in dep_par_mois
            ],
            "top_postes": [
                {
                    "poste": p["poste_budgetaire__libelle"],
                    "total": float(p["total"] or 0),
                }
                for p in top_postes
            ],
            "depenses_par_projet": [
                {
                    "projet": p["projet__name"],
                    "code": p["projet__code"],
                    "total": float(p["total"] or 0),
                }
                for p in dep_par_projet
            ],
        })


# ─────────────────────────────────────────────────────────
# 6.  /api/reports/export/pdf/  — Export PDF
# ─────────────────────────────────────────────────────────
class ReportExportPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.units import cm
            from django.http import HttpResponse
        except ImportError:
            return Response(
                {"detail": "La bibliothèque reportlab n'est pas installée."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        user = request.user
        params = request.query_params
        org = user.organization

        # Collect data
        projects = _filter_projects(user)
        p_ids = list(projects.values_list("id", flat=True))
        campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org)
        beneficiaries = _beneficiary_qs(user, params)
        depenses = _depense_qs(user, params)
        budgets = Budget.objects.filter(projet_id__in=p_ids, organization=org)

        total_budget = budgets.aggregate(s=Sum("montant_total"))["s"] or 0
        total_depenses = depenses.aggregate(s=Sum("montant"))["s"] or 0
        taux = round(float(total_depenses) / float(total_budget) * 100, 1) if total_budget else 0

        # Build PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            rightMargin=2*cm, leftMargin=2*cm,
            topMargin=2*cm, bottomMargin=2*cm
        )
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "title",
            parent=styles["Title"],
            fontSize=20,
            textColor=colors.HexColor("#021427"),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "subtitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#744D03"),
            spaceAfter=12,
        )
        section_style = ParagraphStyle(
            "section",
            parent=styles["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#021427"),
            spaceBefore=16,
            spaceAfter=6,
        )
        normal = styles["Normal"]

        story = []

        # Title
        story.append(Paragraph("BarakaGive360 — Rapport d'activité", title_style))
        story.append(Paragraph(
            f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — Organisation : {org.nom if org else 'N/A'}",
            subtitle_style
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#021427")))
        story.append(Spacer(1, 0.4*cm))

        # Summary table
        story.append(Paragraph("Résumé global", section_style))
        summary_data = [
            ["Indicateur", "Valeur"],
            ["Projets actifs", str(projects.count())],
            ["Campagnes", str(campaigns.count())],
            ["Bénéficiaires enregistrés", str(beneficiaries.count())],
            ["Budget total alloué (FCFA)", f"{float(total_budget):,.0f}".replace(",", " ")],
            ["Total dépenses (FCFA)", f"{float(total_depenses):,.0f}".replace(",", " ")],
            ["Taux d'exécution", f"{taux} %"],
        ]
        t = Table(summary_data, colWidths=[10*cm, 7*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#021427")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

        # Projects table
        story.append(Paragraph("Projets", section_style))
        proj_rows = [["Code", "Nom", "Région", "Budget (FCFA)", "Bénéficiaires"]]
        for p in projects.order_by("-start_date")[:20]:
            nb_ben = Beneficiary.objects.filter(campagne__projet=p, organization=org).count()
            b_total = Budget.objects.filter(projet=p, organization=org).aggregate(s=Sum("montant_total"))["s"] or 0
            proj_rows.append([
                p.code, p.name[:30], p.region,
                f"{float(b_total):,.0f}".replace(",", " "),
                str(nb_ben),
            ])
        pt = Table(proj_rows, colWidths=[3.5*cm, 6*cm, 3*cm, 3.5*cm, 2*cm])
        pt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#021427")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f8fafc"), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(pt)

        doc.build(story)
        buffer.seek(0)

        filename = f"rapport_barakagive_{timezone.now().strftime('%Y%m%d_%H%M')}.pdf"
        response = HttpResponse(buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ─────────────────────────────────────────────────────────
# 7.  /api/reports/export/excel/  — Export Excel
# ─────────────────────────────────────────────────────────
class ReportExportExcelView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            from openpyxl.utils import get_column_letter
            from django.http import HttpResponse
        except ImportError:
            return Response(
                {"detail": "La bibliothèque openpyxl n'est pas installée."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        user = request.user
        params = request.query_params
        org = user.organization

        wb = openpyxl.Workbook()

        # Colors
        BLEU_NUIT = "FF021427"
        OR = "FF744D03"
        LIGHT_BLUE = "FFE8F0F7"
        WHITE = "FFFFFFFF"

        header_font = Font(color=WHITE, bold=True, size=10)
        header_fill = PatternFill(fill_type="solid", fgColor=BLEU_NUIT)
        alt_fill = PatternFill(fill_type="solid", fgColor=LIGHT_BLUE)
        center = Alignment(horizontal="center", vertical="center")
        left = Alignment(horizontal="left", vertical="center")

        thin = Side(style="thin", color="D1D5DB")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        def write_header(ws, headers, row=1):
            for col, h in enumerate(headers, 1):
                cell = ws.cell(row=row, column=col, value=h)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = center
                cell.border = border
            ws.row_dimensions[row].height = 20

        def write_row(ws, values, row, alt=False):
            for col, val in enumerate(values, 1):
                cell = ws.cell(row=row, column=col, value=val)
                if alt:
                    cell.fill = alt_fill
                cell.alignment = left
                cell.border = border

        # ── Sheet 1: Résumé ──────────────────────────────
        ws1 = wb.active
        ws1.title = "Résumé"
        ws1.column_dimensions["A"].width = 35
        ws1.column_dimensions["B"].width = 20

        projects = _filter_projects(user)
        p_ids = list(projects.values_list("id", flat=True))
        campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org)
        beneficiaries = _beneficiary_qs(user, params)
        depenses = _depense_qs(user, params)
        budgets = Budget.objects.filter(projet_id__in=p_ids, organization=org)

        total_budget = float(budgets.aggregate(s=Sum("montant_total"))["s"] or 0)
        total_depenses = float(depenses.aggregate(s=Sum("montant"))["s"] or 0)
        taux = round(total_depenses / total_budget * 100, 1) if total_budget else 0

        ws1.cell(row=1, column=1, value="BarakaGive360 — Rapport d'activité").font = Font(
            bold=True, size=14, color=BLEU_NUIT
        )
        ws1.cell(row=2, column=1, value=f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')}")

        write_header(ws1, ["Indicateur", "Valeur"], row=4)
        resume_rows = [
            ("Projets actifs", projects.count()),
            ("Campagnes", campaigns.count()),
            ("Bénéficiaires enregistrés", beneficiaries.count()),
            ("Budget total alloué (FCFA)", total_budget),
            ("Total dépenses (FCFA)", total_depenses),
            ("Montant restant (FCFA)", total_budget - total_depenses),
            ("Taux d'exécution (%)", taux),
        ]
        for i, (label, val) in enumerate(resume_rows, 5):
            write_row(ws1, [label, val], row=i, alt=(i % 2 == 0))

        # ── Sheet 2: Projets ─────────────────────────────
        ws2 = wb.create_sheet("Projets")
        headers2 = ["Code", "Nom", "Région", "Date début", "Date fin",
                    "Budget (FCFA)", "Dépenses (FCFA)", "Taux exec (%)", "Bénéficiaires"]
        write_header(ws2, headers2)
        for col in ["A", "B", "C", "D", "E", "F", "G", "H", "I"]:
            ws2.column_dimensions[col].width = 18

        for i, p in enumerate(projects.order_by("-start_date"), 2):
            nb_ben = Beneficiary.objects.filter(campagne__projet=p, organization=org).count()
            b_total = float(Budget.objects.filter(projet=p, organization=org).aggregate(s=Sum("montant_total"))["s"] or 0)
            d_total = float(Depense.objects.filter(projet=p, organization=org).aggregate(s=Sum("montant"))["s"] or 0)
            t = round(d_total / b_total * 100, 1) if b_total else 0
            write_row(ws2, [
                p.code, p.name, p.region,
                p.start_date.strftime("%d/%m/%Y"), p.end_date.strftime("%d/%m/%Y"),
                b_total, d_total, t, nb_ben,
            ], row=i, alt=(i % 2 == 0))

        # ── Sheet 3: Campagnes ───────────────────────────
        ws3 = wb.create_sheet("Campagnes")
        headers3 = ["Code", "Nom", "Projet", "Statut", "Date début", "Date fin",
                    "Bénéficiaires", "Femmes", "Hommes", "Zones", "Agents", "Score vulnérabilité moyen"]
        write_header(ws3, headers3)
        for idx, letter in enumerate("ABCDEFGHIJKL", 0):
            ws3.column_dimensions[letter].width = 18

        p_ids2 = list(_filter_projects(user).values_list("id", flat=True))
        camp_qs = Campaign.objects.filter(projet_id__in=p_ids2, organization=org).select_related("projet")
        for i, c in enumerate(camp_qs.order_by("-date_debut"), 2):
            nb = Beneficiary.objects.filter(campagne=c).count()
            nbf = Beneficiary.objects.filter(campagne=c, sexe="F").count()
            nbm = Beneficiary.objects.filter(campagne=c, sexe="M").count()
            sc = Beneficiary.objects.filter(campagne=c, score_vulnerabilite__isnull=False).aggregate(
                avg=Avg("score_vulnerabilite")
            )["avg"]
            write_row(ws3, [
                c.code_campagne, c.nom, c.projet.name, c.statut,
                c.date_debut.strftime("%d/%m/%Y"), c.date_fin.strftime("%d/%m/%Y"),
                nb, nbf, nbm, c.zones.count(), c.agents.count(),
                round(float(sc), 2) if sc else "",
            ], row=i, alt=(i % 2 == 0))

        # ── Sheet 4: Bénéficiaires ───────────────────────
        ws4 = wb.create_sheet("Bénéficiaires")
        headers4 = ["Prénom", "Nom", "Sexe", "Zone", "Région",
                    "Campagne", "Score vulnérabilité", "Statut sync"]
        write_header(ws4, headers4)
        for col in ["A", "B", "C", "D", "E", "F", "G", "H"]:
            ws4.column_dimensions[col].width = 20

        ben_qs = _beneficiary_qs(user, params).select_related("zone", "campagne").order_by("-score_vulnerabilite")
        for i, b in enumerate(ben_qs[:1000], 2):
            write_row(ws4, [
                b.prenom, b.nom, b.sexe, b.zone.nom, b.zone.region,
                b.campagne.nom,
                float(b.score_vulnerabilite) if b.score_vulnerabilite is not None else "",
                b.sync_status,
            ], row=i, alt=(i % 2 == 0))

        # ── Sheet 5: Finance ─────────────────────────────
        ws5 = wb.create_sheet("Finance")
        headers5 = ["Référence", "Projet", "Libellé", "Poste", "Montant (FCFA)", "Date", "Statut"]
        write_header(ws5, headers5)
        for col in ["A", "B", "C", "D", "E", "F", "G"]:
            ws5.column_dimensions[col].width = 20

        dep_qs = _depense_qs(user, params).select_related("projet", "poste_budgetaire").order_by("-date_depense")
        for i, d in enumerate(dep_qs[:1000], 2):
            write_row(ws5, [
                d.reference, d.projet.name, d.libelle,
                d.poste_budgetaire.libelle,
                float(d.montant), d.date_depense.strftime("%d/%m/%Y"), d.statut,
            ], row=i, alt=(i % 2 == 0))

        # Save
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        from django.http import HttpResponse
        filename = f"rapport_barakagive_{timezone.now().strftime('%Y%m%d_%H%M')}.xlsx"
        response = HttpResponse(
            buffer,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ─────────────────────────────────────────────────────────
# 8.  /api/reports/filters/  — Options de filtres
# ─────────────────────────────────────────────────────────
class ReportFiltersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ALLOWED_ROLES:
            return Response({"detail": "Accès refusé."}, status=status.HTTP_403_FORBIDDEN)

        user = request.user
        org = user.organization

        projects = _filter_projects(user)
        p_ids = list(projects.values_list("id", flat=True))

        campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org).values("id", "nom", "code_campagne")
        regions = list(projects.values_list("region", flat=True).distinct())

        return Response({
            "projets": [{"id": p.id, "nom": p.name, "code": p.code} for p in projects.order_by("name")],
            "campagnes": [{"id": str(c["id"]), "nom": c["nom"], "code": c["code_campagne"]} for c in campaigns],
            "regions": sorted(set(regions)),
        })
