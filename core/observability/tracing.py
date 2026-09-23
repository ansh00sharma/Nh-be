from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from django.apps import apps
from django.conf import settings
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import SpanKind, Status, StatusCode

from core.observability.hooks import django_request_hook, django_response_hook


logger = logging.getLogger(__name__)

_init_lock = threading.Lock()
_initialized = False
_django_dispatch_patched = False


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bounded_sample_rate() -> float:
    return max(0.0, min(1.0, _env_float("OTEL_TRACE_SAMPLE_RATE", 1.0)))


def _service_version() -> str:
    spectacular_settings = getattr(settings, "SPECTACULAR_SETTINGS", {})
    return str(spectacular_settings.get("VERSION", ""))


def _deployment_environment() -> str:
    return os.environ.get("DEPLOYMENT_ENVIRONMENT") or os.environ.get("DJANGO_ENV") or "local"


def _excluded_urls() -> str:
    configured = os.environ.get("OTEL_DJANGO_EXCLUDED_URLS")
    if configured:
        return configured
    return ",".join(
        (
            r"^/metrics/?$",
            r"^/api/metrics/?$",
            r"^/health/?$",
            r"^/healthz/?$",
            r"^/api/health/?$",
            r"^/api/healthz/?$",
        )
    )


def _instrument_if_available(module_path: str, class_name: str, configure: Callable | None = None) -> None:
    try:
        module = __import__(module_path, fromlist=[class_name])
    except ModuleNotFoundError:
        logger.warning("OpenTelemetry instrumentation package is not installed: %s", module_path)
        return

    try:
        instrumentor = getattr(module, class_name)()
        kwargs = configure() if configure else {}
        instrumentor.instrument(**kwargs)
    except Exception:
        logger.exception("OpenTelemetry instrumentation failed for %s.%s", module_path, class_name)


def _instrument_django() -> None:
    _instrument_if_available(
        "opentelemetry.instrumentation.django",
        "DjangoInstrumentor",
        lambda: {
            "request_hook": django_request_hook,
            "response_hook": django_response_hook,
            "excluded_urls": _excluded_urls(),
        },
    )


def _instrument_dependencies() -> None:
    _instrument_if_available("opentelemetry.instrumentation.psycopg", "PsycopgInstrumentor")
    _instrument_if_available("opentelemetry.instrumentation.redis", "RedisInstrumentor")
    _instrument_if_available("opentelemetry.instrumentation.celery", "CeleryInstrumentor")


def patch_drf_dispatch() -> None:
    global _django_dispatch_patched

    if _django_dispatch_patched:
        return

    if not apps.apps_ready or not apps.models_ready:
        return

    try:
        from rest_framework.views import APIView
    except Exception:
        logger.exception("Failed to import DRF APIView for tracing")
        return

    if getattr(APIView, "_otel_traced_dispatch", False):
        _django_dispatch_patched = True
        return

    original_dispatch = APIView.dispatch
    tracer = trace.get_tracer("taskflow.drf")

    def traced_dispatch(self, request, *args, **kwargs):
        action = getattr(self, "action", None) or getattr(request, "method", "").lower()
        view_class = self.__class__.__name__
        span_name = f"{view_class}.{action}"
        with tracer.start_as_current_span(span_name, kind=SpanKind.INTERNAL) as span:
            span.set_attribute("app.view_class", view_class)
            span.set_attribute("app.view_action", action)
            span.set_attribute("app.endpoint", span_name)
            span.set_attribute("http.request.method", getattr(request, "method", ""))
            try:
                response = original_dispatch(self, request, *args, **kwargs)
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            status_code = getattr(response, "status_code", None)
            if status_code is not None:
                span.set_attribute("http.response.status_code", status_code)
            return response

    APIView.dispatch = traced_dispatch
    APIView._otel_traced_dispatch = True
    APIView._otel_original_dispatch = original_dispatch
    _django_dispatch_patched = True


def initialize_tracing() -> bool:
    global _initialized

    if _initialized:
        return _env_bool("OTEL_ENABLED", False)

    with _init_lock:
        if _initialized:
            return _env_bool("OTEL_ENABLED", False)

        enabled = _env_bool("OTEL_ENABLED", False)
        if not enabled:
            _initialized = True
            return False

        service_name = os.environ.get("OTEL_SERVICE_NAME", "taskflow-backend")
        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                SERVICE_VERSION: _service_version(),
                DEPLOYMENT_ENVIRONMENT: _deployment_environment(),
            }
        )
        provider = TracerProvider(
            resource=resource,
            sampler=ParentBased(TraceIdRatioBased(_bounded_sample_rate())),
        )

        try:
            endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
            exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))

            if _env_bool("OTEL_CONSOLE_EXPORTER", False):
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

            trace.set_tracer_provider(provider)
        except Exception:
            logger.exception("OpenTelemetry provider initialization failed")
            _initialized = True
            return False

        _instrument_django()
        _instrument_dependencies()
        patch_drf_dispatch()

        _initialized = True
        return True


class TraceContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            record.trace_id = f"{span_context.trace_id:032x}"
            record.span_id = f"{span_context.span_id:016x}"
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return True
