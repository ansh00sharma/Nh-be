from tasks.models import Task
from users.roles import is_admin, is_agent, is_manager


def get_task_queryset_for_user(user):
    if is_admin(user):
        queryset = Task.objects.all()
    elif is_manager(user):
        queryset = Task.objects.filter(project__owner=user)
    elif is_agent(user):
        queryset = Task.objects.filter(assignee=user)
    else:
        queryset = Task.objects.none()

    return queryset.select_related("project", "project__owner", "assignee")
