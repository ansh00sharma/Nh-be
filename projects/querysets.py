from projects.models import Project
from users.roles import ADMIN, MANAGER, get_taskflow_role


PROJECT_SERIALIZED_FIELDS = (
    "id",
    "name",
    "description",
    "owner_id",
    "created_at",
    "updated_at",
)


def get_project_queryset_for_user(user):
    role = get_taskflow_role(user)
    queryset = Project.objects.only(*PROJECT_SERIALIZED_FIELDS)

    if role == ADMIN:
        return queryset
    if role == MANAGER:
        return queryset.filter(owner_id=user.id)
    return Project.objects.none()
