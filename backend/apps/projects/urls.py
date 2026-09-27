from django.urls import path

from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectBudgetView,
    ProjectCriteriaListView,
    ProjectCriteriaDetailView,
)

app_name = "projects"

urlpatterns = [
    path("projects/", ProjectListCreateView.as_view(), name="project-list"),
    path("projects/<int:pk>/", ProjectDetailView.as_view(), name="project-detail"),
    path("projects/<int:pk>/budget/", ProjectBudgetView.as_view(), name="project-budget"),
    path("projets/<int:project_id>/criteres/", ProjectCriteriaListView.as_view(), name="project-criteria-list"),
    path("criteres/<int:pk>/", ProjectCriteriaDetailView.as_view(), name="criteria-detail"),
]
