from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from users.roles import ADMIN, AGENT, MANAGER, assign_taskflow_role


User = get_user_model()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "project-tests",
        }
    }
)
class ProjectAPITests(APITestCase):
    def setUp(self):
        cache.clear()
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
        self.admin = User.objects.create_user(
            email="admin@example.com",
            first_name="Admin",
            last_name="Example",
            password="strong-password-123",
        )
        assign_taskflow_role(self.admin, ADMIN)

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def force_authenticate(self, user):
        self.client.credentials()
        self.client.force_authenticate(user=user)

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

    def test_admin_can_access_all_projects(self):
        manager_project = Project.objects.create(name="Manager Project", owner=self.user)
        admin_project = Project.objects.create(name="Admin Project", owner=self.admin)
        self.authenticate(self.admin)

        response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)
        self.assertTrue(
            {manager_project.id, admin_project.id}.issubset(
                {project["id"] for project in response.data["results"]}
            )
        )

    def test_repeated_project_list_request_uses_cache_until_invalidated(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.authenticate(self.user)

        first_response = self.client.get("/api/projects/")
        Project.objects.create(name="Direct DB Project", owner=self.user)
        cached_response = self.client.get("/api/projects/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data, cached_response.data)
        self.assertEqual(cached_response.data["count"], 1)

        create_response = self.client.post(
            "/api/projects/",
            {"name": "API Created Project"},
            format="json",
        )
        refreshed_response = self.client.get("/api/projects/")

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(refreshed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["count"], 3)

    def test_project_list_cache_miss_then_hit_and_reduces_queries(self):
        for index in range(3):
            Project.objects.create(name=f"Project {index}", owner=self.user)
        self.force_authenticate(self.user)

        with self.assertLogs("api.response_cache", level="INFO") as logs:
            with CaptureQueriesContext(connection) as cold_queries:
                first_response = self.client.get("/api/projects/?page_size=10")
            with CaptureQueriesContext(connection) as warm_queries:
                cached_response = self.client.get("/api/projects/?page_size=10")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data, cached_response.data)
        self.assertLess(len(warm_queries), len(cold_queries))
        messages = "\n".join(logs.output)
        self.assertIn(f"[PROJECT CACHE MISS] user={self.user.id}", messages)
        self.assertIn(f"[PROJECT CACHE HIT] user={self.user.id}", messages)

    def test_project_list_cache_is_user_specific(self):
        own_project = Project.objects.create(name="Own Project", owner=self.user)
        other_project = Project.objects.create(name="Other Project", owner=self.other_user)

        with self.assertLogs("api.response_cache", level="INFO") as logs:
            self.force_authenticate(self.user)
            own_response = self.client.get("/api/projects/?page_size=10")
            self.force_authenticate(self.other_user)
            other_response = self.client.get("/api/projects/?page_size=10")

        self.assertEqual(own_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_response.status_code, status.HTTP_200_OK)
        self.assertEqual(own_response.data["results"][0]["id"], own_project.id)
        self.assertEqual(other_response.data["results"][0]["id"], other_project.id)
        messages = "\n".join(logs.output)
        self.assertEqual(messages.count("[PROJECT CACHE MISS]"), 2)
        self.assertNotIn("[PROJECT CACHE HIT]", messages)

    def test_project_list_cache_separates_different_query_parameters(self):
        for index in range(12):
            Project.objects.create(name=f"Project {index}", owner=self.user)
        self.force_authenticate(self.user)

        with self.assertLogs("api.response_cache", level="INFO") as logs:
            page_size_10_response = self.client.get("/api/projects/?page_size=10")
            page_size_20_response = self.client.get("/api/projects/?page_size=20")

        self.assertEqual(page_size_10_response.status_code, status.HTTP_200_OK)
        self.assertEqual(page_size_20_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(page_size_10_response.data["results"]), 10)
        self.assertEqual(len(page_size_20_response.data["results"]), 12)
        messages = "\n".join(logs.output)
        self.assertEqual(messages.count("[PROJECT CACHE MISS]"), 2)
        self.assertNotIn("[PROJECT CACHE HIT]", messages)

    def test_project_list_cache_normalizes_query_parameter_order(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.authenticate(self.user)

        first_response = self.client.get("/api/projects/?page=1&page_size=10")
        Project.objects.create(name="Direct DB Project", owner=self.user)
        cached_response = self.client.get("/api/projects/?page_size=10&page=1")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data, cached_response.data)
        self.assertEqual(cached_response.data["count"], 1)

    def test_post_is_not_served_from_project_list_cache(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.force_authenticate(self.user)

        first_response = self.client.get("/api/projects/")
        post_response = self.client.post(
            "/api/projects/",
            {"name": "Created By Post", "description": "Fresh write"},
            format="json",
        )
        refreshed_response = self.client.get("/api/projects/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(post_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(post_response.data["name"], "Created By Post")
        self.assertEqual(refreshed_response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["count"], 2)

    def test_project_list_cache_logs_miss_and_hit(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.authenticate(self.user)

        with self.assertLogs("api.response_cache", level="INFO") as logs:
            first_response = self.client.get("/api/projects/?page_size=10")
            cached_response = self.client.get("/api/projects/?page_size=10")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data, cached_response.data)
        messages = "\n".join(logs.output)
        self.assertIn("[PROJECT CACHE CHECK]", messages)
        self.assertIn("version=", messages)
        self.assertIn("redis_get_ms=", messages)
        self.assertIn("cached_type=", messages)
        self.assertIn("cached_size=", messages)
        self.assertIn("project_cache_ttl=300", messages)
        self.assertIn("[PROJECT CACHE SET] success=true", messages)
        self.assertIn("ttl=300", messages)
        self.assertIn("hit=false", messages)
        self.assertIn("hit=true", messages)
        self.assertIn(f"[PROJECT CACHE MISS] user={self.user.id}", messages)
        self.assertIn(f"[PROJECT CACHE HIT] user={self.user.id}", messages)
        self.assertIn(f":list:user:{self.user.id}:", messages)
        self.assertIn("key=api:projects:v", messages)

    def test_project_update_invalidates_cached_project_list(self):
        project = Project.objects.create(name="Original Project", owner=self.user)
        self.authenticate(self.user)

        self.client.get("/api/projects/")
        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"name": "Updated Project"},
            format="json",
        )
        refreshed_response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["results"][0]["name"], "Updated Project")

    def test_project_put_invalidates_cached_project_list(self):
        project = Project.objects.create(name="Original Project", owner=self.user)
        self.force_authenticate(self.user)

        self.client.get("/api/projects/")
        response = self.client.put(
            f"/api/projects/{project.id}/",
            {"name": "PUT Updated Project", "description": "Updated by PUT"},
            format="json",
        )
        refreshed_response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            refreshed_response.data["results"][0]["name"],
            "PUT Updated Project",
        )

    def test_project_delete_invalidates_cached_project_list(self):
        project = Project.objects.create(name="Delete Project", owner=self.user)
        self.authenticate(self.user)

        self.client.get("/api/projects/")
        response = self.client.delete(f"/api/projects/{project.id}/")
        refreshed_response = self.client.get("/api/projects/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed_response.data["count"], 0)

    def test_error_project_list_response_is_not_cached(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.force_authenticate(self.user)

        with self.assertLogs("api.response_cache", level="INFO") as logs:
            first_response = self.client.get("/api/projects/?page=not-a-number")
            second_response = self.client.get("/api/projects/?page=not-a-number")

        self.assertNotEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.status_code, second_response.status_code)
        messages = "\n".join(logs.output)
        self.assertEqual(messages.count("[PROJECT CACHE MISS]"), 2)
        self.assertNotIn("[PROJECT CACHE HIT]", messages)

    def test_cached_project_list_still_requires_authentication_and_permission(self):
        Project.objects.create(name="Cached Project", owner=self.user)
        self.force_authenticate(self.user)

        cached_response = self.client.get("/api/projects/")
        cached_hit_response = self.client.get("/api/projects/")

        self.assertEqual(cached_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cached_hit_response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=None)
        unauthenticated_response = self.client.get("/api/projects/")
        self.assertEqual(unauthenticated_response.status_code, status.HTTP_401_UNAUTHORIZED)

        self.force_authenticate(self.agent)
        forbidden_response = self.client.get("/api/projects/")
        self.assertEqual(forbidden_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_project(self):
        self.authenticate(self.admin)

        response = self.client.post(
            "/api/projects/",
            {"name": "Admin Created", "description": "Owned by admin"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        project = Project.objects.get(id=response.data["id"])
        self.assertEqual(project.owner, self.admin)

    def test_admin_can_update_manager_owned_project(self):
        project = Project.objects.create(name="Manager Project", owner=self.user)
        self.authenticate(self.admin)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"name": "Admin Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        project.refresh_from_db()
        self.assertEqual(project.name, "Admin Updated")

    def test_admin_can_delete_manager_owned_project(self):
        project = Project.objects.create(name="Manager Project", owner=self.user)
        self.authenticate(self.admin)

        response = self.client.delete(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Project.objects.filter(id=project.id).exists())

    def test_manager_cannot_update_admin_owned_project(self):
        project = Project.objects.create(name="Admin Project", owner=self.admin)
        self.authenticate(self.user)

        response = self.client.patch(
            f"/api/projects/{project.id}/",
            {"name": "Manager Override"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        project.refresh_from_db()
        self.assertEqual(project.name, "Admin Project")

    def test_manager_cannot_delete_admin_owned_project(self):
        project = Project.objects.create(name="Admin Project", owner=self.admin)
        self.authenticate(self.user)

        response = self.client.delete(f"/api/projects/{project.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Project.objects.filter(id=project.id).exists())
