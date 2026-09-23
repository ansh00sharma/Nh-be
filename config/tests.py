from django.conf import settings
from django.test import SimpleTestCase


class DatabaseSettingsTests(SimpleTestCase):
    def test_database_connections_are_persistent_without_per_request_health_checks(self):
        self.assertEqual(settings.DATABASES["default"]["CONN_MAX_AGE"], 600)
        self.assertIs(settings.DATABASES["default"]["CONN_HEALTH_CHECKS"], False)
