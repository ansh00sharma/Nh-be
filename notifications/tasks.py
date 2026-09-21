from celery import shared_task
from django.utils import timezone

from notifications.models import Notification
from notifications.services import send_notification_email
from tasks.models import Task


@shared_task
def create_task_reassigned_notification(task_id, assignee_id):
    task = Task.objects.select_related("assignee", "project").get(id=task_id)
    if task.assignee_id != assignee_id or assignee_id is None:
        return

    message = (
        f"You have been assigned to task: {task.title}\n"
        f"Project: {task.project.name}"
    )
    Notification.objects.create(
        user_id=assignee_id,
        task=task,
        type=Notification.Type.TASK_REASSIGNED,
        message=message,
    )
    send_notification_email(
        task.assignee,
        "TaskFlow - Task Assigned to You",
        message,
    )


@shared_task
def create_task_status_changed_notification(task_id, old_status, new_status, changed_by_id=None):
    task = Task.objects.select_related("project", "project__owner", "assignee").get(id=task_id)
    if task.status != new_status or old_status == new_status:
        return

    assignee_name = _user_name(task.assignee) if task.assignee else "Unassigned"
    message = (
        f"Task status updated: {task.title}\n"
        f"Project: {task.project.name}\n"
        f"Status: {_status_label(old_status)} -> {_status_label(new_status)}\n"
        f"Assignee: {assignee_name}"
    )
    Notification.objects.create(
        user=task.project.owner,
        task=task,
        type=Notification.Type.TASK_STATUS_CHANGED,
        message=message,
    )
    send_notification_email(
        task.project.owner,
        "TaskFlow - Task Status Updated",
        message,
    )


@shared_task
def create_overdue_task_notifications():
    overdue_tasks = Task.objects.filter(
        due_date__lt=timezone.now(),
        assignee__isnull=False,
    ).exclude(status=Task.Status.DONE).select_related("assignee", "project")

    created_count = 0
    for task in overdue_tasks:
        already_notified = Notification.objects.filter(
            task=task,
            type=Notification.Type.TASK_OVERDUE,
        ).exists()
        if already_notified:
            continue

        message = (
            f"Task is overdue: {task.title}\n"
            f"Project: {task.project.name}\n"
            f"Due date: {timezone.localtime(task.due_date).strftime('%b %d, %Y, %I:%M %p')}"
        )
        Notification.objects.create(
            user=task.assignee,
            task=task,
            type=Notification.Type.TASK_OVERDUE,
            message=message,
        )
        send_notification_email(
            task.assignee,
            "TaskFlow - Task Overdue",
            message,
        )
        created_count += 1

    return created_count


def _status_label(value):
    return dict(Task.Status.choices).get(value, value)


def _user_name(user):
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.email
