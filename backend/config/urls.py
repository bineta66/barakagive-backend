from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

def health_check(request):
    return JsonResponse({"status": "ok", "service": "barakagive-backend"})

urlpatterns = [
    path("admin/", admin.site.urls),

    path("api/accounts/", include("apps.accounts.urls")),
    path("api/auth/", include(("apps.accounts.urls", "auth"), namespace="auth")),
    path("api/token/", __import__("apps.accounts.jwt_views", fromlist=["JWTLoginView"]).JWTLoginView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", __import__("rest_framework_simplejwt.views", fromlist=["TokenRefreshView"]).TokenRefreshView.as_view(), name="token_refresh"),
    path("api/organizations/", include("apps.organizations.urls")),
    path("api/agent/", include("apps.campaigns.agent_urls")),
    path("api/campaigns/", include("apps.campaigns.urls")),
    path("api/", include("apps.projects.urls")),
    path("api/", include("apps.zones.urls")),
    path("api/regions/", __import__("apps.zones.views", fromlist=["RegionListView"]).RegionListView.as_view(), name="region-list"),
    path("api/forms/", include("apps.forms.urls")),
    path("api/beneficiaries/", include("apps.beneficiaries.urls")),
    path("api/finance/", include("apps.finance.urls")),
    path("api/ia/", include("apps.ia.urls")),
    path("api/assistant/dashboard/", __import__("apps.ia.views", fromlist=["AssistantDashboardView"]).AssistantDashboardView.as_view(), name="assistant-dashboard"),
    path("api/assistant/chat/", __import__("apps.ia.views", fromlist=["AssistantChatView"]).AssistantChatView.as_view(), name="assistant-chat"),
    path("api/payment/", include("apps.payment.urls")),
    path("api/reports/", include("apps.reports.urls")),
    # Carte des Priorités — endpoints régions
    path("api/projets/<int:project_id>/regions/",
         __import__("apps.beneficiaries.views", fromlist=["ProjectRegionsView"]).ProjectRegionsView.as_view(),
         name="project-regions"),
    path("api/projets/<int:project_id>/regions/<str:region_name>/priorites/",
         __import__("apps.beneficiaries.views", fromlist=["RegionPrioritiesView"]).RegionPrioritiesView.as_view(),
         name="region-priorities"),
    path("api/zones/<uuid:zone_id>/beneficiaires/",
         __import__("apps.beneficiaries.views", fromlist=["ZoneBeneficiariesTableView"]).ZoneBeneficiariesTableView.as_view(),
         name="zone-beneficiaires-table"),

    # Health check endpoint for PWA connectivity
    path("api/health/", health_check, name="health-check"),

    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)