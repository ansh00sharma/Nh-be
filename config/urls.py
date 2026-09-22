from django.contrib import admin
from django.urls import include, path

from api.views import api_root, health, metrics

urlpatterns = [
    path("", api_root, name="root"),
    path("api/", api_root, name="api-root"),
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
