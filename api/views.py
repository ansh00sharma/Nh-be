from django.core.cache import cache
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.metrics import get_metrics
from api.responses import error_response, success_response


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return success_response("TaskFlow API is running", {"name": "TaskFlow API"})


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    checks = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"

    try:
        cache.set("health:redis", "ok", 5)
        if cache.get("health:redis") != "ok":
            raise RuntimeError("Redis cache read failed")
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    if all(value == "healthy" for value in checks.values()):
        return success_response("Service is healthy", checks)

    return error_response("Service dependency check failed", status_code=503)


@api_view(["GET"])
@permission_classes([AllowAny])
def metrics(request):
    return success_response("Metrics fetched successfully", get_metrics())
