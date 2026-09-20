from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from tasks.models import Task


User = get_user_model()


class TaskAPITests(APITestCase):
    def setUp(self):
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
