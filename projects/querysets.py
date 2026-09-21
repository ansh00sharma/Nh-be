from projects.models import Project
from users.roles import is_admin, is_manager


def get_project_queryset_for_user(user):
    if is_admin(user):
        return Project.objects.all()
    if is_manager(user):
        return Project.objects.filter(owner=user)
    return Project.objects.none()
