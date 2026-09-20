from django.urls import include, path
from rest_framework.routers import DefaultRouter

from projects.views import ProjectViewSet


router = DefaultRouter()
router.register("", ProjectViewSet, basename="project")

urlpatterns = [
    path("", include(router.urls)),
]
