import logging
from hashlib import sha256
from urllib.parse import urlencode

from django.core.cache import cache


logger = logging.getLogger(__name__)

CACHEABLE_READ_METHODS = {"GET"}


def normalize_query_params(query_params):
    normalized_items = []
    for key, values in sorted(query_params.lists()):
        for value in sorted(values):
            normalized_items.append((key, value))
    return urlencode(normalized_items, doseq=True)


def get_response_cache_version(version_key):
    version = cache.get(version_key)
    if version is None:
        version = 1
        cache.add(version_key, version)
    return version


def increment_response_cache_version(version_key):
    if cache.get(version_key) is None:
        cache.add(version_key, 1)
    try:
        cache.incr(version_key)
    except ValueError:
        cache.set(version_key, 2)


def make_user_response_cache_key(
    request,
    namespace,
    *,
    operation=None,
    version=None,
    extra_context=None,
):
    user = request.user
    user_id = getattr(user, "id", None)
    if user_id is None or version is None:
        return None

    query_params = getattr(request, "query_params", request.GET)
    normalized_query = normalize_query_params(query_params)
    signature_parts = [
        f"method={request.method}",
        f"path={request.path}",
        f"namespace={namespace}",
        f"operation={operation or ''}",
        f"user={user_id}",
        f"version={version}",
        f"query={normalized_query}",
    ]

    for key, value in sorted((extra_context or {}).items()):
        signature_parts.append(f"{key}={value}")

    digest = sha256("|".join(signature_parts).encode()).hexdigest()
    operation_segment = f":{operation}" if operation else ""
    return f"api:{namespace}:v{version}{operation_segment}:user:{user_id}:{digest}"


def get_cached_response_data(
    request,
    namespace,
    *,
    log_label,
    operation=None,
    version=None,
    extra_context=None,
):
    if request.method not in CACHEABLE_READ_METHODS:
        return None, None

    cache_key = make_user_response_cache_key(
        request,
        namespace,
        operation=operation,
        version=version,
        extra_context=extra_context,
    )
    if cache_key is None:
        return None, None

    cached_data = cache.get(cache_key)
    user_id = getattr(request.user, "id", None)
    if cached_data is None:
        logger.info("[%s CACHE MISS] user=%s key=%s", log_label, user_id, cache_key)
    else:
        logger.info("[%s CACHE HIT] user=%s key=%s", log_label, user_id, cache_key)
    return cache_key, cached_data


def set_cached_response_data(cache_key, response, ttl_seconds, *, cacheable_statuses=(200,)):
    if not cache_key or response.status_code not in cacheable_statuses:
        return False

    cache.set(cache_key, response.data, ttl_seconds)
    return True
