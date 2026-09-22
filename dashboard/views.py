from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from api.responses import success_response
from users.roles import is_admin


class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

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
