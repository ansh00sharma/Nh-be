from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from api.responses import success_response
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

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        affected_user_ids = [
            instance.owner_id,
            *instance.tasks.values_list("assignee_id", flat=True),
            *get_admin_user_ids(),
        ]
        self.perform_destroy(instance)
        increment_task_list_cache_versions(*affected_user_ids)
        return success_response("Project deleted successfully", None)
