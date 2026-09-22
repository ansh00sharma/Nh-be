from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from api.responses import success_response
from projects.cache import (
    get_cached_project_list_response,
    increment_project_list_cache_version,
    set_cached_project_list_response,
)
from projects.querysets import get_project_queryset_for_user
from projects.serializers import ProjectSerializer
from tasks.cache import increment_task_list_cache_versions
from users.roles import get_admin_user_ids, is_admin_or_manager


class ProjectViewSet(ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not is_admin_or_manager(request.user):
            raise PermissionDenied("Only admins and managers can access projects.")

    def get_queryset(self):
        return get_project_queryset_for_user(self.request.user)

    def list(self, request, *args, **kwargs):
        cache_key, cached_data = get_cached_project_list_response(request)
        if cached_data is not None:
            return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        set_cached_project_list_response(cache_key, response)
        return response

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        increment_project_list_cache_version()

    def perform_update(self, serializer):
        serializer.save()
        increment_project_list_cache_version()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        affected_user_ids = [
            instance.owner_id,
            *instance.tasks.values_list("assignee_id", flat=True),
            *get_admin_user_ids(),
        ]
        self.perform_destroy(instance)
        increment_project_list_cache_version()
        increment_task_list_cache_versions(*affected_user_ids)
        return success_response("Project deleted successfully", None)
