from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from users.auth_cache import invalidate_auth_user
from users.roles import TASKFLOW_ROLES


User = get_user_model()


@receiver(post_save, sender=User, dispatch_uid="invalidate_auth_user_on_save")
def invalidate_user_on_save(sender, instance, **kwargs):
    invalidate_auth_user(instance.pk)


@receiver(post_delete, sender=User, dispatch_uid="invalidate_auth_user_on_delete")
def invalidate_user_on_delete(sender, instance, **kwargs):
    invalidate_auth_user(instance.pk)


@receiver(m2m_changed, sender=User.groups.through, dispatch_uid="invalidate_auth_user_on_groups")
def invalidate_user_on_group_change(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in {"post_add", "post_remove", "post_clear", "pre_clear"}:
        return

    if reverse:
        user_ids = pk_set or instance.user_set.values_list("id", flat=True)
        for user_id in user_ids:
            invalidate_auth_user(user_id)
        return

    invalidate_auth_user(instance.pk)


@receiver(pre_save, sender=Group, dispatch_uid="invalidate_auth_users_before_group_rename")
def invalidate_group_users_before_save(sender, instance, **kwargs):
    if not instance.pk:
        return
    if Group.objects.filter(pk=instance.pk, name__in=TASKFLOW_ROLES).exists():
        for user_id in instance.user_set.values_list("id", flat=True):
            invalidate_auth_user(user_id)


@receiver(post_save, sender=Group, dispatch_uid="invalidate_auth_users_after_group_save")
def invalidate_group_users_after_save(sender, instance, **kwargs):
    if instance.name not in TASKFLOW_ROLES:
        return
    for user_id in instance.user_set.values_list("id", flat=True):
        invalidate_auth_user(user_id)


@receiver(pre_delete, sender=Group, dispatch_uid="invalidate_auth_users_before_group_delete")
def invalidate_group_users_before_delete(sender, instance, **kwargs):
    for user_id in instance.user_set.values_list("id", flat=True):
        invalidate_auth_user(user_id)
