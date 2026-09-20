from django.contrib.auth.models import Group


MANAGER = "manager"
AGENT = "agent"
TASKFLOW_ROLES = (MANAGER, AGENT)
MANAGER_MODULES = ("users", "projects", "tasks")
AGENT_MODULES = ("tasks",)


def get_or_create_role_group(role):
    if role not in TASKFLOW_ROLES:
        raise ValueError(f"Unsupported TaskFlow role: {role}")
    group, _ = Group.objects.get_or_create(name=role)
    return group


def assign_taskflow_role(user, role):
    group = get_or_create_role_group(role)
    user.groups.remove(*Group.objects.filter(name__in=TASKFLOW_ROLES))
    user.groups.add(group)


def get_taskflow_role(user):
    if not user or not user.is_authenticated:
        return None

    role_names = set(user.groups.filter(name__in=TASKFLOW_ROLES).values_list("name", flat=True))
    for role in TASKFLOW_ROLES:
        if role in role_names:
            return role
    return None


def is_manager(user):
    return get_taskflow_role(user) == MANAGER


def is_agent(user):
    return get_taskflow_role(user) == AGENT


def get_allowed_modules(user):
    role = get_taskflow_role(user)
    if role == MANAGER:
        return list(MANAGER_MODULES)
    if role == AGENT:
        return list(AGENT_MODULES)
    return []
