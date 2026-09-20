from api.metrics import record_request


class MetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path != "/api/metrics/":
            record_request(response.status_code)
        return response
