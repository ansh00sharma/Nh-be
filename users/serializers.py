from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.db.models.functions import Lower
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.settings import api_settings

from core.observability.decorators import traced, traced_span
from users.roles import (
    AGENT,
    TASKFLOW_ROLES,
    assign_taskflow_role,
    get_allowed_modules,
    get_allowed_modules_for_role,
    get_taskflow_role,
)


User = get_user_model()


@extend_schema_field(serializers.ChoiceField(choices=TASKFLOW_ROLES))
class RoleField(serializers.Field):
    def to_representation(self, obj):
        return get_taskflow_role(obj)

    def to_internal_value(self, data):
        if data not in TASKFLOW_ROLES:
            raise serializers.ValidationError("Role must be admin, manager, or agent.")
        return {"role": data}


class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "email", "password")
        read_only_fields = ("id",)
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
            "first_name": {"required": True, "allow_blank": False},
            "last_name": {"required": True, "allow_blank": False},
        }

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    @traced("auth.signup.create_user")
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        assign_taskflow_role(user, AGENT)
        return user


class LoginSerializer(TokenObtainPairSerializer):
    @traced("auth.login.validate_credentials")
    def validate(self, attrs):
        email = (attrs.get(self.username_field) or attrs.get("username") or "").strip().lower()
        password = attrs.get("password")

        user = (
            User.objects.alias(email_lower=Lower("email"))
            .filter(email_lower=email)
            .first()
            if email
            else None
        )
        if user is None:
            raise AuthenticationFailed("No account found with this email.")

        with traced_span("auth.login.check_password"):
            password_matches = user.check_password(password)
        if not password_matches:
            raise AuthenticationFailed("Incorrect password.")

        if not user.is_active:
            raise AuthenticationFailed("This account is inactive.")

        self.user = user
        refresh = self.get_token(user)
        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)

        return data


class UserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "modules",
            "created_at",
            "updated_at",
        )

    @extend_schema_field(serializers.CharField())
    def get_username(self, obj):
        return obj.email

    @extend_schema_field(serializers.ChoiceField(choices=TASKFLOW_ROLES))
    def get_role(self, obj):
        return get_taskflow_role(obj)

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_modules(self, obj):
        annotated_role = getattr(obj, "taskflow_role", None)
        if annotated_role in TASKFLOW_ROLES:
            return get_allowed_modules_for_role(annotated_role)
        return get_allowed_modules(obj)


class ManagedUserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    role = RoleField(source="*")
    modules = serializers.SerializerMethodField(read_only=True)
    password = serializers.CharField(
        write_only=True,
        min_length=6,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "modules",
            "password",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "username", "modules", "created_at", "updated_at")
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
            "first_name": {"required": True, "allow_blank": False},
            "last_name": {"required": True, "allow_blank": False},
        }

    @extend_schema_field(serializers.CharField())
    def get_username(self, obj):
        return obj.email

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_modules(self, obj):
        return get_allowed_modules(obj)

    def validate_email(self, value):
        email = value.strip().lower()
        queryset = User.objects.filter(email__iexact=email)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return email

    def validate(self, attrs):
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Password is required."})
        return attrs

    @traced("user.serializer.create")
    def create(self, validated_data):
        role = validated_data.pop("role")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        assign_taskflow_role(user, role)
        return user

    @traced("user.serializer.update")
    def update(self, instance, validated_data):
        role = validated_data.pop("role", None)
        password = validated_data.pop("password", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if password:
            instance.set_password(password)

        instance.save()

        if role:
            assign_taskflow_role(instance, role)

        return instance
