import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from secrets import token_hex


logger = logging.getLogger(__name__)

_current_profile = ContextVar("request_profile", default=None)


class QueryTimingWrapper:
    def __init__(self, slow_query_threshold_seconds=0.100):
        self.query_count = 0
        self.total_db_time = 0.0
        self.slow_query_threshold_seconds = slow_query_threshold_seconds
        self.slow_queries = []

    def __call__(self, execute, sql, params, many, context):
        start = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            elapsed = time.perf_counter() - start
            self.query_count += 1
            self.total_db_time += elapsed

            if elapsed >= self.slow_query_threshold_seconds:
                self.slow_queries.append(
                    {
                        "duration": elapsed,
                        "sql": clean_sql(sql),
                    }
                )


@dataclass
class RequestProfile:
    method: str
    path: str
    request_id: str = field(default_factory=lambda: token_hex(3))
    started_at: float = field(default_factory=time.perf_counter)
    status_code: int = 500
    auth_time: float = 0.0
    permission_time: float = 0.0
    cache_get_time: float = 0.0
    cache_set_time: float = 0.0
    service_time: float = 0.0
    serialization_time: float = 0.0
    response_render_time: float = 0.0
    cache_hit: bool = False
    query_tracker: QueryTimingWrapper | None = None

    def elapsed_ms(self):
        return (time.perf_counter() - self.started_at) * 1000


def clean_sql(sql):
    return " ".join(str(sql).split())[:2000]


def get_current_profile():
    return _current_profile.get()


def set_current_profile(profile):
    return _current_profile.set(profile)


def reset_current_profile(token):
    _current_profile.reset(token)


def add_profile_time(field_name, elapsed_seconds):
    profile = get_current_profile()
    if profile is not None:
        setattr(profile, field_name, getattr(profile, field_name) + elapsed_seconds)


def set_profile_cache_hit(hit):
    profile = get_current_profile()
    if profile is not None:
        profile.cache_hit = hit


@contextmanager
def profile_timer(field_name):
    start = time.perf_counter()
    try:
        yield
    finally:
        add_profile_time(field_name, time.perf_counter() - start)


def milliseconds(seconds):
    return seconds * 1000


def log_request_profile(profile):
    query_tracker = profile.query_tracker
    db_time = query_tracker.total_db_time if query_tracker else 0.0
    query_count = query_tracker.query_count if query_tracker else 0

    logger.warning(
        "[REQUEST PROFILE] request_id=%s method=%s path=%s status=%s "
        "total_ms=%.1f auth_ms=%.1f permission_ms=%.1f cache_get_ms=%.2f "
        "cache_set_ms=%.2f cache_hit=%s service_ms=%.1f db_ms=%.1f "
        "db_queries=%s serialization_ms=%.1f render_ms=%.1f",
        profile.request_id,
        profile.method,
        profile.path,
        profile.status_code,
        profile.elapsed_ms(),
        milliseconds(profile.auth_time),
        milliseconds(profile.permission_time),
        milliseconds(profile.cache_get_time),
        milliseconds(profile.cache_set_time),
        str(profile.cache_hit).lower(),
        milliseconds(profile.service_time),
        milliseconds(db_time),
        query_count,
        milliseconds(profile.serialization_time),
        milliseconds(profile.response_render_time),
    )

    for slow_query in query_tracker.slow_queries if query_tracker else ():
        logger.warning(
            "[SLOW SQL] request_id=%s duration_ms=%.1f sql=%s",
            profile.request_id,
            milliseconds(slow_query["duration"]),
            slow_query["sql"],
        )
