from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from users.roles import AGENT, assign_taskflow_role, get_taskflow_role


User = get_user_model()


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

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        assign_taskflow_role(user, AGENT)
        return user


LoginSerializer = TokenObtainPairSerializer


class UserSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "created_at",
            "updated_at",
        )

    def get_username(self, obj):
        return obj.email

    def get_role(self, obj):
        return get_taskflow_role(obj)
