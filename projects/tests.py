from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from users.roles import AGENT, MANAGER, assign_taskflow_role


User = get_user_model()


class ProjectAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(self.user, MANAGER)
        self.other_user = User.objects.create_user(
            email="bob@example.com",
            first_name="Bob",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(self.other_user, MANAGER)
        self.agent = User.objects.create_user(
            email="agent@example.com",
            first_name="Task",
            last_name="Agent",
            password="strong-password-123",
        )
        assign_taskflow_role(self.agent, AGENT)

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_authenticated_user_can_create_project(self):
        self.authenticate(self.user)

        response = self.client.post(
            "/api/projects/",
            {
                "name": "Launch Plan",
                "description": "POC project",
                "owner": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(id=response.data["id"])
        self.assertEqual(project.owner, self.user)
        self.assertEqual(response.data["owner"], self.user.id)

    def test_agent_cannot_create_project(self):
        self.authenticate(self.agent)

        response = self.client.post(
            "/api/projects/",
            {
                "name": "Agent Project",
                "description": "Not allowed",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_create_project(self):
        response = self.client.post(
            "/api/projects/",
            {
                "name": "Launch Plan",
                "description": "POC project",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["status"], "error")

    def test_user_only_sees_their_own_projects(self):
        own_project = Project.objects.create(
            name="Own Project",
            description="Visible",
            owner=self.user,
        )
        Project.objects.create(
            name="Other Project",
            description="Hidden",
            owner=self.other_user,
        )
        self.authenticate(self.user)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], own_project.id)

    def test_agent_cannot_list_projects(self):
        Project.objects.create(
            name="Own Project",
            description="Hidden from agent",
            owner=self.user,
        )
        self.authenticate(self.agent)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_retrieve_their_own_project(self):
        project = Project.objects.create(
            name="Own Project",
            description="Visible",
            owner=self.user,
        )
        self.authenticate(self.user)

        response = self.client.get(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], project.id)

    def test_user_cannot_access_another_users_project(self):
        project = Project.objects.create(
            name="Other Project",
            description="Hidden",
            owner=self.other_user,
        )
        self.authenticate(self.user)

        response = self.client.get(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["status"], "error")

    def test_agent_cannot_retrieve_project(self):
        project = Project.objects.create(
            name="Manager Project",
            description="Hidden from agent",
            owner=self.user,
        )
        self.authenticate(self.agent)

        response = self.client.get(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_update_their_own_project(self):
        project = Project.objects.create(
            name="Own Project",
            description="Visible",
            owner=self.user,
        )
        self.authenticate(self.user)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {
                "name": "Updated Project",
                "owner": self.other_user.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        self.assertEqual(project.name, "Updated Project")
        self.assertEqual(project.owner, self.user)

    def test_user_cannot_update_another_users_project(self):
        project = Project.objects.create(
            name="Other Project",
            description="Hidden",
            owner=self.other_user,
        )
        self.authenticate(self.user)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"name": "Updated Project"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        project.refresh_from_db()
        self.assertEqual(project.name, "Other Project")

    def test_user_can_delete_their_own_project(self):
        project = Project.objects.create(
            name="Own Project",
            description="Visible",
            owner=self.user,
        )
        self.authenticate(self.user)

        response = self.client.delete(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Project.objects.filter(id=project.id).exists())

    def test_user_cannot_delete_another_users_project(self):
        project = Project.objects.create(
            name="Other Project",
            description="Hidden",
            owner=self.other_user,
        )
        self.authenticate(self.user)

        response = self.client.delete(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Project.objects.filter(id=project.id).exists())
