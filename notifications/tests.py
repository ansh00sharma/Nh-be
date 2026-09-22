from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from notifications.models import Notification
from notifications.tasks import (
    create_overdue_task_notifications,
)
from projects.models import Project
from tasks.models import Task
from users.roles import AGENT, MANAGER, assign_taskflow_role


User = get_user_model()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class NotificationTests(APITestCase):
    def setUp(self):
        if hasattr(mail, "outbox"):
            mail.outbox.clear()

        self.owner = User.objects.create_user(
            email="owner@example.com",
            first_name="Project",
            last_name="Owner",
            password="strong-password-123",
        )
        assign_taskflow_role(self.owner, MANAGER)
        self.assignee = User.objects.create_user(
            email="assignee@example.com",
            first_name="Task",
            last_name="Assignee",
            password="strong-password-123",
        )
        assign_taskflow_role(self.assignee, AGENT)
        self.new_assignee = User.objects.create_user(
            email="new-assignee@example.com",
            first_name="New",
            last_name="Assignee",
            password="strong-password-123",
        )
        assign_taskflow_role(self.new_assignee, AGENT)
        self.project = Project.objects.create(name="Project", owner=self.owner)

    def authenticate(self, user):
        access_token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    def assert_email_has_view_ticket_link(self, task):
        html_message = mail.outbox[0].alternatives[0][0]
        self.assertIn("View Ticket", html_message)
        self.assertIn(f"http://13.127.86.130/tasks?task={task.id}", html_message)

    def test_creating_assigned_task_creates_notification_and_email(self):
        self.authenticate(self.owner)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "New assigned task",
                "description": "Created with assignee",
                "assignee": self.assignee.id,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task = Task.objects.get(title="New assigned task")
        notification = Notification.objects.get(
            task=task,
            user=self.assignee,
            type=Notification.Type.TASK_CREATED,
        )
        self.assertTrue(notification.is_read_by_system)
        self.assertTrue(notification.is_send)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.assignee.email])
        self.assertEqual(mail.outbox[0].subject, "TaskFlow - New Task Created")
        self.assertIn(task.title, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assertIn("New task created", mail.outbox[0].alternatives[0][0])
        self.assert_email_has_view_ticket_link(task)

    def test_creating_unassigned_task_does_not_create_notification_or_email(self):
        self.authenticate(self.owner)

        response = self.client.post(
            "/api/tasks/",
            {
                "project": self.project.id,
                "title": "New unassigned task",
                "description": "Created without assignee",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_changing_task_assignee_creates_reassignment_notification(self):
        task = Task.objects.create(project=self.project, title="Assign me")
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.new_assignee.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(
            task=task,
            user=self.new_assignee,
            type=Notification.Type.TASK_REASSIGNED,
        )
        self.assertTrue(notification.is_read_by_system)
        self.assertTrue(notification.is_send)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.new_assignee.email])
        self.assertEqual(mail.outbox[0].subject, "TaskFlow - Task Reassigned to You")
        self.assertIn(task.title, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assert_email_has_view_ticket_link(task)

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
        self.assertEqual(len(mail.outbox), 0)

    def test_unchanged_assignee_does_not_create_reassignment_notification_or_email(self):
        task = Task.objects.create(
            project=self.project,
            title="Same assignee",
            assignee=self.assignee,
        )
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"assignee": self.assignee.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

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
        self.assertEqual(mail.outbox[0].to, [self.new_assignee.email])

    def test_overdue_task_creates_notification(self):
        task = Task.objects.create(
            project=self.project,
            title="Overdue",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )

        result = create_overdue_task_notifications.delay().get()

        notification = Notification.objects.get(
            task=task,
            user=self.assignee,
            type=Notification.Type.TASK_OVERDUE,
        )
        self.assertTrue(notification.is_read_by_system)
        self.assertTrue(notification.is_send)
        self.assertEqual(result["future_due_found"], 0)
        self.assertEqual(result["notifications_send"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.assignee.email])
        self.assertEqual(mail.outbox[0].subject, "TaskFlow - Task Overdue")
        self.assertIn(task.title, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assert_email_has_view_ticket_link(task)

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
        self.assertEqual(len(mail.outbox), 0)

    def test_future_task_does_not_create_overdue_notification(self):
        Task.objects.create(
            project=self.project,
            title="Future",
            assignee=self.assignee,
            due_date=timezone.now() + timedelta(hours=1),
        )

        result = create_overdue_task_notifications.delay().get()

        self.assertFalse(Notification.objects.exists())
        self.assertEqual(result["future_due_found"], 1)
        self.assertEqual(result["notifications_send"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_repeated_overdue_checks_do_not_create_duplicates(self):
        Task.objects.create(
            project=self.project,
            title="Overdue once",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )

        first_result = create_overdue_task_notifications.delay().get()
        second_result = create_overdue_task_notifications.delay().get()

        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(first_result["notifications_send"], 1)
        self.assertEqual(second_result["notifications_send"], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_overdue_check_retries_existing_unsent_notification(self):
        task = Task.objects.create(
            project=self.project,
            title="Retry overdue",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )
        Notification.objects.create(
            user=self.assignee,
            task=task,
            type=Notification.Type.TASK_OVERDUE,
            message="Previous failed notification",
            is_read_by_system=True,
            is_send=False,
        )

        result = create_overdue_task_notifications.delay().get()

        notification = Notification.objects.get()
        self.assertEqual(Notification.objects.count(), 1)
        self.assertTrue(notification.is_read_by_system)
        self.assertTrue(notification.is_send)
        self.assertEqual(result["notifications_send"], 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_overdue_check_tracks_failed_email(self):
        task = Task.objects.create(
            project=self.project,
            title="Email failure",
            assignee=self.assignee,
            due_date=timezone.now() - timedelta(hours=1),
        )

        with patch("notifications.tasks.send_notification_email", return_value=False):
            result = create_overdue_task_notifications.delay().get()

        notification = Notification.objects.get(
            task=task,
            user=self.assignee,
            type=Notification.Type.TASK_OVERDUE,
        )
        self.assertTrue(notification.is_read_by_system)
        self.assertFalse(notification.is_send)
        self.assertEqual(result["notifications_send"], 0)

    def test_changing_task_status_creates_status_notification_and_email(self):
        task = Task.objects.create(
            project=self.project,
            title="Status task",
            assignee=self.assignee,
            status=Task.Status.TODO,
        )
        self.authenticate(self.assignee)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"status": Task.Status.IN_PROGRESS},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(
            task=task,
            user=self.owner,
            type=Notification.Type.TASK_STATUS_CHANGED,
        )
        self.assertTrue(notification.is_read_by_system)
        self.assertTrue(notification.is_send)
        self.assertIn("Todo -> In progress", notification.message)
        self.assertIn(task.title, notification.message)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertEqual(mail.outbox[0].subject, "TaskFlow - Task Status Updated")
        self.assertIn("Todo -> In progress", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].alternatives[0][1], "text/html")
        self.assert_email_has_view_ticket_link(task)

    def test_unrelated_task_update_does_not_create_status_notification_or_email(self):
        task = Task.objects.create(
            project=self.project,
            title="No status change",
            status=Task.Status.TODO,
        )
        self.authenticate(self.owner)

        response = self.client.patch(
            f"/api/tasks/{task.id}/",
            {"title": "Still no status change"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(
            Notification.objects.filter(type=Notification.Type.TASK_STATUS_CHANGED).exists()
        )
        self.assertEqual(len(mail.outbox), 0)

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
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], other_notification.id)
