from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from .models import Project, ProjectCriteria
from .serializers import (
    ProjectSerializer,
    ProjectCreateSerializer,
    BudgetUpdateSerializer,
    ProjectCriteriaSerializer,
    ProjectCriteriaCreateSerializer,
)
from .permissions import (
    IsGerantOrFinanceOrAgent,
    CanManageProject,
)


@extend_schema(tags=["Projets"])
class ProjectListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsGerantOrFinanceOrAgent, CanManageProject]

    def get_queryset(self):
        queryset = Project.objects.select_related(
            "chef_projet", "responsable_finance", "organization", "created_by"
        ).prefetch_related("criteres").all()
        user = self.request.user
        if user.role == "CHEF_PROJET":
            return queryset.filter(organization=user.organization, chef_projet=user)
        if user.role == "FINANCE":
            return queryset.filter(organization=user.organization, responsable_finance=user)
        return queryset.filter(organization=user.organization)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCreateSerializer
        return ProjectSerializer

    def perform_create(self, serializer):
        serializer.save()


@extend_schema(tags=["Projets"])
class ProjectDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsGerantOrFinanceOrAgent, CanManageProject]
    queryset = Project.objects.select_related(
        "chef_projet", "responsable_finance", "organization", "created_by"
    ).prefetch_related("criteres").all()

    def get_queryset(self):
        queryset = self.queryset.filter(organization=self.request.user.organization)
        if self.request.user.role == "CHEF_PROJET":
            queryset = queryset.filter(chef_projet=self.request.user)
        elif self.request.user.role == "FINANCE":
            queryset = queryset.filter(responsable_finance=self.request.user)
        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.archived = True
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Projets"])
class ProjectBudgetView(generics.UpdateAPIView):
    serializer_class = BudgetUpdateSerializer
    permission_classes = [IsGerantOrFinanceOrAgent, CanManageProject]
    queryset = Project.objects.all()

    def get_object(self):
        obj = super().get_object()
        if self.request.user.role not in ["GERANT", "FINANCE"]:
            self.permission_denied(self.request)
        return obj

    def update(self, request, *args, **kwargs):
        project = self.get_object()
        serializer = self.get_serializer(project, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProjectSerializer(project).data)


@extend_schema(tags=["Critères Projet"])
class ProjectCriteriaListView(generics.ListCreateAPIView):
    serializer_class = ProjectCriteriaSerializer
    permission_classes = [IsGerantOrFinanceOrAgent]
    queryset = ProjectCriteria.objects.select_related("created_by", "projet").all()

    def get_queryset(self):
        projet_id = self.kwargs.get("project_id")
        return self.queryset.filter(projet_id=projet_id, actif=True)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProjectCriteriaCreateSerializer
        return ProjectCriteriaSerializer

    def list(self, request, *args, **kwargs):
        projet_id = kwargs.get("project_id")
        projet = Project.objects.filter(pk=projet_id).first()
        if not projet:
            return Response({"detail": "Projet introuvable."}, status=status.HTTP_404_NOT_FOUND)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        total_poids = sum(c.poids for c in queryset)
        return Response({
            "total_poids": total_poids,
            "criteres": serializer.data,
        })

    def create(self, request, *args, **kwargs):
        projet_id = kwargs.get("project_id")
        projet = Project.objects.filter(pk=projet_id).first()
        if not projet:
            return Response({"detail": "Projet introuvable."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(data=request.data, context={"projet": projet, "request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Critères Projet"])
class ProjectCriteriaDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectCriteriaSerializer
    permission_classes = [IsGerantOrFinanceOrAgent]
    queryset = ProjectCriteria.objects.select_related("created_by", "projet").all()

    def get_queryset(self):
        return self.queryset.filter(actif=True)

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return ProjectCriteriaCreateSerializer
        return ProjectCriteriaSerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.actif = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)
