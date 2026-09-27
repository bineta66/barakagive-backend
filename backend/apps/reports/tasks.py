import os
import io
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from apps.projects.models import Project
from apps.campaigns.models import Campaign
from apps.beneficiaries.models import Beneficiary
from apps.finance.models import Budget, Depense
from apps.organizations.models import Organization
from django.db.models import Sum, Count, Avg

def build_pdf_report(org: Organization, params: dict = None) -> bytes:
    """Generate a PDF report for a single organization.
    Mirrors the logic of `ReportExportPDFView` but works without an HTTP request.
    """
    if params is None:
        params = {}
    # Build querysets scoped to the organization
    projects = Project.objects.filter(organization=org, archived=False)
    p_ids = list(projects.values_list("id", flat=True))
    campaigns = Campaign.objects.filter(projet_id__in=p_ids, organization=org)
    beneficiaries = Beneficiary.objects.filter(organization=org)
    depenses = Depense.objects.filter(organization=org)
    budgets = Budget.objects.filter(projet_id__in=p_ids, organization=org)

    total_budget = budgets.aggregate(s=Sum("montant_total"))["s"] or 0
    total_depenses = depenses.aggregate(s=Sum("montant"))["s"] or 0
    taux = round(float(total_depenses) / float(total_budget) * 100, 1) if total_budget else 0

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
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

    story = []
    story.append(Paragraph("BarakaGive360 — Rapport d'activité", title_style))
    story.append(
        Paragraph(
            f"Généré le {timezone.now().strftime('%d/%m/%Y à %H:%M')} — Organisation : {getattr(org, 'nom', 'N/A')}",
            subtitle_style,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#021427")))
    story.append(Spacer(1, 0.4 * cm))

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
    t = Table(summary_data, colWidths=[10 * cm, 7 * cm])
    t.setStyle(
        TableStyle(
            [
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
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))

    # Projects table (first 20)
    story.append(Paragraph("Projets", section_style))
    proj_rows = [["Code", "Nom", "Région", "Budget (FCFA)", "Bénéficiaires"]]
    for p in projects.order_by("-start_date")[:20]:
        nb_ben = Beneficiary.objects.filter(campagne__projet=p, organization=org).count()
        b_total = Budget.objects.filter(projet=p, organization=org).aggregate(s=Sum("montant_total"))["s"] or 0
        proj_rows.append([
            p.code,
            p.name[:30],
            p.region,
            f"{float(b_total):,.0f}".replace(",", " "),
            str(nb_ben),
        ])
    pt = Table(proj_rows, colWidths=[3.5 * cm, 6 * cm, 3 * cm, 3.5 * cm, 2 * cm])
    pt.setStyle(
        TableStyle(
            [
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
            ]
        )
    )
    story.append(pt)

    doc.build(story)
    buffer.seek(0)
    return buffer.read()

# Celery task to generate reports for all organizations
from celery import shared_task

@shared_task
def generate_global_reports():
    """Generate PDF reports for every organization and store them under MEDIA_ROOT/reports/."""
    reports_dir = os.path.join(settings.MEDIA_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    for org in Organization.objects.all():
        pdf_bytes = build_pdf_report(org)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        filename = f"rapport_{org.id}_{timestamp}.pdf"
        file_path = os.path.join(reports_dir, filename)
        with open(file_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"Generated report for organization {org.id} -> {file_path}")
