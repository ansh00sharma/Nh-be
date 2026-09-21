from django.contrib.auth.hashers import make_password
from django.db import migrations


TASKFLOW_ROLES = ("admin", "manager", "agent")
OBSOLETE_SEED_EMAILS = ("manager1@example.com", "agent1@example.com")
FINAL_SEED_USERS = (
    {
        "email": "admin@taskflow.in",
        "password": "aisufhasiw@eq2weh3as",
        "first_name": "TaskFlow",
        "last_name": "Admin",
        "role": "admin",
        "is_staff": True,
    },
    {
        "email": "sharma999ansh@gmail.com",
        "password": "welcome",
        "first_name": "Manager",
        "last_name": "Ansh",
        "role": "manager",
        "is_staff": False,
    },
    {
        "email": "ansh.sharma.tenant@gmail.com",
        "password": "welcome",
        "first_name": "Agent",
        "last_name": "Ansh",
        "role": "agent",
        "is_staff": False,
    },
)
FINAL_SEED_PROJECTS = (
    {"name": "Fintech", "owner_email": "admin@taskflow.in"},
    {"name": "Sales Marketing", "owner_email": "sharma999ansh@gmail.com"},
    {"name": "HR management", "owner_email": "sharma999ansh@gmail.com"},
)


def seed_final_taskflow_data(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Project = apps.get_model("projects", "Project")
    Task = apps.get_model("tasks", "Task")
    User = apps.get_model("users", "User")

    groups = {}
    for role in TASKFLOW_ROLES:
        groups[role], _ = Group.objects.get_or_create(name=role)

    for email in OBSOLETE_SEED_EMAILS:
        user = User.objects.filter(email=email).first()
        if not user:
            continue
        has_related_data = (
            Project.objects.filter(owner_id=user.id).exists()
            or Task.objects.filter(assignee_id=user.id).exists()
        )
        if not has_related_data:
            user.delete()

    users_by_email = {}
    for seed_user in FINAL_SEED_USERS:
        user, _ = User.objects.update_or_create(
            email=seed_user["email"],
            defaults={
                "first_name": seed_user["first_name"],
                "last_name": seed_user["last_name"],
                "is_active": True,
                "is_staff": seed_user["is_staff"],
                "is_superuser": False,
                "password": make_password(seed_user["password"]),
            },
        )
        user.groups.remove(*Group.objects.filter(name__in=TASKFLOW_ROLES))
        user.groups.add(groups[seed_user["role"]])
        users_by_email[seed_user["email"]] = user

    for seed_project in FINAL_SEED_PROJECTS:
        Project.objects.get_or_create(
            name=seed_project["name"],
            owner=users_by_email[seed_project["owner_email"]],
            defaults={"description": ""},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
        ("tasks", "0001_initial"),
        ("users", "0003_seed_poc_users"),
    ]

    operations = [
        migrations.RunPython(seed_final_taskflow_data, migrations.RunPython.noop),
    ]
