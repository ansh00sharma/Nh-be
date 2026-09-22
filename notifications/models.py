from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Type(models.TextChoices):
        TASK_CREATED = "task_created", "Task created"
        TASK_OVERDUE = "task_overdue", "Task overdue"
        TASK_REASSIGNED = "task_reassigned", "Task reassigned"
        TASK_STATUS_CHANGED = "task_status_changed", "Task status changed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    task = models.ForeignKey(
        "tasks.Task",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    message = models.TextField()
    is_read_by_system = models.BooleanField(default=False)
    is_send = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type}: {self.message}"
