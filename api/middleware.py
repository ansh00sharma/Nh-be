import logging
import time

from django.conf import settings
from django.db import connection

from api.metrics import record_request


logger = logging.getLogger(__name__)


class RequestTimingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.REQUEST_TIMING_ENABLED:
            return self.get_response(request)

        query_count = 0
        db_duration = 0.0
        slow_queries = []
        slow_sql_threshold = settings.REQUEST_TIMING_SLOW_SQL_THRESHOLD_SECONDS
        request_started_at = time.perf_counter()
        status_code = 500

        def execute_wrapper(execute, sql, params, many, context):
            nonlocal query_count, db_duration

            query_started_at = time.perf_counter()
            try:
                return execute(sql, params, many, context)
            finally:
                query_duration = time.perf_counter() - query_started_at
                query_count += 1
                db_duration += query_duration

                if query_duration >= slow_sql_threshold:
                    slow_queries.append((query_duration, _clean_sql(sql)))

        try:
            with connection.execute_wrapper(execute_wrapper):
                response = self.get_response(request)
                status_code = response.status_code
                return response
        finally:
            total_duration = time.perf_counter() - request_started_at
            logger.warning(
                "[REQUEST TIMING] %s %s status=%s total=%.3fs db=%.3fs queries=%s",
                request.method,
                request.path,
                status_code,
                total_duration,
                db_duration,
                query_count,
            )

            for query_duration, sql in slow_queries:
                logger.warning("[SLOW SQL] duration=%.3fs sql=%s", query_duration, sql)


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path != "/api/metrics/":
            record_request(response.status_code)
        return response


def _clean_sql(sql):
    return " ".join(str(sql).split())[:2000]
