from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from tasks.models import Task


User = get_user_model()


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "task-tests",
        }
    }
)
class TaskAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="alice@example.com",
            first_name="Alice",
            last_name="Example",
            password="strong-password-123",
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com",
            first_name="Bob",
            last_name="Example",
            password="strong-password-123",
        )
        self.project = Project.objects.create(name="Own Project", owner=self.user)
        self.other_project = Project.objects.create(
            name="Other Project",
            owner=self.other_user,
        )

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_user_can_create_task_for_their_own_project(self):
        self.authenticate(self.user)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Write POC",
                "status": Task.Status.TODO,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.get().project, self.project)

    def test_user_cannot_create_task_for_another_users_project(self):
        self.authenticate(self.user)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.other_project.id,
                "title": "Hidden task",
                "status": Task.Status.TODO,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)

    def test_user_only_sees_tasks_from_their_own_projects(self):
        own_task = Task.objects.create(project=self.project, title="Visible task")
        Task.objects.create(project=self.other_project, title="Hidden task")
        self.authenticate(self.user)

        response = self.client.get("/api/tasks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], own_task.id)

    def test_repeated_task_list_request_uses_cache_until_invalidated(self):
        task = Task.objects.create(project=self.project, title="Original title")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        task.title = "Direct DB edit"
        task.save()
        cached_response = self.client.get("/api/tasks/")
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"title": "API edit"},
            format="json",
        )
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data, cached_response.data)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data[0]["title"], "API edit")
