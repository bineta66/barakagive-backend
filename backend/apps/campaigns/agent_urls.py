from django.urls import path

from .agent_views import (
    AgentCampaignBeneficiaryCreateView,
    AgentCampaignFormView,
    AgentCampaignListView,
    AgentDashboardView,
    AgentSynchronizationView,
)

urlpatterns = [
    path("campagnes/", AgentCampaignListView.as_view(), name="agent-campagnes"),
    path("dashboard/", AgentDashboardView.as_view(), name="agent-dashboard"),
    path("campagnes/<uuid:pk>/formulaire/", AgentCampaignFormView.as_view(), name="agent-campagne-formulaire"),
    path("campagnes/<uuid:pk>/beneficiaires/", AgentCampaignBeneficiaryCreateView.as_view(), name="agent-campagne-beneficiaires"),
    path("synchronisation/", AgentSynchronizationView.as_view(), name="agent-synchronisation"),
]
