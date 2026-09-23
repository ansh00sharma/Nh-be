from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
from rest_framework.test import APITestCase

from core.observability.decorators import traced


BACKEND_DIR = Path(__file__).resolve().parents[2]
TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _project_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = BACKEND_DIR / ".env"
    if not env_file.exists():
        return values

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _run_backend_startup(*, enabled: bool) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(_project_env())
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["OTEL_ENABLED"] = "true" if enabled else "false"
    env["OTEL_CONSOLE_EXPORTER"] = "true"
    env["OTEL_TRACE_SAMPLE_RATE"] = "1.0"
    env.pop("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", None)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import config.wsgi; "
                "from core.observability import initialize_tracing; "
                "from django.db import connections; "
                "print(initialize_tracing()); "
                "connections.close_all(); "
                "print('started')"
            ),
        ],
        cwd=BACKEND_DIR,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )


class TracingStartupTests(SimpleTestCase):
    def test_backend_starts_with_tracing_disabled(self):
        result = _run_backend_startup(enabled=False)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("False", result.stdout)
        self.assertIn("started", result.stdout)

    def test_backend_starts_with_tracing_enabled(self):
        result = _run_backend_startup(enabled=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("True", result.stdout)
        self.assertIn("started", result.stdout)

    def test_initialize_tracing_is_idempotent(self):
        result = _run_backend_startup(enabled=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("True"), 1)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "observability-tests",
        }
    }
)
class TraceIdResponseTests(APITestCase):
    def test_normal_api_response_is_unchanged_when_no_trace_is_active(self):
        response = self.client.get("/api/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("X-Trace-Id", response)
        self.assertEqual(response.json()["status"], "success")

    def test_x_trace_id_is_returned_when_valid_trace_is_active(self):
        expected_trace_id = 0x4BF92F3577B34DA6A3CE929D0E0E4736
        span_context = SpanContext(
            trace_id=expected_trace_id,
            span_id=0x00F067AA0BA902B7,
            is_remote=False,
            trace_flags=TraceFlags(TraceFlags.SAMPLED),
            trace_state={},
        )
        token = context.attach(trace.set_span_in_context(NonRecordingSpan(span_context)))
        try:
            response = self.client.get("/api/")
        finally:
            context.detach(token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Trace-Id"], f"{expected_trace_id:032x}")
        self.assertRegex(response["X-Trace-Id"], TRACE_ID_PATTERN)

    def test_excluded_health_and_metrics_endpoints_work(self):
        health_response = self.client.get("/api/health/")
        metrics_response = self.client.get("/api/metrics/")

        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(metrics_response.status_code, 200)


class TracedDecoratorTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.exporter = InMemorySpanExporter()
        cls.provider = TracerProvider()
        cls.provider.add_span_processor(SimpleSpanProcessor(cls.exporter))
        try:
            trace.set_tracer_provider(cls.provider)
        except Exception:
            pass

    def setUp(self):
        self.exporter.clear()

    def test_traced_decorator_preserves_function_result(self):
        @traced("test.decorated_add")
        def add(left, right):
            return left + right

        self.assertEqual(add(2, 3), 5)

    def test_traced_decorator_reraises_exceptions(self):
        @traced("test.decorated_error")
        def fail():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            fail()

    def test_traced_decorator_supports_nested_spans(self):
        @traced("test.inner")
        def inner():
            return trace.get_current_span().get_span_context().span_id

        @traced("test.outer")
        def outer():
            outer_span_id = trace.get_current_span().get_span_context().span_id
            inner_span_id = inner()
            return outer_span_id, inner_span_id

        outer_span_id, inner_span_id = outer()

        self.assertNotEqual(outer_span_id, inner_span_id)
        self.assertNotEqual(inner_span_id, 0)
