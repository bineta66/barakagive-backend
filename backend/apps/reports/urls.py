from django.urls import path
from .views import (
    ReportDashboardView,
    ReportProjetsView,
    ReportCampagnesView,
    ReportBeneficiairesView,
    ReportFinanceView,
    ReportExportPDFView,
    ReportExportExcelView,
    ReportFiltersView,
)

urlpatterns = [
    path("dashboard/", ReportDashboardView.as_view(), name="report-dashboard"),
    path("projets/", ReportProjetsView.as_view(), name="report-projets"),
    path("campagnes/", ReportCampagnesView.as_view(), name="report-campagnes"),
    path("beneficiaires/", ReportBeneficiairesView.as_view(), name="report-beneficiaires"),
    path("finance/", ReportFinanceView.as_view(), name="report-finance"),
    path("export/pdf/", ReportExportPDFView.as_view(), name="report-export-pdf"),
    path("export/excel/", ReportExportExcelView.as_view(), name="report-export-excel"),
    path("filters/", ReportFiltersView.as_view(), name="report-filters"),
]
