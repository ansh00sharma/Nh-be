from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from users.roles import ADMIN, MANAGER, assign_taskflow_role


User = get_user_model()


class DashboardAPITests(APITestCase):
    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_admin_can_access_dashboard(self):
        user = User.objects.create_user(
            email="admin@example.com",
            first_name="Admin",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(user, ADMIN)
        self.authenticate(user)

        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["title"], "Dashboard")

    def test_manager_cannot_access_dashboard(self):
        user = User.objects.create_user(
            email="manager@example.com",
            first_name="Manager",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(user, MANAGER)
        self.authenticate(user)

        response = self.client.get("/api/dashboard/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
