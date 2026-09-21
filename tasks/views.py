from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from api.responses import success_response
from tasks.cache import (
    TASK_LIST_CACHE_TTL_SECONDS,
    increment_task_list_cache_versions,
    make_task_list_cache_key,
)
from tasks.querysets import get_task_queryset_for_user
from tasks.serializers import TaskSerializer
from notifications.tasks import (
    create_task_created_notification,
    create_task_reassigned_notification,
    create_task_status_changed_notification,
)
from users.roles import get_admin_user_ids, is_admin, is_agent, is_manager


class TaskViewSet(ModelViewSet):
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated]
    agent_restricted_update_fields = {
        "assignee",
        "project",
        "title",
        "description",
        "due_date",
    }

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not (is_admin(request.user) or is_manager(request.user) or is_agent(request.user)):
            raise PermissionDenied("An admin, manager, or agent role is required.")

    def get_queryset(self):
        queryset = get_task_queryset_for_user(self.request.user)

        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)

        assignee_id = self.request.query_params.get("assignee")
        if assignee_id:
            if not assignee_id.isdigit():
                return queryset.none()
            queryset = queryset.filter(assignee_id=assignee_id)

        project_id = self.request.query_params.get("project")
        if project_id:
            if not project_id.isdigit():
                return queryset.none()
            queryset = queryset.filter(project_id=project_id)

        due_date_from = _parse_due_date_filter(
            self.request.query_params.get("due_date_from"),
            end_of_day=False,
        )
        if due_date_from:
            queryset = queryset.filter(due_date__gte=due_date_from)

        due_date_to = _parse_due_date_filter(
            self.request.query_params.get("due_date_to"),
            end_of_day=True,
        )
        if due_date_to:
            queryset = queryset.filter(due_date__lte=due_date_to)

        return queryset

    def create(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_manager(request.user)):
            raise PermissionDenied("Only admins and managers can create tasks.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if is_agent(request.user):
            restricted_fields = sorted(
                field for field in self.agent_restricted_update_fields if field in request.data
            )
            if restricted_fields:
                raise ValidationError(
                    {
                        "detail": (
                            "Agents can only update task status. Restricted fields: "
                            + ", ".join(restricted_fields)
                        )
                    }
                )
        return super().update(request, *args, **kwargs)

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
        increment_task_list_cache_versions(
            task.project.owner_id,
            task.assignee_id,
            *get_admin_user_ids(),
        )
        if task.assignee_id:
            create_task_created_notification.delay(
                task.id,
                task.assignee_id,
                self.request.user.id,
            )

    def perform_update(self, serializer):
        previous_project_owner_id = serializer.instance.project.owner_id
        previous_assignee_id = serializer.instance.assignee_id
        previous_status = serializer.instance.status
        task = serializer.save()
        increment_task_list_cache_versions(
            previous_project_owner_id,
            task.project.owner_id,
            previous_assignee_id,
            task.assignee_id,
            *get_admin_user_ids(),
        )
        if task.assignee_id and task.assignee_id != previous_assignee_id:
            create_task_reassigned_notification.delay(
                task.id,
                task.assignee_id,
                self.request.user.id,
            )
        if task.status != previous_status:
            create_task_status_changed_notification.delay(
                task.id,
                previous_status,
                task.status,
                self.request.user.id,
            )

    def perform_destroy(self, instance):
        owner_id = instance.project.owner_id
        assignee_id = instance.assignee_id
        instance.delete()
        increment_task_list_cache_versions(owner_id, assignee_id, *get_admin_user_ids())

    def destroy(self, request, *args, **kwargs):
        if not (is_admin(request.user) or is_manager(request.user)):
            raise PermissionDenied("Only admins and managers can delete tasks.")
        instance = self.get_object()
        self.perform_destroy(instance)
        return success_response("Task deleted successfully", None)


def _parse_due_date_filter(value, end_of_day):
    if not value:
        return None

    parsed_value = parse_datetime(value)
    if parsed_value is None:
        parsed_date = parse_date(value)
        if parsed_date is None:
            return None
        time_value = "23:59:59.999999" if end_of_day else "00:00:00"
        parsed_value = parse_datetime(f"{parsed_date.isoformat()}T{time_value}")

    if timezone.is_naive(parsed_value):
        return timezone.make_aware(parsed_value, timezone.get_current_timezone())
    return parsed_value
