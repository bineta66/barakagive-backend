from django.urls import path
from .views import (
    AssistantDashboardView,
    AssistantChatView,
    ExecutiveInsightView,
    RegionZonesView,
    ZoneDetailView,
    BudgetAnalysisView,
    RegionAnalysisView,
    RegionAnalysisIAView,
)

urlpatterns = [
    path('dashboard/', AssistantDashboardView.as_view(), name='assistant_dashboard'),
    path('chat/', AssistantChatView.as_view(), name='assistant_chat'),
    path('executive-insight', ExecutiveInsightView.as_view(), name='executive_insight'),
    path('regions/<str:id>/zones', RegionZonesView.as_view(), name='region_zones'),
    path('regions/<str:region_name>/analysis', RegionAnalysisView.as_view(), name='region_analysis'),
    path('regions/<str:region_name>/analyze-ia', RegionAnalysisIAView.as_view(), name='region_analysis_ia'),
    path('regions/<str:region_name>/analyze', RegionAnalysisIAView.as_view(), name='region_analyze_direct'),
    path('zones/<str:id>', ZoneDetailView.as_view(), name='zone_detail'),
    path('budget-analysis/<str:campagne_id>', BudgetAnalysisView.as_view(), name='budget_analysis'),
]