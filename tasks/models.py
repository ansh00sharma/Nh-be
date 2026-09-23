from django.conf import settings
from django.db import models
from django.db.models import Q


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "Todo"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TODO,
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_tasks",
        null=True,
        blank=True,
    )
    due_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["assignee", "-created_at"], name="task_assignee_created_idx"),
            models.Index(fields=["project", "-created_at"], name="task_project_created_idx"),
            models.Index(fields=["status", "-created_at"], name="task_status_created_idx"),
            models.Index(
                fields=["assignee", "status", "-created_at"],
                name="task_assignee_status_idx",
            ),
            models.Index(
                fields=["project", "status", "-created_at"],
                name="task_project_status_idx",
            ),
            models.Index(fields=["due_date", "-created_at"], name="task_due_created_idx"),
            models.Index(
                fields=["due_date"],
                name="task_due_active_idx",
                condition=Q(assignee__isnull=False) & ~Q(status="done"),
            ),
        ]

    def __str__(self):
        return self.title
