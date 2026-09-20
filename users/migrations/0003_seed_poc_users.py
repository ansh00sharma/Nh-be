from django.contrib.auth.hashers import make_password
from django.db import migrations


SEED_PASSWORD = "strong-password-123"
TASKFLOW_ROLES = ("manager", "agent")
SEED_USERS = (
    {
        "email": "manager1@example.com",
        "first_name": "Manager",
        "last_name": "One",
        "role": "manager",
    },
    {
        "email": "agent1@example.com",
        "first_name": "Agent",
        "last_name": "One",
        "role": "agent",
    },
)


def seed_poc_users(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    User = apps.get_model("users", "User")

    groups = {}
    for role in TASKFLOW_ROLES:
        group, _ = Group.objects.get_or_create(name=role)
        groups[role] = group

    for seed_user in SEED_USERS:
        user, _ = User.objects.update_or_create(
            email=seed_user["email"],
            defaults={
                "first_name": seed_user["first_name"],
                "last_name": seed_user["last_name"],
                "is_active": True,
                "is_staff": False,
                "is_superuser": False,
                "password": make_password(SEED_PASSWORD),
            },
        )
        user.groups.remove(*Group.objects.filter(name__in=TASKFLOW_ROLES))
        user.groups.add(groups[seed_user["role"]])


def unseed_poc_users(apps, schema_editor):
    User = apps.get_model("users", "User")
    User.objects.filter(email__in=[user["email"] for user in SEED_USERS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_user_groups_user_user_permissions_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_poc_users, unseed_poc_users),
    ]
