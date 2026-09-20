from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from api.metrics import reset_metrics


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "api-tests",
        }
    }
)
class StandardResponseAndHealthTests(APITestCase):
    def setUp(self):
        cache.clear()
        reset_metrics()

    def assert_standard_response(self, response, expected_status):
        payload = response.json()
        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(payload["status_code"], expected_status)
        self.assertIn("message", payload)
        self.assertIn("data", payload)
        self.assertIn("status", payload)
        return payload

    def test_successful_api_response_uses_standard_format(self):
        response = self.client.get("/api/")

        payload = self.assert_standard_response(response, status.HTTP_200_OK)
        self.assertEqual(payload["status"], "success")

    def test_successful_create_response_uses_standard_format(self):
        response = self.client.post(
            "/api/auth/signup/",
            {
                "first_name": "Alice",
                "last_name": "Example",
                "email": "alice-format@example.com",
                "password": "strong-password-123",
            },
            format="json",
        )

        payload = self.assert_standard_response(response, status.HTTP_201_CREATED)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["email"], "alice-format@example.com")

    def test_validation_error_uses_standard_format(self):
        response = self.client.post(
            "/api/auth/signup/",
            {"email": "bad@example.com"},
            format="json",
        )

        payload = self.assert_standard_response(response, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(payload["status"], "error")
        self.assertIsNone(payload["data"])

    def test_authentication_error_uses_standard_format(self):
        response = self.client.get("/api/tasks/")

        payload = self.assert_standard_response(response, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(payload["status"], "error")
        self.assertIsNone(payload["data"])

    def test_health_returns_healthy_database_and_cache_status(self):
        response = self.client.get("/api/health/")

        payload = self.assert_standard_response(response, status.HTTP_200_OK)
        self.assertEqual(
            payload["data"],
            {
                "database": "healthy",
                "redis": "healthy",
            },
        )

    def test_health_handles_dependency_failure_cleanly(self):
        with patch("api.views.cache.set", side_effect=RuntimeError("cache down")):
            response = self.client.get("/api/health/")

        payload = self.assert_standard_response(
            response,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
        self.assertEqual(payload["status"], "error")
        self.assertIsNone(payload["data"])

    def test_metrics_returns_counters(self):
        response = self.client.get("/api/metrics/")

        payload = self.assert_standard_response(response, status.HTTP_200_OK)
        self.assertEqual(
            set(payload["data"].keys()),
            {"total_requests", "successful_requests", "error_requests"},
        )

    def test_request_counter_increases_when_apis_are_called(self):
        before = self.client.get("/api/metrics/").json()["data"]["total_requests"]

        self.client.get("/api/")
        after = self.client.get("/api/metrics/").json()["data"]["total_requests"]

        self.assertEqual(after, before + 1)

    def test_successful_and_error_counters_increment(self):
        self.client.get("/api/")
        self.client.get("/api/tasks/")

        metrics = self.client.get("/api/metrics/").json()["data"]

        self.assertEqual(metrics["successful_requests"], 1)
        self.assertEqual(metrics["error_requests"], 1)
        self.assertEqual(metrics["total_requests"], 2)
