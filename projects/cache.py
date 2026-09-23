from django.conf import settings

from api.response_cache import (
    get_cached_response_data,
    get_response_cache_version,
    increment_response_cache_version,
    make_user_response_cache_key,
    set_cached_response_data,
)

from users.roles import get_taskflow_role
from core.observability.decorators import traced


PROJECT_CACHE_NAMESPACE = "projects"
PROJECT_LIST_CACHE_OPERATION = "list"
PROJECT_CACHE_VERSION_KEY = "projects:version"


@traced("project.cache.get_version")
def get_project_cache_version():
    return get_response_cache_version(PROJECT_CACHE_VERSION_KEY)


@traced("project.cache.increment_list_version")
def increment_project_list_cache_version():
    increment_response_cache_version(PROJECT_CACHE_VERSION_KEY)


def get_project_list_cache_context(request):
    return {"role": get_taskflow_role(request.user) or "none"}


def make_project_list_cache_key(request):
    return make_user_response_cache_key(
        request,
        PROJECT_CACHE_NAMESPACE,
        operation=PROJECT_LIST_CACHE_OPERATION,
        version=get_project_cache_version(),
        extra_context=get_project_list_cache_context(request),
    )


@traced("project.cache.get_list_response")
def get_cached_project_list_response(request):
    return get_cached_response_data(
        request,
        PROJECT_CACHE_NAMESPACE,
        log_label="PROJECT",
        operation=PROJECT_LIST_CACHE_OPERATION,
        version=get_project_cache_version(),
        ttl_seconds=settings.PROJECT_LIST_CACHE_TTL,
        extra_context=get_project_list_cache_context(request),
    )


@traced("project.cache.set_list_response")
def set_cached_project_list_response(cache_key, response):
    return set_cached_response_data(
        cache_key,
        response,
        settings.PROJECT_LIST_CACHE_TTL,
        log_label="PROJECT",
        verify=settings.REQUEST_TIMING_ENABLED,
    )
