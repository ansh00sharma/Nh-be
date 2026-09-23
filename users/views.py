from django.contrib.auth import get_user_model
from django.db import IntegrityError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.mixins import (
    CreateModelMixin,
    DestroyModelMixin,
    ListModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.utils import datetime_from_epoch

from api.responses import success_response
from api.pagination import NoCountPageNumberPagination
from core.observability.decorators import traced
from users.serializers import (
    LoginSerializer,
    ManagedUserSerializer,
    SignupSerializer,
    UserSerializer,
)
from users.querysets import with_taskflow_role
from users.roles import is_admin_or_manager


User = get_user_model()


class LogoutRefreshToken(RefreshToken):
    def check_blacklist(self):
        return None


logout_request = inline_serializer(
    name="LogoutRequest",
    fields={"refresh": serializers.CharField(required=False, allow_blank=True)},
)

logout_response = inline_serializer(
    name="LogoutResponse",
    fields={
        "message": serializers.CharField(),
        "data": serializers.JSONField(allow_null=True),
        "status": serializers.CharField(),
        "status_code": serializers.IntegerField(),
    },
)


class SignupView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=SignupSerializer, responses={201: UserSerializer}, tags=["Auth"])
    @traced("auth.signup")
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=LoginSerializer, responses=LoginSerializer, tags=["Auth"])
    @traced("auth.login")
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=logout_request, responses=logout_response, tags=["Auth"])
    @traced("auth.logout")
    def post(self, request):
        refresh_token = request.data.get("refresh")

        if refresh_token:
            try:
                blacklist_refresh_token(refresh_token)
            except TokenError:
                pass

        return success_response("Logged out successfully", None)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer, tags=["Auth"])
    @traced("auth.me")
    def get(self, request):
        return Response(UserSerializer(request.user).data)


def blacklist_refresh_token(refresh_token):
    token = LogoutRefreshToken(refresh_token)
    jti = token[api_settings.JTI_CLAIM]
    created_outstanding_token = False

    try:
        outstanding_token = (
            OutstandingToken.objects.select_related("blacklistedtoken")
            .order_by()
            .get(jti=jti)
        )
    except OutstandingToken.DoesNotExist:
        outstanding_token = OutstandingToken.objects.create(
            jti=jti,
            token=str(token),
            created_at=token.current_time,
            expires_at=datetime_from_epoch(token["exp"]),
        )
        created_outstanding_token = True

    if not created_outstanding_token:
        try:
            outstanding_token.blacklistedtoken
            return
        except BlacklistedToken.DoesNotExist:
            pass

    try:
        BlacklistedToken.objects.create(token=outstanding_token)
    except IntegrityError:
        pass


class ManagedUserViewSet(
    ListModelMixin,
    CreateModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    GenericViewSet,
):
    serializer_class = ManagedUserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = NoCountPageNumberPagination

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not is_admin_or_manager(request.user):
            raise PermissionDenied("Only admins and managers can access users.")

    @traced("user.repository.list")
    def get_queryset(self):
        return with_taskflow_role(User.objects.all()).order_by("id")

    @traced("user.destroy")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response("User deleted successfully", None)
