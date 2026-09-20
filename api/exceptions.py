from rest_framework.views import exception_handler

from api.responses import error_response


def standard_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return error_response("Internal server error", status_code=500)

    message = "Request failed"
    if isinstance(response.data, dict):
        detail = response.data.get("detail")
        if detail:
            message = str(detail)
        elif response.status_code == 400:
            message = "Invalid request data"
    elif response.data:
        message = str(response.data)

    return error_response(message, status_code=response.status_code)
