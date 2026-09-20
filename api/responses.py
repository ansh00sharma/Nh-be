from rest_framework.response import Response


SUCCESS = "success"
ERROR = "error"


def build_response(message, data, status_text, status_code):
    return {
        "message": message,
        "data": data,
        "status": status_text,
        "status_code": status_code,
    }


def success_response(message, data=None, status_code=200):
    return Response(
        build_response(message, data, SUCCESS, status_code),
        status=status_code,
    )


def error_response(message, status_code=400):
    return Response(
        build_response(message, None, ERROR, status_code),
        status=status_code,
    )


def is_standard_response(data):
    return (
        isinstance(data, dict)
        and {"message", "data", "status", "status_code"}.issubset(data.keys())
    )
