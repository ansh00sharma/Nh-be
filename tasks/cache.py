from hashlib import sha256
from urllib.parse import urlencode

from django.core.cache import cache


TASK_LIST_CACHE_TTL_SECONDS = 300


def task_list_version_key(user_id):
    return f"tasks:list:user:{user_id}:version"


def get_task_list_cache_version(user_id):
    key = task_list_version_key(user_id)
    version = cache.get(key)
    if version is None:
        version = 1
        cache.add(key, version)
    return version


def increment_task_list_cache_version(user_id):
    if not user_id:
        return

    key = task_list_version_key(user_id)
    if cache.get(key) is None:
        cache.add(key, 1)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2)


def increment_task_list_cache_versions(*user_ids):
    for user_id in set(user_ids):
        increment_task_list_cache_version(user_id)


def make_task_list_cache_key(request):
    query_items = []
    for key, values in sorted(request.query_params.lists()):
        for value in values:
            query_items.append((key, value))

    query_string = urlencode(query_items, doseq=True)
    version = get_task_list_cache_version(request.user.id)
    raw_key = f"user={request.user.id}:version={version}:query={query_string}"
    digest = sha256(raw_key.encode()).hexdigest()
    return f"tasks:list:{digest}"
