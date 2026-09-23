from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from api.responses import success_response
from core.observability.decorators import traced
from users.roles import is_admin


dashboard_response = inline_serializer(
    name="DashboardResponse",
    fields={
        "message": serializers.CharField(),
        "status": serializers.CharField(),
        "status_code": serializers.IntegerField(),
        "data": inline_serializer(
            name="DashboardData",
            fields={
                "title": serializers.CharField(),
                "message": serializers.CharField(),
            },
        ),
    },
)


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=dashboard_response, tags=["Dashboard"])
    @traced("dashboard.build_response")
    def get(self, request):
        if not is_admin(request.user):
            raise PermissionDenied("Only admins can access the dashboard.")

        return success_response(
            "Dashboard loaded successfully",
            {
                "title": "Dashboard",
                "message": "Dashboard implementation will be added later.",
            },
        )
