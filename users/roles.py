from django.contrib.auth.models import Group


ADMIN = "admin"
MANAGER = "manager"
AGENT = "agent"
TASKFLOW_ROLES = (ADMIN, MANAGER, AGENT)
ADMIN_MODULES = ("dashboard", "users", "projects", "tasks")
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
    if hasattr(user, "_taskflow_role_cache"):
        delattr(user, "_taskflow_role_cache")


def get_taskflow_role(user):
    if not user or not user.is_authenticated:
        return None

    annotated_role = getattr(user, "taskflow_role", None)
    if annotated_role in TASKFLOW_ROLES:
        user._taskflow_role_cache = annotated_role
        return annotated_role

    if hasattr(user, "_taskflow_role_cache"):
        return user._taskflow_role_cache

    role_names = set(user.groups.filter(name__in=TASKFLOW_ROLES).values_list("name", flat=True))
    for role in TASKFLOW_ROLES:
        if role in role_names:
            user._taskflow_role_cache = role
            return role
    user._taskflow_role_cache = None
    return None


def is_manager(user):
    return get_taskflow_role(user) == MANAGER


def is_admin(user):
    return get_taskflow_role(user) == ADMIN


def is_agent(user):
    return get_taskflow_role(user) == AGENT


def is_admin_or_manager(user):
    return is_admin(user) or is_manager(user)


def get_allowed_modules(user):
    role = get_taskflow_role(user)
    return get_allowed_modules_for_role(role)


def get_allowed_modules_for_role(role):
    if role == ADMIN:
        return list(ADMIN_MODULES)
    if role == MANAGER:
        return list(MANAGER_MODULES)
    if role == AGENT:
        return list(AGENT_MODULES)
    return []


def get_admin_user_ids():
    return Group.objects.filter(name=ADMIN).values_list("user__id", flat=True)
