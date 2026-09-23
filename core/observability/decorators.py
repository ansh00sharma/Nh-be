from __future__ import annotations

import inspect
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode


def _default_span_name(func: Callable[..., Any]) -> str:
    module = getattr(func, "__module__", "")
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", "call"))
    return f"{module}.{qualname}" if module else qualname


def _set_function_attributes(span, func: Callable[..., Any]) -> None:
    span.set_attribute("code.namespace", getattr(func, "__module__", ""))
    span.set_attribute("code.function", getattr(func, "__qualname__", getattr(func, "__name__", "")))


@contextmanager
def traced_span(name: str, **attributes: str | int | float | bool | None):
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise


def traced(name: str | None = None):
    def decorator(func: Callable[..., Any]):
        span_name = name or _default_span_name(func)

        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                with traced_span(span_name) as span:
                    _set_function_attributes(span, func)
                    return await func(*args, **kwargs)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            with traced_span(span_name) as span:
                _set_function_attributes(span, func)
                return func(*args, **kwargs)

        return sync_wrapper

    return decorator
