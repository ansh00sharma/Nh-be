from django.contrib.auth import get_user_model
from django.db.models import Case, CharField, IntegerField, OuterRef, Subquery, Value, When

from users.roles import ADMIN, AGENT, MANAGER, TASKFLOW_ROLES


User = get_user_model()
ROLE_ORDER = {
    ADMIN: 0,
    MANAGER: 1,
    AGENT: 2,
}


def with_taskflow_role(queryset=None):
    queryset = queryset if queryset is not None else User.objects.all()
    user_groups = User.groups.through.objects.filter(
        user_id=OuterRef("pk"),
        group__name__in=TASKFLOW_ROLES,
    ).annotate(
        role_priority=Case(
            *[
                When(group__name=role, then=Value(priority))
                for role, priority in ROLE_ORDER.items()
            ],
            default=Value(len(ROLE_ORDER)),
            output_field=IntegerField(),
        )
    )

    return queryset.annotate(
        taskflow_role=Subquery(
            user_groups.order_by("role_priority", "group__name").values("group__name")[:1],
            output_field=CharField(),
        )
    )
