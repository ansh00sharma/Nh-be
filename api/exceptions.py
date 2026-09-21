from rest_framework.views import exception_handler

from api.responses import error_response


def _message_from_error_data(data):
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)

        messages = []
        for field, errors in data.items():
            if isinstance(errors, (list, tuple)):
                messages.append(f"{field}: {', '.join(str(error) for error in errors)}")
            elif isinstance(errors, dict):
                messages.append(f"{field}: {_message_from_error_data(errors)}")
            else:
                messages.append(f"{field}: {errors}")
        if messages:
            return "; ".join(messages)

    if isinstance(data, list) and data:
        return ", ".join(str(item) for item in data)

    return "Invalid request data"


def standard_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return error_response("Internal server error", status_code=500)

    message = "Request failed"
    if isinstance(response.data, dict):
        message = _message_from_error_data(response.data)
    elif response.data:
        message = str(response.data)

    return error_response(message, status_code=response.status_code)
