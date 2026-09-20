from rest_framework.renderers import JSONRenderer

from api.responses import ERROR, SUCCESS, build_response, is_standard_response


class StandardJSONRenderer(JSONRenderer):
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = renderer_context.get("response") if renderer_context else None
        status_code = response.status_code if response else 200

        if is_standard_response(data):
            data["status_code"] = status_code
            return super().render(data, accepted_media_type, renderer_context)

        if status_code >= 400:
            message = _error_message(data)
            data = build_response(message, None, ERROR, status_code)
        else:
            data = build_response(
                _success_message(status_code),
                data,
                SUCCESS,
                status_code,
            )

        return super().render(data, accepted_media_type, renderer_context)


def _success_message(status_code):
    if status_code == 201:
        return "Created successfully"
    if status_code == 204:
        return "Deleted successfully"
    return "Request successful"


def _error_message(data):
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)
        return "Invalid request data"
    if isinstance(data, list) and data:
        return str(data[0])
    return "Request failed"
