from django.urls import path
from .views import (
    SubscriptionStatusView,
    SubscriptionDetailView,
    InitiatePaymentView,
    PaymentWebhookView,
    TransactionHistoryView,
    SubscriptionCheckView,
    AdminSubscriptionListView,
    AdminSubscriptionDetailView,
    AdminSubscriptionSuspendView,
    AdminSubscriptionReactivateView,
)

urlpatterns = [
    # Gérant — état abonnement
    path("subscription/", SubscriptionStatusView.as_view(), name="subscription-status"),
    path("subscription/detail/", SubscriptionDetailView.as_view(), name="subscription-detail"),
    path("subscription/check/", SubscriptionCheckView.as_view(), name="subscription-check"),

    # Gérant — paiement
    path("subscribe/", InitiatePaymentView.as_view(), name="initiate-payment"),

    # Gérant — historique
    path("history/", TransactionHistoryView.as_view(), name="transaction-history"),

    # Webhook PayTech (public)
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),

    # Super Admin — gestion des abonnements
    path("admin/subscriptions/", AdminSubscriptionListView.as_view(), name="admin-subscription-list"),
    path("admin/subscriptions/<uuid:pk>/", AdminSubscriptionDetailView.as_view(), name="admin-subscription-detail"),
    path("admin/subscriptions/<uuid:pk>/suspend/", AdminSubscriptionSuspendView.as_view(), name="admin-subscription-suspend"),
    path("admin/subscriptions/<uuid:pk>/reactivate/", AdminSubscriptionReactivateView.as_view(), name="admin-subscription-reactivate"),
]
