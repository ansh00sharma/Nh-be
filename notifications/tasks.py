from celery import shared_task
from django.utils import timezone

from notifications.models import Notification
from tasks.models import Task


@shared_task
def create_task_reassigned_notification(task_id, assignee_id):
    task = Task.objects.select_related("assignee").get(id=task_id)
    if task.assignee_id != assignee_id or assignee_id is None:
        return

    Notification.objects.create(
        user_id=assignee_id,
        task=task,
        type=Notification.Type.TASK_REASSIGNED,
        message=f"You have been assigned to task: {task.title}",
    )


@shared_task
def create_overdue_task_notifications():
    overdue_tasks = Task.objects.filter(
        due_date__lt=timezone.now(),
        assignee__isnull=False,
    ).exclude(status=Task.Status.DONE)

    created_count = 0
    for task in overdue_tasks:
        already_notified = Notification.objects.filter(
            task=task,
            type=Notification.Type.TASK_OVERDUE,
        ).exists()
        if already_notified:
            continue

        Notification.objects.create(
            user=task.assignee,
            task=task,
            type=Notification.Type.TASK_OVERDUE,
            message=f"Task is overdue: {task.title}",
        )
        created_count += 1

    return created_count
