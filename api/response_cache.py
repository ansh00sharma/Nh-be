import json
import logging
import time
from hashlib import sha256
from urllib.parse import urlencode

from django.core.cache import cache

from api.profiling import add_profile_time, set_profile_cache_hit


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
    ttl_seconds=None,
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

    cache_start = time.perf_counter()
    cached_data = cache.get(cache_key)
    cache_get_elapsed = time.perf_counter() - cache_start
    cache_get_ms = cache_get_elapsed * 1000
    user_id = getattr(request.user, "id", None)
    hit = cached_data is not None
    cached_type = get_cached_payload_type(cached_data)
    cached_size = get_approximate_payload_size(cached_data)
    add_profile_time("cache_get_time", cache_get_elapsed)
    set_profile_cache_hit(hit)
    logger.info(
        "[%s CACHE CHECK] user=%s version=%s key=%s redis_get_ms=%.2f hit=%s "
        "cached_type=%s cached_size=%s project_cache_ttl=%s",
        log_label,
        user_id,
        version,
        cache_key,
        cache_get_ms,
        str(hit).lower(),
        cached_type,
        cached_size,
        ttl_seconds,
    )
    if cached_data is None:
        logger.info(
            "[%s CACHE MISS] user=%s key=%s redis_get_ms=%.2f "
            "cached_type=%s cached_size=%s project_cache_ttl=%s",
            log_label,
            user_id,
            cache_key,
            cache_get_ms,
            cached_type,
            cached_size,
            ttl_seconds,
        )
    else:
        logger.info(
            "[%s CACHE HIT] user=%s key=%s redis_get_ms=%.2f "
            "cached_type=%s cached_size=%s project_cache_ttl=%s",
            log_label,
            user_id,
            cache_key,
            cache_get_ms,
            cached_type,
            cached_size,
            ttl_seconds,
        )
    return cache_key, cached_data


def set_cached_response_data(
    cache_key,
    response,
    ttl_seconds,
    *,
    cacheable_statuses=(200,),
    log_label=None,
    verify=False,
):
    if not cache_key or response.status_code not in cacheable_statuses:
        return False

    cache_start = time.perf_counter()
    set_result = cache.set(cache_key, response.data, ttl_seconds)
    cache_set_elapsed = time.perf_counter() - cache_start
    add_profile_time("cache_set_time", cache_set_elapsed)

    success = set_result is not False
    verified = None
    if verify and success:
        verified = cache.get(cache_key) is not None

    if log_label:
        logger.info(
            "[%s CACHE SET] success=%s verified=%s ttl=%s "
            "cache_set_ms=%.2f cached_type=%s cached_size=%s",
            log_label,
            str(success).lower(),
            "skipped" if verified is None else str(verified).lower(),
            ttl_seconds,
            cache_set_elapsed * 1000,
            get_cached_payload_type(response.data),
            get_approximate_payload_size(response.data),
        )

    return success


def get_cached_payload_type(value):
    if value is None:
        return "none"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def get_approximate_payload_size(value):
    if value is None:
        return 0
    try:
        return len(json.dumps(value, default=str, separators=(",", ":")).encode())
    except (TypeError, ValueError):
        return len(str(value).encode())
