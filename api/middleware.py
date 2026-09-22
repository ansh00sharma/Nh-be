import time

from django.conf import settings
from django.db import connection

from api.metrics import record_request
from api.profiling import (
    QueryTimingWrapper,
    RequestProfile,
    add_profile_time,
    log_request_profile,
    reset_current_profile,
    set_current_profile,
)


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.REQUEST_TIMING_ENABLED:
            return self.get_response(request)

        profile = RequestProfile(method=request.method, path=request.path)
        profile.query_tracker = QueryTimingWrapper(
            settings.REQUEST_TIMING_SLOW_SQL_THRESHOLD_SECONDS
        )
        profile_token = set_current_profile(profile)

        try:
            with connection.execute_wrapper(profile.query_tracker):
                response = self.get_response(request)
                profile.status_code = response.status_code
                return response
        finally:
            log_request_profile(profile)
            reset_current_profile(profile_token)

    def process_template_response(self, request, response):
        if not settings.REQUEST_TIMING_ENABLED:
            return response
        if not hasattr(response, "render"):
            return response

        original_render = response.render

        def profiled_render(*args, **kwargs):
            render_started_at = time.perf_counter()
            try:
                return original_render(*args, **kwargs)
            finally:
                add_profile_time(
                    "response_render_time",
                    time.perf_counter() - render_started_at,
                )

        response.render = profiled_render
        return response


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path != "/api/metrics/":
            record_request(response.status_code)
        return response
