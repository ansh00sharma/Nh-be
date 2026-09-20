from django.urls import include, path
from rest_framework.routers import DefaultRouter

from users.views import ManagedUserViewSet


router = DefaultRouter()
router.register("", ManagedUserViewSet, basename="user")

urlpatterns = [
    path("", include(router.urls)),
]
