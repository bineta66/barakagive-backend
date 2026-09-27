from django.urls import path

from .views import (
    FormulaireListCreateView,
    FormulaireDetailView,
    FormulairePublishView,
    QuestionListCreateView,
    QuestionDetailView,
    QuestionDuplicateView,
    QuestionReorderView,
)

urlpatterns = [
    # Formulaires
    path("", FormulaireListCreateView.as_view(), name="formulaire-list-create"),
    path("<uuid:pk>/", FormulaireDetailView.as_view(), name="formulaire-detail"),
    path("<uuid:pk>/publish/", FormulairePublishView.as_view(), name="formulaire-publish"),

    # Questions
    path("<uuid:form_id>/questions/", QuestionListCreateView.as_view(), name="question-list-create"),
    path("questions/<uuid:pk>/", QuestionDetailView.as_view(), name="question-detail"),
    path("questions/<uuid:pk>/duplicate/", QuestionDuplicateView.as_view(), name="question-duplicate"),
    path("questions/reorder/", QuestionReorderView.as_view(), name="question-reorder"),
]