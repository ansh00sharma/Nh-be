from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from tasks.cache import (
    TASK_LIST_CACHE_TTL_SECONDS,
    increment_task_list_cache_version,
    make_task_list_cache_key,
)
from tasks.models import Task
from tasks.serializers import TaskSerializer
from notifications.tasks import create_task_reassigned_notification


class TaskViewSet(ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Task.objects.filter(project__owner=self.request.user)

    def list(self, request, *args, **kwargs):
        cache_key = make_task_list_cache_key(request)
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, TASK_LIST_CACHE_TTL_SECONDS)
        return response

    def perform_create(self, serializer):
        task = serializer.save()
        increment_task_list_cache_version(task.project.owner_id)

    def perform_update(self, serializer):
        previous_assignee_id = serializer.instance.assignee_id
        task = serializer.save()
        increment_task_list_cache_version(task.project.owner_id)
        if task.assignee_id and task.assignee_id != previous_assignee_id:
            create_task_reassigned_notification.delay(task.id, task.assignee_id)

    def perform_destroy(self, instance):
        owner_id = instance.project.owner_id
        instance.delete()
        increment_task_list_cache_version(owner_id)
