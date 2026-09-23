import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache

from core.observability.decorators import traced_span
from users.querysets import with_taskflow_role


logger = logging.getLogger(__name__)

AUTH_USER_CACHE_PREFIX = "auth:user"
AUTH_USER_CACHE_TTL = getattr(settings, "AUTH_USER_CACHE_TTL", 300)


def auth_user_cache_key(user_id):
    return f"{AUTH_USER_CACHE_PREFIX}:{user_id}"


def get_cached_auth_user(user_id):
    key = auth_user_cache_key(user_id)
    with traced_span("auth.cache.lookup") as span:
        try:
            snapshot = cache.get(key)
        except Exception:
            logger.exception("[AUTH CACHE ERROR] action=get user=%s", user_id)
            span.set_attribute("auth.cache.error", True)
            return None

        hit = snapshot is not None
        span.set_attribute("auth.cache.hit", hit)
        if hit:
            logger.debug("[AUTH CACHE HIT] user=%s", user_id)
            return user_from_snapshot(snapshot)

        logger.debug("[AUTH CACHE MISS] user=%s", user_id)
        return None


def cache_auth_user(user):
    key = auth_user_cache_key(user.pk)
    snapshot = snapshot_auth_user(user)
    with traced_span("auth.cache.populate"):
        try:
            cache.set(key, snapshot, AUTH_USER_CACHE_TTL)
        except Exception:
            logger.exception("[AUTH CACHE ERROR] action=set user=%s", user.pk)


def invalidate_auth_user(user_id):
    if not user_id:
        return

    try:
        cache.delete(auth_user_cache_key(user_id))
        logger.debug("[AUTH CACHE INVALIDATE] user=%s", user_id)
    except Exception:
        logger.exception("[AUTH CACHE ERROR] action=delete user=%s", user_id)


def snapshot_auth_user(user):
    return {
        "id": user.pk,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login,
        "date_joined": user.date_joined,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "taskflow_role": getattr(user, "taskflow_role", None),
    }


def user_from_snapshot(snapshot):
    User = get_user_model()
    user = User(
        id=snapshot["id"],
        email=snapshot["email"],
        first_name=snapshot["first_name"],
        last_name=snapshot["last_name"],
        is_active=snapshot["is_active"],
        is_staff=snapshot["is_staff"],
        is_superuser=snapshot["is_superuser"],
        last_login=snapshot.get("last_login"),
        date_joined=snapshot.get("date_joined"),
        created_at=snapshot.get("created_at"),
        updated_at=snapshot.get("updated_at"),
        password="",
    )
    user._state.adding = False
    user._state.db = "default"
    user.taskflow_role = snapshot.get("taskflow_role")
    if user.taskflow_role:
        user._taskflow_role_cache = user.taskflow_role
    return user


def load_auth_user_from_database(user_model, lookup):
    with traced_span("auth.load_user"):
        user = with_taskflow_role(user_model.objects).get(**lookup)
    cache_auth_user(user)
    return user
