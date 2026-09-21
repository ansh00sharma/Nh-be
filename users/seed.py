from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from projects.models import Project
from users.roles import ADMIN, AGENT, MANAGER, TASKFLOW_ROLES


FINAL_SEED_USERS = (
    {
        "email": "admin@taskflow.in",
        "password": "aisufhasiw@eq2weh3as",
        "first_name": "TaskFlow",
        "last_name": "Admin",
        "role": ADMIN,
    },
    {
        "email": "sharma999ansh@gmail.com",
        "password": "welcome",
        "first_name": "Ansh",
        "last_name": "Sharma",
        "role": MANAGER,
    },
    {
        "email": "ansh.sharma.tenant@gmail.com",
        "password": "welcome",
        "first_name": "Ansh",
        "last_name": "Tenant",
        "role": AGENT,
    },
)

FINAL_SEED_PROJECTS = (
    {"name": "Fintech", "owner_email": "admin@taskflow.in"},
    {"name": "Sales Marketing", "owner_email": "sharma999ansh@gmail.com"},
    {"name": "HR management", "owner_email": "sharma999ansh@gmail.com"},
)


def ensure_final_seed_data():
    User = get_user_model()
    groups = {role: Group.objects.get_or_create(name=role)[0] for role in TASKFLOW_ROLES}

    users_by_email = {}
    for seed_user in FINAL_SEED_USERS:
        user, _ = User.objects.update_or_create(
            email=seed_user["email"],
            defaults={
                "first_name": seed_user["first_name"],
                "last_name": seed_user["last_name"],
                "is_active": True,
                "is_staff": seed_user["role"] == ADMIN,
                "is_superuser": False,
            },
        )
        user.set_password(seed_user["password"])
        user.save(update_fields=["password"])
        user.groups.remove(*Group.objects.filter(name__in=TASKFLOW_ROLES))
        user.groups.add(groups[seed_user["role"]])
        users_by_email[seed_user["email"]] = user

    for seed_project in FINAL_SEED_PROJECTS:
        Project.objects.get_or_create(
            name=seed_project["name"],
            owner=users_by_email[seed_project["owner_email"]],
            defaults={"description": ""},
        )

    return users_by_email
