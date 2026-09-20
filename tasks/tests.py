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
            "LOCATION": "task-api-tests",
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
        self.assignee = User.objects.create_user(
            email="casey@example.com",
            first_name="Casey",
            last_name="Example",
            password="strong-password-123",
        )
        self.project = Project.objects.create(
            name="Own Project",
            description="Visible",
            owner=self.user,
        )
        self.other_project = Project.objects.create(
            name="Other Project",
            description="Hidden",
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
                "description": "Build the task endpoint",
                "status": Task.Status.TODO,
                "assignee": self.assignee.id,
                "due_date": "2026-10-01T12:00:00Z",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task = Task.objects.get(id=response.data["id"])
        self.assertEqual(task.project, self.project)
        self.assertEqual(task.assignee, self.assignee)

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


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "task-list-cache-tests",
        }
    }
)
class TaskListCacheTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="alice-cache@example.com",
            first_name="Alice",
            last_name="Cache",
            password="strong-password-123",
        )
        self.other_user = User.objects.create_user(
            email="bob-cache@example.com",
            first_name="Bob",
            last_name="Cache",
            password="strong-password-123",
        )
        self.assignee = User.objects.create_user(
            email="casey-cache@example.com",
            first_name="Casey",
            last_name="Cache",
            password="strong-password-123",
        )
        self.project = Project.objects.create(
            name="Own Cached Project",
            description="Visible",
            owner=self.user,
        )
        self.other_project = Project.objects.create(
            name="Other Cached Project",
            description="Hidden",
            owner=self.other_user,
        )

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_repeated_identical_task_list_request_can_use_cache(self):
        Task.objects.create(project=self.project, title="Cached task")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        Task.objects.create(project=self.project, title="Direct DB task")
        second_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data, second_response.data)
        self.assertEqual(len(second_response.data), 1)

    def test_different_users_do_not_share_cached_results(self):
        Task.objects.create(project=self.project, title="Alice task")
        Task.objects.create(project=self.other_project, title="Bob task")

        self.authenticate(self.user)
        user_response = self.client.get("/api/tasks/")

        self.authenticate(self.other_user)
        other_response = self.client.get("/api/tasks/")

        self.assertEqual(user_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user_response.data[0]["title"], "Alice task")
        self.assertEqual(other_response.data[0]["title"], "Bob task")

    def test_different_filters_create_independent_cached_results(self):
        Task.objects.create(project=self.project, title="First task")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/?status=todo")
        Task.objects.create(project=self.project, title="Second task")
        second_response = self.client.get("/api/tasks/?status=done")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(first_response.data), 1)
        self.assertEqual(len(second_response.data), 2)

    def test_task_creation_invalidates_user_task_list_cache(self):
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        create_response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Created through API",
                "status": Task.Status.TODO,
            },
            format="json",
        )
        second_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(first_response.data), 0)
        self.assertEqual(len(second_response.data), 1)
        self.assertEqual(second_response.data[0]["title"], "Created through API")

    def test_task_status_update_invalidates_cache(self):
        task = Task.objects.create(
            project=self.project,
            title="Status task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.DONE},
            format="json",
        )
        second_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data[0]["status"], Task.Status.TODO)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data[0]["status"], Task.Status.DONE)

    def test_task_reassignment_invalidates_cache(self):
        task = Task.objects.create(project=self.project, title="Assignee task")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.assignee.id},
            format="json",
        )
        second_response = self.client.get("/api/tasks/")

        self.assertIsNone(first_response.data[0]["assignee"])
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data[0]["assignee"], self.assignee.id)

    def test_task_deletion_invalidates_cache(self):
        task = Task.objects.create(project=self.project, title="Delete task")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        delete_response = self.client.delete(f"/api/tasks/{task.id}/")
        second_response = self.client.get("/api/tasks/")

        self.assertEqual(len(first_response.data), 1)
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(len(second_response.data), 0)

    def test_after_update_next_get_returns_fresh_data(self):
        task = Task.objects.create(project=self.project, title="Original title")
        self.authenticate(self.user)

        first_response = self.client.get("/api/tasks/")
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"title": "Fresh title"},
            format="json",
        )
        second_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data[0]["title"], "Original title")
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.data[0]["title"], "Fresh title")

    def test_user_only_sees_tasks_from_their_own_projects(self):
        own_task = Task.objects.create(
            project=self.project,
            title="Visible task",
            status=Task.Status.TODO,
        )
        Task.objects.create(
            project=self.other_project,
            title="Hidden task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.get("/api/tasks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], own_task.id)

    def test_user_can_retrieve_their_own_projects_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Visible task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.get(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], task.id)

    def test_user_cannot_retrieve_another_users_task(self):
        task = Task.objects.create(
            project=self.other_project,
            title="Hidden task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.get(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_update_their_own_projects_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Visible task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {
                "title": "Updated task",
                "status": Task.Status.IN_PROGRESS,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.title, "Updated task")
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)

    def test_user_cannot_update_another_users_task(self):
        task = Task.objects.create(
            project=self.other_project,
            title="Hidden task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"title": "Updated task"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        task.refresh_from_db()
        self.assertEqual(task.title, "Hidden task")

    def test_user_can_delete_their_own_projects_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Visible task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.user)

        response = self.client.delete(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_invalid_task_status_is_rejected(self):
        self.authenticate(self.user)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Bad status",
                "status": "blocked",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_invalid_nonexistent_project_is_rejected(self):
        self.authenticate(self.user)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": 999999,
                "title": "Bad project",
                "status": Task.Status.TODO,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project", response.data)
