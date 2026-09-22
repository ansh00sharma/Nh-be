from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from api.views import api_root, health, metrics

urlpatterns = [
    path("", api_root, name="root"),
    path("api/", api_root, name="api-root"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/health/", health, name="health"),
    path("api/metrics/", metrics, name="metrics"),
    path("api/auth/", include("users.urls")),
    path("api/dashboard/", include("dashboard.urls")),
    path("api/users/", include("users.api_urls")),
    path("api/projects/", include("projects.urls")),
    path("api/tasks/", include("tasks.urls")),
    path("api/notifications/", include("notifications.urls")),
    path("admin/", admin.site.urls),
]
