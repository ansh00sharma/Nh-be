import logging
from zoneinfo import ZoneInfo

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from notifications.models import Notification
from notifications.services import send_notification_email
from tasks.models import Task

logger = logging.getLogger(__name__)
User = get_user_model()
IST_TIME_ZONE = ZoneInfo("Asia/Kolkata")
TASKFLOW_PRODUCTION_TASKS_URL = "http://15.252.221.30/tasks"


@shared_task
def create_task_created_notification(task_id, assignee_id, assigned_by_id=None):
    task = Task.objects.select_related("assignee", "project", "project__owner").get(id=task_id)
    if task.assignee_id != assignee_id or assignee_id is None:
        return

    assigned_by = _get_user(assigned_by_id) or task.project.owner
    message = _plain_task_message(
        heading=f"A new task has been created for you: {task.title}",
        task=task,
        assigned_by=assigned_by,
    )
    _create_notification_and_send_email(
        user=task.assignee,
        task=task,
        notification_type=Notification.Type.TASK_CREATED,
        message=message,
        subject="TaskFlow - New Task Created",
        template_name="emails/task_created.html",
        context=_task_email_context(task, assigned_by=assigned_by, event_label="New Task"),
    )


@shared_task
def create_task_reassigned_notification(task_id, assignee_id, assigned_by_id=None):
    task = Task.objects.select_related("assignee", "project", "project__owner").get(id=task_id)
    if task.assignee_id != assignee_id or assignee_id is None:
        return

    assigned_by = _get_user(assigned_by_id) or task.project.owner
    message = _plain_task_message(
        heading=f"This task has been reassigned to you: {task.title}",
        task=task,
        assigned_by=assigned_by,
    )
    _create_notification_and_send_email(
        user=task.assignee,
        task=task,
        notification_type=Notification.Type.TASK_REASSIGNED,
        message=message,
        subject="TaskFlow - Task Reassigned to You",
        template_name="emails/task_reassigned.html",
        context=_task_email_context(task, assigned_by=assigned_by, event_label="Task Reassigned"),
    )


@shared_task
def create_task_status_changed_notification(task_id, old_status, new_status, changed_by_id=None):
    task = Task.objects.select_related("project", "project__owner", "assignee").get(id=task_id)
    if task.status != new_status or old_status == new_status:
        return

    changed_by = _get_user(changed_by_id)
    assignee_name = _user_name(task.assignee) if task.assignee else "Unassigned"
    message = (
        f"Task status updated: {task.title}\n"
        f"Project: {task.project.name}\n"
        f"Status: {_status_label(old_status)} -> {_status_label(new_status)}\n"
        f"Assignee: {assignee_name}"
    )
    _create_notification_and_send_email(
        user=task.project.owner,
        task=task,
        notification_type=Notification.Type.TASK_STATUS_CHANGED,
        message=message,
        subject="TaskFlow - Task Status Updated",
        template_name="emails/task_status_changed.html",
        context=_task_email_context(
            task,
            assigned_by=changed_by,
            event_label="Status Updated",
            old_status=_status_label(old_status),
            new_status=_status_label(new_status),
        ),
    )


@shared_task
def create_overdue_task_notifications():
    now = timezone.now()
    overdue_tasks = Task.objects.filter(
        due_date__lt=now,
        assignee__isnull=False,
    ).exclude(status=Task.Status.DONE).select_related("assignee", "project")
    future_due_count = Task.objects.filter(
        due_date__gte=now,
        assignee__isnull=False,
    ).exclude(status=Task.Status.DONE).count()

    notifications_send = 0

    for task in overdue_tasks:
        notification = Notification.objects.filter(
            user=task.assignee,
            task=task,
            type=Notification.Type.TASK_OVERDUE,
        ).first()

        if notification and notification.is_read_by_system and notification.is_send:
            continue

        message = _plain_task_message(
            heading=f"Task is overdue: {task.title}",
            task=task,
            assigned_by=task.project.owner,
        )

        if notification:
            notification.message = message
            notification.is_read_by_system = True
            notification.save(update_fields=["message", "is_read_by_system"])
        else:
            notification = Notification.objects.create(
                user=task.assignee,
                task=task,
                type=Notification.Type.TASK_OVERDUE,
                message=message,
                is_read_by_system=True,
                is_send=False,
            )

        email_sent = _send_and_mark_notification(
            notification,
            task.assignee,
            "TaskFlow - Task Overdue",
            message,
            "emails/task_overdue.html",
            _task_email_context(task, assigned_by=task.project.owner, event_label="Task Overdue"),
        )
        if email_sent:
            notifications_send += 1

    summary = {
        "future_due_found": future_due_count,
        "notifications_send": notifications_send,
    }
    logger.info("Overdue notification scan finished: %s", summary)
    return summary


def _create_notification_and_send_email(
    user,
    task,
    notification_type,
    message,
    subject,
    template_name,
    context,
):
    notification = Notification.objects.create(
        user=user,
        task=task,
        type=notification_type,
        message=message,
        is_read_by_system=True,
        is_send=False,
    )
    return _send_and_mark_notification(
        notification,
        user,
        subject,
        message,
        template_name,
        context,
    )


def _send_and_mark_notification(notification, user, subject, message, template_name, context):
    email_sent = send_notification_email(
        user,
        subject,
        message,
        template_name,
        context,
    )
    notification.is_send = email_sent
    notification.save(update_fields=["is_send"])
    return email_sent


def _plain_task_message(heading, task, assigned_by=None):
    lines = [
        heading,
        f"Task: {task.title}",
        f"Description: {task.description or '-'}",
        f"Project: {task.project.name}",
        f"Assigned by: {_user_name(assigned_by) if assigned_by else '-'}",
        f"Current status: {_status_label(task.status)}",
        f"Due date (IST): {_format_due_date(task.due_date)}",
    ]
    return "\n".join(lines)


def _task_email_context(task, assigned_by=None, event_label="", old_status=None, new_status=None):
    return {
        "event_label": event_label,
        "task_url": f"{TASKFLOW_PRODUCTION_TASKS_URL}?task={task.id}",
        "task_name": task.title,
        "description": task.description or "-",
        "project_name": task.project.name,
        "assigned_by": _user_name(assigned_by) if assigned_by else "-",
        "assignee": _user_name(task.assignee) if task.assignee else "Unassigned",
        "current_status": _status_label(task.status),
        "old_status": old_status,
        "new_status": new_status,
        "due_date": _format_due_date(task.due_date),
    }


def _format_due_date(value):
    if not value:
        return "-"
    return timezone.localtime(value, IST_TIME_ZONE).strftime("%b %d, %Y, %I:%M %p IST")


def _get_user(user_id):
    if not user_id:
        return None
    return User.objects.filter(id=user_id).first()


def _status_label(value):
    return dict(Task.Status.choices).get(value, value)


def _user_name(user):
    name = f"{user.first_name} {user.last_name}".strip()
    return name or user.email
