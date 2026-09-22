import logging
import time

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.profiling import get_current_profile, milliseconds, profile_timer
from api.responses import success_response
from api.viewsets import ProfiledModelViewSet
from projects.cache import (
    get_cached_project_list_response,
    increment_project_list_cache_version,
    set_cached_project_list_response,
)
from projects.querysets import get_project_queryset_for_user
from projects.serializers import ProjectSerializer
from tasks.cache import increment_task_list_cache_versions
from users.roles import get_admin_user_ids, is_admin_or_manager


logger = logging.getLogger("api.profiling")


class ProjectViewSet(ProfiledModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        with profile_timer("permission_time"):
            if not is_admin_or_manager(request.user):
                raise PermissionDenied("Only admins and managers can access projects.")

    def get_queryset(self):
        return get_project_queryset_for_user(self.request.user)

    def list(self, request, *args, **kwargs):
        view_started_at = time.perf_counter()
        profile = get_current_profile()
        request_id = profile.request_id if profile else "-"
        cache_get_before = profile.cache_get_time if profile else 0.0

        cache_key, cached_data = get_cached_project_list_response(request)
        profile = get_current_profile()
        cache_get_after = profile.cache_get_time if profile else cache_get_before
        cache_get_ms = milliseconds(cache_get_after - cache_get_before)

        if cached_data is not None:
            log_project_profile(
                request_id=request_id,
                user_id=request.user.pk,
                cache_hit=True,
                cache_get_ms=cache_get_ms,
                queryset_ms=0.0,
                pagination_ms=0.0,
                serialization_ms=0.0,
                cache_set_ms=0.0,
                total_view_ms=milliseconds(time.perf_counter() - view_started_at),
            )
            return Response(cached_data)

        with profile_timer("service_time"):
            queryset_started_at = time.perf_counter()
            queryset = self.filter_queryset(self.get_queryset())
            queryset_ms = milliseconds(time.perf_counter() - queryset_started_at)

            pagination_started_at = time.perf_counter()
            page = self.paginate_queryset(queryset)
            pagination_ms = milliseconds(time.perf_counter() - pagination_started_at)

        serialized_items = page if page is not None else queryset
        serializer = self.get_serializer(serialized_items, many=True)
        serialization_started_at = time.perf_counter()
        with profile_timer("serialization_time"):
            data = serializer.data
        serialization_ms = milliseconds(time.perf_counter() - serialization_started_at)

        if page is not None:
            response = self.get_paginated_response(data)
        else:
            response = Response(data)

        profile = get_current_profile()
        cache_set_before = profile.cache_set_time if profile else 0.0
        set_cached_project_list_response(cache_key, response)
        profile = get_current_profile()
        cache_set_after = profile.cache_set_time if profile else cache_set_before
        cache_set_ms = milliseconds(cache_set_after - cache_set_before)

        log_project_profile(
            request_id=request_id,
            user_id=request.user.pk,
            cache_hit=False,
            cache_get_ms=cache_get_ms,
            queryset_ms=queryset_ms,
            pagination_ms=pagination_ms,
            serialization_ms=serialization_ms,
            cache_set_ms=cache_set_ms,
            total_view_ms=milliseconds(time.perf_counter() - view_started_at),
        )
        return response

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        increment_project_list_cache_version()

    def perform_update(self, serializer):
        serializer.save()
        increment_project_list_cache_version()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        affected_user_ids = [
            instance.owner_id,
            *instance.tasks.values_list("assignee_id", flat=True),
            *get_admin_user_ids(),
        ]
        self.perform_destroy(instance)
        increment_project_list_cache_version()
        increment_task_list_cache_versions(*affected_user_ids)
        return success_response("Project deleted successfully", None)


def log_project_profile(
    *,
    request_id,
    user_id,
    cache_hit,
    cache_get_ms,
    queryset_ms,
    pagination_ms,
    serialization_ms,
    cache_set_ms,
    total_view_ms,
):
    logger.warning(
        "[PROJECT PROFILE] request_id=%s user=%s cache_hit=%s cache_get_ms=%.2f "
        "queryset_ms=%.1f pagination_ms=%.1f serialization_ms=%.1f "
        "cache_set_ms=%.2f total_view_ms=%.1f",
        request_id,
        user_id,
        str(cache_hit).lower(),
        cache_get_ms,
        queryset_ms,
        pagination_ms,
        serialization_ms,
        cache_set_ms,
        total_view_ms,
    )
