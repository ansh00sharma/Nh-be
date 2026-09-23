from django.core.cache import cache
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from api.metrics import get_metrics
from api.responses import error_response, success_response


standard_status_fields = {
    "message": serializers.CharField(),
    "status": serializers.CharField(),
    "status_code": serializers.IntegerField(),
}

api_root_response = inline_serializer(
    name="ApiRootResponse",
    fields={
        **standard_status_fields,
        "data": inline_serializer(
            name="ApiRootData",
            fields={"name": serializers.CharField()},
        ),
    },
)

health_response = inline_serializer(
    name="HealthResponse",
    fields={
        **standard_status_fields,
        "data": inline_serializer(
            name="HealthData",
            fields={
                "database": serializers.CharField(),
                "redis": serializers.CharField(),
            },
        ),
    },
)

metrics_response = inline_serializer(
    name="MetricsResponse",
    fields={
        **standard_status_fields,
        "data": inline_serializer(
            name="MetricsData",
            fields={
                "total_requests": serializers.IntegerField(),
                "successful_requests": serializers.IntegerField(),
                "error_requests": serializers.IntegerField(),
            },
        ),
    },
)


@extend_schema(responses=api_root_response, tags=["System"])
@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    return success_response("TaskFlow API is running", {"name": "TaskFlow API"})


@extend_schema(responses={200: health_response, 503: health_response}, tags=["System"])
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):
    checks = {"database": "not_checked"}

    try:
        cache.set("health:redis", "ok", 5)
        if cache.get("health:redis") != "ok":
            raise RuntimeError("Redis cache read failed")
        checks["redis"] = "healthy"
    except Exception:
        checks["redis"] = "unhealthy"

    if checks["redis"] == "healthy":
        return success_response("Service is healthy", checks)

    return error_response("Service dependency check failed", status_code=503)


@extend_schema(responses=metrics_response, tags=["System"])
@api_view(["GET"])
@permission_classes([AllowAny])
def metrics(request):
    return success_response("Metrics fetched successfully", get_metrics())
