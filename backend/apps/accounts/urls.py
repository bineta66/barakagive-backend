from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .jwt_views import JWTLoginView, LogoutView
from .views import (
    ActivateAccountView,
    AgentListView,
    UserListView,
    UserCreateView,
    UserDetailView,
    MeView,
    RegisterAuthView,
    ChangePasswordView,
    ResendActivationView,
    GerantListView,
)

app_name = "accounts"

urlpatterns = [
    path("register/", RegisterAuthView.as_view(), name="auth-register"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("resend-activation/", ResendActivationView.as_view(), name="resend-activation"),
    # Authentification
    path("login/", JWTLoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),

    # Activation du compte
    path("activate/", ActivateAccountView.as_view(), name="activate"),

    # Gestion des utilisateurs
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path("agents/", AgentListView.as_view(), name="agent-list"),
    path("gerants/", GerantListView.as_view(), name="gerant-list"),
    path("me/", MeView.as_view(), name="me"),
]