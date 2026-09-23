from __future__ import annotations

from opentelemetry import trace
from opentelemetry.trace import Span


def format_trace_id(trace_id: int) -> str | None:
    if not trace_id:
        return None
    return f"{trace_id:032x}"


def current_trace_id() -> str | None:
    span = trace.get_current_span()
    context = span.get_span_context()
    if not context.is_valid:
        return None
    return format_trace_id(context.trace_id)


def _safe_resolver_attributes(request) -> dict[str, str]:
    resolver_match = getattr(request, "resolver_match", None)
    if not resolver_match:
        return {}

    attributes: dict[str, str] = {}
    if resolver_match.view_name:
        attributes["app.view_name"] = resolver_match.view_name
        attributes["app.endpoint"] = resolver_match.view_name
    if resolver_match.route:
        attributes["app.route"] = resolver_match.route
    if resolver_match.url_name:
        attributes["app.url_name"] = resolver_match.url_name
    return attributes


def django_request_hook(span: Span, request) -> None:
    if not span or not span.is_recording():
        return

    span.set_attribute("http.request.method", getattr(request, "method", ""))
    span.set_attribute("url.path", getattr(request, "path", ""))


def django_response_hook(span: Span, request, response) -> None:
    if not span or not span.is_recording():
        return

    status_code = getattr(response, "status_code", None)
    if status_code is not None:
        span.set_attribute("http.response.status_code", status_code)

    for key, value in _safe_resolver_attributes(request).items():
        span.set_attribute(key, value)


class TraceIdResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        trace_id = current_trace_id()
        if trace_id:
            response["X-Trace-Id"] = trace_id
        return response
