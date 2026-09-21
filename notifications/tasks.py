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
    Notification.objects.create(
        user_id=assignee_id,
        task=task,
        type=Notification.Type.TASK_CREATED,
        message=message,
    )
    send_notification_email(
        task.assignee,
        "TaskFlow - New Task Created",
        message,
        "emails/task_created.html",
        _task_email_context(task, assigned_by=assigned_by, event_label="New Task"),
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
    Notification.objects.create(
        user_id=assignee_id,
        task=task,
        type=Notification.Type.TASK_REASSIGNED,
        message=message,
    )
    send_notification_email(
        task.assignee,
        "TaskFlow - Task Reassigned to You",
        message,
        "emails/task_reassigned.html",
        _task_email_context(task, assigned_by=assigned_by, event_label="Task Reassigned"),
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
        "emails/task_status_changed.html",
        _task_email_context(
            task,
            assigned_by=changed_by,
            event_label="Status Updated",
            old_status=_status_label(old_status),
            new_status=_status_label(new_status),
        ),
    )


@shared_task
def create_overdue_task_notifications():
    overdue_tasks = Task.objects.filter(
        due_date__lt=timezone.now(),
        assignee__isnull=False,
    ).exclude(status=Task.Status.DONE).select_related("assignee", "project")

    overdue_count = overdue_tasks.count()
    logger.info("Overdue notification scan found %s task(s).", overdue_count)

    created_count = 0
    skipped_count = 0
    email_sent_count = 0
    email_failed_count = 0

    for task in overdue_tasks:
        already_notified = Notification.objects.filter(
            task=task,
            type=Notification.Type.TASK_OVERDUE,
        ).exists()
        if already_notified:
            skipped_count += 1
            logger.info(
                "Skipping overdue task notification for task_id=%s assignee_id=%s: already notified.",
                task.id,
                task.assignee_id,
            )
            continue

        message = _plain_task_message(
            heading=f"Task is overdue: {task.title}",
            task=task,
            assigned_by=task.project.owner,
        )
        Notification.objects.create(
            user=task.assignee,
            task=task,
            type=Notification.Type.TASK_OVERDUE,
            message=message,
        )
        email_sent = send_notification_email(
            task.assignee,
            "TaskFlow - Task Overdue",
            message,
            "emails/task_overdue.html",
            _task_email_context(task, assigned_by=task.project.owner, event_label="Task Overdue"),
        )
        created_count += 1
        if email_sent:
            email_sent_count += 1
        else:
            email_failed_count += 1
        logger.info(
            "Created overdue notification for task_id=%s assignee_id=%s email_sent=%s due_date_ist=%s.",
            task.id,
            task.assignee_id,
            email_sent,
            _format_due_date(task.due_date),
        )

    summary = {
        "overdue_found": overdue_count,
        "notifications_created": created_count,
        "duplicates_skipped": skipped_count,
        "emails_sent": email_sent_count,
        "emails_failed": email_failed_count,
    }
    logger.info("Overdue notification scan finished: %s", summary)
    return summary


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
