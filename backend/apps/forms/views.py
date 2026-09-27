from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import extend_schema

from apps.campaigns.models import Campaign
from .models import Formulaire, FormField
from .serializers import (
    FormulaireListSerializer,
    FormulaireDetailSerializer,
    FormulaireCreateSerializer,
    FormulaireUpdateSerializer,
    FormFieldSerializer,
    FormFieldCreateSerializer,
    FormFieldUpdateSerializer,
    ReorderQuestionsSerializer,
    DuplicateQuestionSerializer,
)
from .permissions import (
    IsChefProjetOrGerantOrAgent,
    IsChefProjetOnly,
    CanManageFormulaire,
    CanViewFormulaire,
    CanManageQuestion,
    CanManageQuestionObject,
)
from .services import (
    create_formulaire,
    update_formulaire,
    publish_formulaire,
    add_question,
    update_question,
    duplicate_question,
    delete_question,
    reorder_questions,
    get_published_formulaires_for_agent,
    FormulaireError,
)


@extend_schema(tags=["Formulaires"])
class FormulaireListCreateView(APIView):
    """
    GET /api/forms/ - Liste des formulaires
    POST /api/forms/ - Création d'un formulaire avec ses questions (CHEF_PROJET)
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsChefProjetOnly()]
        return [IsAuthenticated(), IsChefProjetOrGerantOrAgent()]

    @extend_schema(
        responses={200: FormulaireListSerializer(many=True)},
    )
    def get(self, request):
        """
        Liste les formulaires selon le rôle :
        - CHEF_PROJET/GERANT : tous les formulaires de leur ONG
        - AGENT : seulement les formulaires PUBLIES de leur ONG
        """
        if request.user.role == "AGENT":
            formulaires = get_published_formulaires_for_agent(request.user)
        else:
            formulaires = Formulaire.objects.filter(
                organization=request.user.organization
            ).select_related(
                "campagne", "campagne__projet", "created_by"
            ).prefetch_related("fields").order_by("-created_at")

        serializer = FormulaireListSerializer(formulaires, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=FormulaireCreateSerializer,
        responses={201: FormulaireDetailSerializer},
    )
    def post(self, request):
        """
        Crée un formulaire avec ses questions.

        Vérifications :
        1. JWT valide
        2. Rôle = CHEF_PROJET
        3. Campagne existe
        4. Campagne appartient à la même ONG
        5. Chef de projet autorisé sur le projet de la campagne
        """
        serializer = FormulaireCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            formulaire = create_formulaire(serializer.validated_data, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        detail_serializer = FormulaireDetailSerializer(formulaire)
        return Response(
            {
                "id": formulaire.id,
                "nom": formulaire.nom,
                "version": formulaire.version,
                "statut": formulaire.statut,
                "message": "Formulaire créé avec succès.",
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Formulaires"])
class FormulaireDetailView(APIView):
    """
    GET /api/forms/{id}/ - Détail d'un formulaire avec ses questions
    PATCH /api/forms/{id}/ - Modification (nom, description, statut) - CHEF_PROJET
    DELETE /api/forms/{id}/ - Suppression - CHEF_PROJET
    """

    def get_object(self, pk, user):
        try:
            return Formulaire.objects.select_related(
                "campagne", "campagne__projet", "created_by", "organization"
            ).prefetch_related("fields").get(pk=pk, organization=user.organization)
        except Formulaire.DoesNotExist:
            return None

    def get_permissions(self):
        if self.request.method in ["PATCH", "DELETE"]:
            return [IsAuthenticated(), IsChefProjetOnly(), CanManageFormulaire()]
        return [IsAuthenticated(), IsChefProjetOrGerantOrAgent(), CanViewFormulaire()]

    @extend_schema(
        responses={200: FormulaireDetailSerializer},
    )
    def get(self, request, pk):
        """Retourne le formulaire complet avec toutes ses questions triées par ordre."""
        formulaire = self.get_object(pk, request.user)
        if not formulaire:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, formulaire)

        serializer = FormulaireDetailSerializer(formulaire)
        return Response(serializer.data)

    @extend_schema(
        request=FormulaireUpdateSerializer,
        responses={200: FormulaireDetailSerializer},
    )
    def patch(self, request, pk):
        """
        Met à jour un formulaire.
        Champs modifiables : nom, description, statut
        """
        formulaire = self.get_object(pk, request.user)
        if not formulaire:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, formulaire)

        serializer = FormulaireUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            formulaire = update_formulaire(formulaire, serializer.validated_data, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        detail_serializer = FormulaireDetailSerializer(formulaire)
        return Response(detail_serializer.data)

    @extend_schema(
        responses={204: None},
    )
    def delete(self, request, pk):
        """Supprime un formulaire et toutes ses questions (CHEF_PROJET uniquement)."""
        formulaire = self.get_object(pk, request.user)
        if not formulaire:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, formulaire)

        formulaire.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Formulaires"])
class FormulairePublishView(APIView):
    """
    PATCH /api/forms/{id}/publish/ - Publier un formulaire (CHEF_PROJET)
    Conditions : au moins une question, statut = BROUILLON
    """

    permission_classes = [IsAuthenticated, IsChefProjetOnly, CanManageFormulaire]

    def get_object(self, pk, user):
        try:
            return Formulaire.objects.select_related(
                "campagne__projet", "organization"
            ).prefetch_related("fields").get(pk=pk, organization=user.organization)
        except Formulaire.DoesNotExist:
            return None

    @extend_schema(
        request=None,
        responses={200: None},
    )
    def patch(self, request, pk):
        """Publie un formulaire (BROUILLON -> PUBLIE)."""
        formulaire = self.get_object(pk, request.user)
        if not formulaire:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, formulaire)

        try:
            formulaire = publish_formulaire(formulaire, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                "message": "Formulaire publié avec succès.",
                "statut": formulaire.statut,
            }
        )


@extend_schema(tags=["Questions"])
class QuestionListCreateView(APIView):
    """
    POST /api/forms/{form_id}/questions/ - Ajouter une question (CHEF_PROJET)
    """

    permission_classes = [IsAuthenticated, IsChefProjetOnly, CanManageQuestion]

    def get_formulaire(self, form_id, user):
        try:
            return Formulaire.objects.select_related(
                "campagne__projet", "organization"
            ).get(id=form_id, organization=user.organization)
        except Formulaire.DoesNotExist:
            return None

    @extend_schema(
        request=FormFieldCreateSerializer,
        responses={201: FormFieldSerializer},
    )
    def post(self, request, form_id):
        """Ajoute une question à un formulaire en brouillon."""
        formulaire = self.get_formulaire(form_id, request.user)
        if not formulaire:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, formulaire)

        serializer = FormFieldCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            question = add_question(formulaire, serializer.validated_data, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = FormFieldSerializer(question)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Questions"])
class QuestionDetailView(APIView):
    """
    PATCH /api/forms/questions/{id}/ - Modifier une question (CHEF_PROJET)
    DELETE /api/forms/questions/{id}/ - Supprimer une question (CHEF_PROJET)
    """

    permission_classes = [IsAuthenticated, IsChefProjetOnly, CanManageQuestionObject]

    def get_question(self, pk):
        try:
            return FormField.objects.select_related(
                "formulaire", "formulaire__campagne__projet", "formulaire__organization"
            ).get(pk=pk)
        except FormField.DoesNotExist:
            return None

    @extend_schema(
        request=FormFieldUpdateSerializer,
        responses={200: FormFieldSerializer},
    )
    def patch(self, request, pk):
        """Modifie une question (label, type, obligatoire, placeholder, options, ordre)."""
        question = self.get_question(pk)
        if not question:
            return Response(
                {"detail": "Question non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, question)

        serializer = FormFieldUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            question = update_question(question, serializer.validated_data, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = FormFieldSerializer(question)
        return Response(response_serializer.data)

    @extend_schema(
        responses={204: None},
    )
    def delete(self, request, pk):
        """Supprime une question."""
        question = self.get_question(pk)
        if not question:
            return Response(
                {"detail": "Question non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, question)

        try:
            delete_question(question, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Questions"])
class QuestionDuplicateView(APIView):
    """
    POST /api/forms/questions/{id}/duplicate/ - Dupliquer une question (CHEF_PROJET)
    """

    permission_classes = [IsAuthenticated, IsChefProjetOnly, CanManageQuestionObject]

    def get_question(self, pk):
        try:
            return FormField.objects.select_related(
                "formulaire", "formulaire__campagne__projet", "formulaire__organization"
            ).get(pk=pk)
        except FormField.DoesNotExist:
            return None

    @extend_schema(
        request=DuplicateQuestionSerializer,
        responses={201: FormFieldSerializer},
    )
    def post(self, request, pk):
        """Duplique une question dans le même formulaire."""
        question = self.get_question(pk)
        if not question:
            return Response(
                {"detail": "Question non trouvée."},
                status=status.HTTP_404_NOT_FOUND
            )

        self.check_object_permissions(request, question)

        try:
            new_question = duplicate_question(question, request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = FormFieldSerializer(new_question)
        return Response(
            {
                "message": "Question dupliquée avec succès.",
                "question": response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


@extend_schema(tags=["Questions"])
class QuestionReorderView(APIView):
    """
    PATCH /api/forms/questions/reorder/ - Réordonner les questions (CHEF_PROJET)
    """

    permission_classes = [IsAuthenticated, IsChefProjetOnly]

    def get_formulaire(self, request, user):
        form_id = request.data.get("formulaire_id")
        if not form_id:
            return None
        try:
            return Formulaire.objects.select_related(
                "campagne__projet", "organization"
            ).get(id=form_id, organization=user.organization)
        except Formulaire.DoesNotExist:
            return None

    @extend_schema(
        request=ReorderQuestionsSerializer,
        responses={200: FormFieldSerializer(many=True)},
    )
    def patch(self, request):
        """Réordonne les questions d'un formulaire."""
        form_id = request.data.get("formulaire_id")
        if not form_id:
            return Response(
                {"detail": "L'ID du formulaire (formulaire_id) est requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            formulaire = Formulaire.objects.select_related(
                "campagne__projet", "organization"
            ).get(id=form_id, organization=request.user.organization)
        except Formulaire.DoesNotExist:
            return Response(
                {"detail": "Formulaire non trouvé."},
                status=status.HTTP_404_NOT_FOUND
            )

        if formulaire.campagne.projet.chef_projet != request.user:
            return Response(
                {"detail": "Seul le Chef de projet peut réordonner les questions."},
                status=status.HTTP_403_FORBIDDEN
            )

        if formulaire.statut != Formulaire.Statut.BROUILLON:
            return Response(
                {"detail": "Impossible de réordonner les questions d'un formulaire non-brouillon."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ReorderQuestionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            questions = reorder_questions(formulaire, serializer.validated_data["questions"], request.user)
        except FormulaireError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        response_serializer = FormFieldSerializer(questions, many=True)
        return Response(response_serializer.data)