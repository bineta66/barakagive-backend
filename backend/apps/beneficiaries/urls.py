from django.urls import path

from .views import (
    BeneficiaryListCreateView,
    BeneficiaryDetailView,
    BeneficiarySyncView,
    BeneficiaryAIScoreView,
    ZoneRankingView,
    ProjectRegionsView,
    RegionPrioritiesView,
    ZoneBeneficiariesTableView,
)

urlpatterns = [
    path("", BeneficiaryListCreateView.as_view(), name="beneficiary-list-create"),
    path("sync/", BeneficiarySyncView.as_view(), name="beneficiary-sync"),
    path("zone/<uuid:zone_id>/", ZoneBeneficiariesTableView.as_view(), name="beneficiary-zone-table"),
    path("<uuid:pk>/", BeneficiaryDetailView.as_view(), name="beneficiary-detail"),
    path("<uuid:pk>/ai-score/", BeneficiaryAIScoreView.as_view(), name="beneficiary-ai-score"),
    path("zone-ranking/", ZoneRankingView.as_view(), name="beneficiary-zone-ranking"),
]

