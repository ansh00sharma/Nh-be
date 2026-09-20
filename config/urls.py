from django.contrib import admin
from django.urls import include, path

from api.views import api_root

urlpatterns = [
    path("", api_root, name="root"),
    path("api/", api_root, name="api-root"),
    path("api/auth/", include("accounts.urls")),
    path("api/projects/", include("projects.urls")),
    path("admin/", admin.site.urls),
]
