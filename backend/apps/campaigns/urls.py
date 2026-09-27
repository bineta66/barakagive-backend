from django.urls import path

from .views import (
    CampaignAgentZonesView,
    CampaignListCreateView,
    CampaignDetailView,
)

urlpatterns = [
    path("", CampaignListCreateView.as_view(), name="campaign-list-create"),
    path("<uuid:pk>/", CampaignDetailView.as_view(), name="campaign-detail"),
    path("<uuid:pk>/agents/zones/", CampaignAgentZonesView.as_view(), name="campaign-agent-zones"),
]