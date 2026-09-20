from django.contrib import admin
from django.urls import path

from api.views import api_root

urlpatterns = [
    path("", api_root, name="root"),
    path("api/", api_root, name="api-root"),
    path("admin/", admin.site.urls),
]
