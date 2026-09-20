from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.models import Notification
from notifications.tasks import create_overdue_task_notifications
from projects.models import Project
from tasks.models import Task


User = get_user_model()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class NotificationTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            first_name="Project",
            last_name="Owner",
            password="strong-password-123",
        )
        self.assignee = User.objects.create_user(
            email="assignee@example.com",
            first_name="Task",
            last_name="Assignee",
            password="strong-password-123",
        )
        self.new_assignee = User.objects.create_user(
            email="new-assignee@example.com",
            first_name="New",
            last_name="Assignee",
            password="strong-password-123",
        )
        self.project = Project.objects.create(name="Project", owner=self.owner)

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def test_changing_task_assignee_creates_reassignment_notification(self):
        task = Task.objects.create(project=self.project, title="Assign me")
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.new_assignee.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Notification.objects.filter(
                task=task,
                user=self.new_assignee,
                type=Notification.Type.TASK_REASSIGNED,
            ).exists()
        )

    def test_updating_task_without_assignee_change_does_not_notify(self):
        task = Task.objects.create(
            project=self.project,
            title="Original",
            assignee=self.assignee,
        )
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"title": "Updated"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.exists())

    def test_reassignment_notification_belongs_to_new_assignee(self):
        task = Task.objects.create(
            project=self.project,
            title="Reassign me",
            assignee=self.assignee,
        )
        self.authenticate(self.owner)

        self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.new_assignee.id},
            format="json",
        )

        notification = Notification.objects.get()
        self.assertEqual(notification.user, self.new_assignee)
        self.assertNotEqual(notification.user, self.assignee)

    def test_overdue_task_creates_notification(self):
        task = Task.objects.create(
            project=self.project,
            title="Overdue",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )

        create_overdue_task_notifications.delay()

        self.assertTrue(
            Notification.objects.filter(
                task=task,
                user=self.assignee,
                type=Notification.Type.TASK_OVERDUE,
            ).exists()
        )

    def test_completed_task_does_not_create_overdue_notification(self):
        Task.objects.create(
            project=self.project,
            title="Done",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
            status=Task.Status.DONE,
        )

        create_overdue_task_notifications.delay()

        self.assertFalse(Notification.objects.exists())

    def test_future_task_does_not_create_overdue_notification(self):
        Task.objects.create(
            project=self.project,
            title="Future",
            assignee=self.assignee,
            due_date=timezone.now() + timedelta(hours=1),
        )

        create_overdue_task_notifications.delay()

        self.assertFalse(Notification.objects.exists())

    def test_repeated_overdue_checks_do_not_create_duplicates(self):
        Task.objects.create(
            project=self.project,
            title="Overdue once",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )

        create_overdue_task_notifications.delay()
        create_overdue_task_notifications.delay()

        self.assertEqual(Notification.objects.count(), 1)

    def test_user_only_sees_their_own_notifications(self):
        task = Task.objects.create(project=self.project, title="Visible")
        other_notification = Notification.objects.create(
            user=self.owner,
            task=task,
            type=Notification.Type.TASK_REASSIGNED,
            message="Owner notification",
        )
        Notification.objects.create(
            user=self.assignee,
            task=task,
            type=Notification.Type.TASK_REASSIGNED,
            message="Assignee notification",
        )
        self.authenticate(self.owner)

        response = self.client.get("/api/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], other_notification.id)
