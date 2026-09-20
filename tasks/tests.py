from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from projects.models import Project
from tasks.models import Task
from users.roles import AGENT, MANAGER, assign_taskflow_role


User = get_user_model()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
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
        self.other_agent = User.objects.create_user(
            email="other-agent@example.com",
            first_name="Other",
            last_name="Agent",
            password="strong-password-123",
        )
        assign_taskflow_role(self.other_agent, AGENT)
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

    def test_agent_cannot_create_task(self):
        self.authenticate(self.agent)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "Agent task",
                "status": Task.Status.TODO,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self.assertEqual(response.data["status"], "error")
        self.assertIsNone(response.data["data"])

    def test_user_only_sees_tasks_from_their_own_projects(self):
        own_task = Task.objects.create(project=self.project, title="Visible task")
        Task.objects.create(project=self.other_project, title="Hidden task")
        self.authenticate(self.user)

        response = self.client.get("/api/tasks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], own_task.id)

    def test_agent_only_sees_tasks_assigned_to_themselves(self):
        own_task = Task.objects.create(
            project=self.project,
            title="Assigned task",
            assignee=self.agent,
        )
        Task.objects.create(
            project=self.project,
            title="Other agent task",
            assignee=self.other_agent,
        )
        Task.objects.create(
            project=self.project,
            title="Unassigned task",
        )
        self.authenticate(self.agent)

        response = self.client.get("/api/tasks/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], own_task.id)

    def test_agent_cannot_see_another_agents_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Other agent task",
            assignee=self.other_agent,
        )
        self.authenticate(self.agent)

        response = self.client.get(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_agent_can_update_status_of_assigned_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Assigned task",
            status=Task.Status.TODO,
            assignee=self.agent,
        )
        self.authenticate(self.agent)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.IN_PROGRESS},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.IN_PROGRESS)

    def test_agent_cannot_modify_unassigned_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Unassigned task",
            status=Task.Status.TODO,
        )
        self.authenticate(self.agent)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.IN_PROGRESS},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def assert_agent_restricted_field_rejected(self, field, value):
        task = Task.objects.create(
            project=self.project,
            title="Assigned task",
            description="Original",
            due_date=timezone.now() + timedelta(days=1),
            assignee=self.agent,
        )
        self.authenticate(self.agent)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {field: value},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["status"], "error")

    def test_agent_cannot_change_assignee(self):
        self.assert_agent_restricted_field_rejected("assignee", self.other_agent.id)

    def test_agent_cannot_change_project(self):
        self.assert_agent_restricted_field_rejected("project", self.other_project.id)

    def test_agent_cannot_change_title(self):
        self.assert_agent_restricted_field_rejected("title", "Updated title")

    def test_agent_cannot_change_description(self):
        self.assert_agent_restricted_field_rejected("description", "Updated description")

    def test_agent_cannot_change_due_date(self):
        self.assert_agent_restricted_field_rejected(
            "due_date",
            (timezone.now() + timedelta(days=3)).isoformat(),
        )

    def test_agent_cannot_delete_task(self):
        task = Task.objects.create(
            project=self.project,
            title="Assigned task",
            assignee=self.agent,
        )
        self.authenticate(self.agent)

        response = self.client.delete(f"/api/tasks/{task.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Task.objects.filter(id=task.id).exists())

    def test_task_filters_cannot_bypass_project_ownership(self):
        Task.objects.create(
            project=self.project,
            title="Todo task",
            status=Task.Status.TODO,
        )
        Task.objects.create(
            project=self.other_project,
            title="Hidden done task",
            status=Task.Status.DONE,
        )
        self.authenticate(self.user)

        status_response = self.client.get(f"/api/tasks/?status={Task.Status.DONE}")
        project_response = self.client.get(f"/api/tasks/?project={self.other_project.id}")

        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["count"], 0)
        self.assertEqual(project_response.status_code, status.HTTP_200_OK)
        self.assertEqual(project_response.data["count"], 0)

    def test_agent_filters_cannot_bypass_assignment_scope(self):
        Task.objects.create(
            project=self.project,
            title="Own done task",
            status=Task.Status.DONE,
            assignee=self.agent,
        )
        Task.objects.create(
            project=self.project,
            title="Other todo task",
            status=Task.Status.TODO,
            assignee=self.other_agent,
        )
        self.authenticate(self.agent)

        assignee_response = self.client.get(f"/api/tasks/?assignee={self.other_agent.id}")
        status_response = self.client.get(f"/api/tasks/?status={Task.Status.TODO}")

        self.assertEqual(assignee_response.status_code, status.HTTP_200_OK)
        self.assertEqual(assignee_response.data["count"], 0)
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["count"], 0)

    def test_due_date_filters_return_matching_owned_tasks(self):
        matching_task = Task.objects.create(
            project=self.project,
            title="Matching task",
            due_date=timezone.now() + timedelta(days=2),
        )
        Task.objects.create(
            project=self.project,
            title="Outside range",
            due_date=timezone.now() + timedelta(days=10),
        )
        self.authenticate(self.user)
        from_date = (timezone.now() + timedelta(days=1)).date().isoformat()
        to_date = (timezone.now() + timedelta(days=3)).date().isoformat()

        response = self.client.get(
            f"/api/tasks/?due_date_from={from_date}&due_date_to={to_date}"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], matching_task.id)

    def test_task_list_is_paginated(self):
        Task.objects.create(project=self.project, title="First task")
        Task.objects.create(project=self.project, title="Second task")
        self.authenticate(self.user)

        response = self.client.get("/api/tasks/?page_size=1")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)

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
        self.assertEqual(fresh_response.data["results"][0]["title"], "API edit")

    def test_status_change_invalidates_cached_task_list(self):
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
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["results"][0]["status"], Task.Status.TODO)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data["results"][0]["status"], Task.Status.DONE)

    def test_agent_status_update_invalidates_agent_cached_task_list(self):
        task = Task.objects.create(
            project=self.project,
            title="Agent cached task",
            status=Task.Status.TODO,
            assignee=self.agent,
        )
        self.authenticate(self.agent)

        first_response = self.client.get("/api/tasks/")
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.IN_PROGRESS},
            format="json",
        )
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["results"][0]["status"], Task.Status.TODO)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            fresh_response.data["results"][0]["status"],
            Task.Status.IN_PROGRESS,
        )

    def test_manager_sees_fresh_data_after_agent_status_update(self):
        task = Task.objects.create(
            project=self.project,
            title="Manager cached task",
            status=Task.Status.TODO,
            assignee=self.agent,
        )
        self.authenticate(self.user)
        first_response = self.client.get("/api/tasks/")

        self.authenticate(self.agent)
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.DONE},
            format="json",
        )

        self.authenticate(self.user)
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["results"][0]["status"], Task.Status.TODO)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data["results"][0]["status"], Task.Status.DONE)

    def test_reassignment_invalidates_manager_cache(self):
        task = Task.objects.create(
            project=self.project,
            title="Manager reassignment cache",
            assignee=self.agent,
        )
        self.authenticate(self.user)
        first_response = self.client.get("/api/tasks/")

        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.other_agent.id},
            format="json",
        )
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["results"][0]["assignee"], self.agent.id)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data["results"][0]["assignee"], self.other_agent.id)

    def test_reassignment_invalidates_previous_assignee_cache(self):
        task = Task.objects.create(
            project=self.project,
            title="Previous assignee cache",
            assignee=self.agent,
        )
        self.authenticate(self.agent)
        first_response = self.client.get("/api/tasks/")

        self.authenticate(self.user)
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.other_agent.id},
            format="json",
        )

        self.authenticate(self.agent)
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["count"], 1)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data["count"], 0)

    def test_reassignment_invalidates_new_assignee_cache(self):
        task = Task.objects.create(
            project=self.project,
            title="New assignee cache",
            assignee=self.agent,
        )
        self.authenticate(self.other_agent)
        first_response = self.client.get("/api/tasks/")

        self.authenticate(self.user)
        update_response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.other_agent.id},
            format="json",
        )

        self.authenticate(self.other_agent)
        fresh_response = self.client.get("/api/tasks/")

        self.assertEqual(first_response.data["count"], 0)
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(fresh_response.data["count"], 1)
        self.assertEqual(fresh_response.data["results"][0]["id"], task.id)
